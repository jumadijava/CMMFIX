"""
utils/xgb_inference.py
─────────────────────
Shared XGBoost inference — dipakai bersama oleh Dashboard dan Predictive.
Inference hanya jalan sekali per sesi per shift, hasilnya di-cache 30 menit.

Cache key: "xgb_cls_{next_shift}_{next_date}" — identik di semua halaman.
"""

import time
import logging
import pandas as pd
import streamlit as st
from pathlib import Path
from utils.prediction_cache import save_xgb, load_xgb, save_rules, load_rules

TTL_SECONDS = 1800  # 30 menit

# ── Logger diagnostik ─────────────────────────────────────────────
# Inference dijalankan di background thread dengan try/except lebar, jadi
# kegagalan mudah "hilang" tanpa jejak. Tulis alasan skip/error ke
# data/xgb_inference.log supaya bisa ditelusuri kalau prediksi tak muncul.
_logger = logging.getLogger("xgb_inference")
if not _logger.handlers:
    try:
        Path("data").mkdir(exist_ok=True)
        _h = logging.FileHandler(Path("data") / "xgb_inference.log", encoding="utf-8")
        _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        _logger.addHandler(_h)
        _logger.setLevel(logging.INFO)
    except Exception:
        pass


def _log_skip(model_stem: str, reason: str) -> None:
    try:
        _logger.warning("skip %s: %s", model_stem, reason)
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────
CACHE_KEY_PREFIX = "xgb_cls_v2"  # v2: include Category filter fix


def _get_next_shift():
    """Deteksi shift berikutnya berdasarkan jam WIB."""
    try:
        import pytz
        from datetime import datetime, date
        now = datetime.now(pytz.timezone("Asia/Jakarta"))
    except Exception:
        from datetime import datetime, date
        now = datetime.now()

    hour = now.hour
    today = now.date() if hasattr(now, "date") else date.today()

    if 7 <= hour < 16:
        cur_shift, next_shift, next_date = 1, 2, today
    elif 16 <= hour < 24:
        cur_shift, next_shift, next_date = 2, 3, today
    else:
        cur_shift, next_shift, next_date = 3, 1, today

    return cur_shift, next_shift, next_date


def get_xgb_cache_key():
    """Return (cache_key, cur_shift, next_shift, next_date)."""
    cur_shift, next_shift, next_date = _get_next_shift()
    cache_key = f"{CACHE_KEY_PREFIX}_{next_shift}_{next_date.isoformat()}"
    return cache_key, cur_shift, next_shift, next_date


def run_xgb_inference(df_all: pd.DataFrame, allow_compute: bool = True) -> pd.DataFrame | None:
    """
    Jalankan XGBoost inference untuk semua model.
    Hasilnya di-cache di session_state selama TTL_SECONDS.

    allow_compute=False → kalau cache (session_state / JSON) belum ada,
    langsung return None tanpa compute. Dipakai oleh caller non-blocking
    (misal Dashboard) supaya tidak freeze main thread; compute berat
    diserahkan ke background warmup thread di mainloca.py.

    Return:
        DataFrame hasil inference (semua model digabung), atau None kalau gagal
        atau kalau allow_compute=False dan cache belum siap.
        Kolom: PartName, ModelName, SampleNo, CMMName, Parameter, Category,
               ref, point, Nominal, Uppertol, Lowertol, KP,
               Prob_NG, Pred, Risiko, _threshold
    """
    cache_key, cur_shift, next_shift, next_date = get_xgb_cache_key()
    ts_key = f"{cache_key}_ts"

    # 1. Return dari session_state kalau ada
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    # 2. Load dari JSON cache kalau key cocok (login berikutnya, shift sama)
    cached = load_xgb(cache_key)
    if cached is not None:
        st.session_state[cache_key] = cached
        return cached

    # 3. Cache belum siap dan caller minta non-blocking → jangan compute
    if not allow_compute:
        return None

    # Run inference
    try:
        import joblib, json as _json
        MODEL_DIR = Path("models")
        if not MODEL_DIR.exists():
            return None

        model_files = sorted(MODEL_DIR.glob("xgb_*.pkl"))
        if not model_files:
            return None

        all_results = []
        for mp in model_files:
            stem = mp.stem.replace("xgb_", "")
            ep   = MODEL_DIR / f"encoders_{stem}.pkl"
            ip   = MODEL_DIR / f"model_info_{stem}.json"
            if not ep.exists() or not ip.exists():
                continue
            try:
                xgb_model = joblib.load(mp)
                encoders  = joblib.load(ep)
                with open(ip) as fi:
                    minfo = _json.load(fi)
            except Exception as e:
                _log_skip(stem, f"gagal load model/encoder/info: {e}")
                continue

            threshold = minfo.get("optimal_threshold", 0.5)
            features  = minfo.get("features", [])
            f_part    = minfo.get("part", "")
            f_model   = minfo.get("model_name", "")

            df_ref = df_all[
                (df_all["PartName"] == f_part) & (df_all["ModelName"] == f_model)
            ][["PartName","ModelName","SampleNo","CMMName","Parameter",
               "Category","ref","point","Nominal","Uppertol","Lowertol","KP"]
             ].drop_duplicates().copy()
            if df_ref.empty:
                continue

            df_ref["Shift"]       = next_shift
            df_ref["Cycle"]       = 1
            df_ref["DayOfWeek"]   = next_date.weekday()
            df_ref["Hour"]        = 7 if next_shift==1 else (16 if next_shift==2 else 0)
            df_ref["DayOfMonth"]  = next_date.day
            df_ref["WeekOfYear"]  = int(next_date.isocalendar()[1])
            df_ref["TolRange"]    = df_ref["Uppertol"] - df_ref["Lowertol"]
            df_ref["TolMidpoint"] = (df_ref["Uppertol"] + df_ref["Lowertol"]) / 2

            for col in ["PartName","ModelName","SampleNo","CMMName",
                        "Parameter","Category","ref","point"]:
                le = encoders.get(col)
                if le:
                    # Gunakan map dict — jauh lebih cepat dari .apply() per sel
                    known_map = {v: i for i, v in enumerate(le.classes_)}
                    df_ref[col+"_enc"] = df_ref[col].astype(str).map(known_map).fillna(-1).astype(int)
                else:
                    df_ref[col+"_enc"] = 0

            try:
                # Pastikan SEMUA fitur bertipe numerik sebelum prediksi.
                # KP (dan beberapa kolom lain) tersimpan sebagai TEXT di
                # SQLite, sehingga df_ref["KP"] bertipe object/string.
                # XGBoost 3.x menolak kolom object dan akan raise untuk
                # SETIAP model — akibatnya prediksi tidak pernah muncul.
                # Coerce ke numerik dulu (NaN → 0) agar aman.
                X = df_ref[features].apply(pd.to_numeric, errors="coerce").fillna(0)
                proba = xgb_model.predict_proba(X)[:, 1]
            except Exception as e:
                _log_skip(stem, f"predict_proba gagal: {e}")
                continue

            df_ref["Prob_NG"]    = (proba * 100).round(1)
            df_ref["Pred"]       = ["NG" if p >= threshold else "OK" for p in proba]
            df_ref["Risiko"]     = df_ref["Prob_NG"].apply(
                lambda p: "🔴 Tinggi" if p >= threshold * 100 else
                          ("🟡 Sedang" if p >= 30 else "🟢 Rendah")
            )
            df_ref["_threshold"] = threshold
            all_results.append(df_ref)

        if not all_results:
            _logger.warning(
                "Tidak ada hasil XGB: %d model ditemukan tapi semua dilewati "
                "(cek data matching part/model atau error di atas).",
                len(model_files),
            )
            return None

        result = pd.concat(all_results, ignore_index=True)
        # Simpan ke JSON (aman dari background thread)
        save_xgb(cache_key, result)
        # Simpan ke session_state kalau di main thread
        try:
            st.session_state[cache_key] = result
        except Exception:
            pass
        return result

    except Exception as e:
        _logger.exception("run_xgb_inference gagal total: %s", e)
        return None


def get_prediction_alerts(df_all: pd.DataFrame,
                           filter_part: str = None,
                           filter_model: str = None,
                           filter_cmm: str = None,
                           allow_compute: bool = True) -> list:
    """
    Ambil alert prediksi NG untuk Dashboard.
    Pakai shared cache — tidak compute ulang kalau Predictive sudah run.

    allow_compute=False → non-blocking, return [] kalau cache belum siap.

    Return list dict: part, model, shift, n_ng, top_ref, top_ref_raw,
                      top_param, top_prob, label
    """
    result = run_xgb_inference(df_all, allow_compute=allow_compute)
    if result is None or result.empty:
        return []

    _, cur_shift, next_shift, next_date = get_xgb_cache_key()

    df = result.copy()

    # Dashboard hanya tampilkan prediksi Produksi (bukan QIS/waste)
    if "Category" in df.columns:
        df = df[df["Category"] == "Produksi"]

    # Filter tambahan dari caller
    if filter_part:
        df = df[df["PartName"] == filter_part]
    if filter_model:
        df = df[df["ModelName"] == filter_model]
    if filter_cmm:
        df = df[df["CMMName"] == filter_cmm]

    # Hanya prediksi NG dengan prob >= threshold masing-masing model
    df_ng = df[df["Pred"] == "NG"].copy()
    if df_ng.empty:
        return []

    alerts = []
    ref_col   = "ref"   if "ref"   in df_ng.columns else "PartName"
    param_col = "point" if "point" in df_ng.columns else "Parameter"

    # Pastikan SampleNo tidak kosong
    df_ng["SampleNo"] = df_ng["SampleNo"].fillna("—").astype(str)

    for (f_part, f_model, sno), grp in df_ng.groupby(["PartName","ModelName","SampleNo"]):
        grp_s = grp.sort_values("Prob_NG", ascending=False)
        top   = grp_s.iloc[0]
        # Ambil semua ref·param yang prediksi NG, tampilkan yang teratas
        top_ref_val   = str(top[ref_col])   if ref_col   in top.index else "-"
        top_param_val = str(top[param_col]) if param_col in top.index else "-"
        alerts.append({
            "part":          str(f_part),
            "model":         str(f_model),
            "shift":         next_shift,
            "n_ng":          len(grp_s),
            "top_ref":       f'{top_ref_val} · {top_param_val}',
            "top_ref_raw":   top_ref_val,
            "top_param":     top_param_val,
            "top_prob":      float(top["Prob_NG"]),
            "label":         f"{f_part} {f_model} No.{sno} Shift {next_shift}",
        })

    return sorted(alerts, key=lambda x: -x["top_prob"])


# ─────────────────────────────────────────────────────────────────
#  PREDIKSI RULE — shared cache
# ─────────────────────────────────────────────────────────────────
RULE_CACHE_KEY  = "rule_pred_v1"
RULE_TTL        = 1800  # 30 menit

# Default params — sama dengan default di Predictive
RULE_N_HIST = 20
RULE_N_FC   = 10

RULE_DESC = {
    1: "titik di luar batas kendali (outlier)",
    2: "8 titik berurutan di satu sisi rata-rata",
    3: "7 titik naik/turun berurutan (drift)",
    4: "14 titik bergantian naik-turun (osilasi)",
    5: "2 dari 3 titik mendekati batas (pergeseran awal)",
    6: "4 dari 5 titik jauh dari pusat (drift halus)",
    7: "15 titik dalam zona C (stratifikasi)",
}


def _detect_kendali_shared(values: list) -> dict:
    """Deteksi 7 Nelson rules. Sama persis dengan _detect_kendali di predictive.py."""
    import numpy as np
    vbr = {r: set() for r in range(1, 8)}
    n = len(values)
    if n < 2:
        return vbr
    mean  = float(np.mean(values))
    sigma = float(np.std(values, ddof=1)) if n > 1 else 0.0
    if sigma == 0:
        return vbr
    for i, v in enumerate(values):
        if abs(v - mean) > 3 * sigma: vbr[1].add(i)
    for i in range(n - 7):
        w = values[i:i+8]
        if all(v > mean for v in w) or all(v < mean for v in w):
            for j in range(i, i+8): vbr[2].add(j)
    for i in range(n - 6):
        w = values[i:i+7]
        if all(w[j] < w[j+1] for j in range(6)) or all(w[j] > w[j+1] for j in range(6)):
            for j in range(i, i+7): vbr[3].add(j)
    for i in range(n - 13):
        w = values[i:i+14]
        if all((w[j] < w[j+1]) != (w[j+1] < w[j+2]) for j in range(12)):
            for j in range(i, i+14): vbr[4].add(j)
    for i in range(n - 2):
        w = values[i:i+3]
        if (sum(1 for v in w if v > mean + 2*sigma) >= 2 or
                sum(1 for v in w if v < mean - 2*sigma) >= 2):
            for j in range(i, i+3): vbr[5].add(j)
    for i in range(n - 4):
        w = values[i:i+5]
        if (sum(1 for v in w if v > mean + sigma) >= 4 or
                sum(1 for v in w if v < mean - sigma) >= 4):
            for j in range(i, i+5): vbr[6].add(j)
    for i in range(n - 14):
        w = values[i:i+15]
        if all(abs(v - mean) < sigma for v in w):
            for j in range(i, i+15): vbr[7].add(j)
    return vbr


def run_rule_prediction(df_all: pd.DataFrame,
                         n_hist: int = RULE_N_HIST,
                         n_fc: int   = RULE_N_FC,
                         allow_compute: bool = True) -> list | None:
    """
    Scan semua titik ukur (Category=Produksi), deteksi rule yang akan terpicu.
    Cache 30 menit di session_state.

    allow_compute=False → kalau cache (session_state / JSON) belum ada,
    langsung return None tanpa compute. Dipakai oleh caller non-blocking
    (misal Dashboard) supaya tidak freeze main thread; compute berat
    diserahkan ke background warmup thread di mainloca.py.

    Return: list dict per titik yang status != Aman, atau None kalau gagal
    atau kalau allow_compute=False dan cache belum siap.
    """
    import numpy as np

    ts_key = f"{RULE_CACHE_KEY}_ts"

    # 1. Return dari session_state kalau ada
    if RULE_CACHE_KEY in st.session_state:
        return st.session_state[RULE_CACHE_KEY]

    # 2. Load dari JSON cache (pakai xgb cache key agar invalidasi seragam per shift)
    _xgb_key, *_ = get_xgb_cache_key()
    cached_rules = load_rules(_xgb_key)
    if cached_rules is not None:
        st.session_state[RULE_CACHE_KEY] = cached_rules
        return cached_rules

    # 3. Cache belum siap dan caller minta non-blocking → jangan compute
    if not allow_compute:
        return None

    try:
        df = df_all.copy()
        # Hanya Produksi untuk alert dashboard
        if "Category" in df.columns:
            df = df[df["Category"] == "Produksi"]

        param_col = "point" if "point" in df.columns else "Parameter"
        ref_col   = "ref"   if "ref"   in df.columns else "ID"

        all_rows = []
        group_keys = [c for c in ["PartName","ModelName","SampleNo", ref_col, param_col]
                      if c in df.columns]

        for keys, grp in df.groupby(group_keys, sort=False):
            key_dict = dict(zip(group_keys, keys if isinstance(keys, tuple) else [keys]))
            part  = key_dict.get("PartName","")
            model = key_dict.get("ModelName","")
            sno   = str(key_dict.get("SampleNo",""))
            ref   = str(key_dict.get(ref_col,""))
            param = str(key_dict.get(param_col,""))
            kp    = bool(grp["KP"].astype(str).isin(["1","1.0","True"]).any()) if "KP" in grp.columns else False

            grp_s = grp.sort_values(["Date","Shift","Cycle"]).dropna(subset=["Actual"])
            if len(grp_s) < 10:
                continue

            y_all = grp_s["Actual"].tolist()
            y_use = y_all[-int(n_hist):]
            n_use = len(y_use)
            if n_use < 5:
                continue

            nom  = float(grp_s["Nominal"].dropna().iloc[0])  if grp_s["Nominal"].notna().any()  else 0.0
            utol = float(grp_s["Uppertol"].dropna().iloc[0]) if grp_s["Uppertol"].notna().any() else 0.0
            ltol = float(grp_s["Lowertol"].dropna().iloc[0]) if grp_s["Lowertol"].notna().any() else 0.0
            usl  = round(nom + utol, 5)
            lsl  = round(nom + ltol, 5)

            x_arr = np.arange(n_use)
            slope, intercept = np.polyfit(x_arr, y_use, 1)

            x_fc_arr = np.arange(n_use, n_use + int(n_fc))
            y_fc     = (slope * x_fc_arr + intercept).tolist()

            y_combined   = y_use + y_fc
            vbr_combined = _detect_kendali_shared(y_combined)

            fc_rules_violated = [
                r for r, idxs in vbr_combined.items()
                if any(i >= n_use for i in idxs)
            ]
            n_fc_ng = sum(1 for v in y_fc if v > usl or v < lsl)
            trend_lbl = "📈 Naik" if slope > 1e-6 else ("📉 Turun" if slope < -1e-6 else "➡ Stabil")

            shifts_to_batas = None
            if slope > 1e-9:
                s = (usl - y_use[-1]) / slope
                if 0 < s <= 50: shifts_to_batas = int(s)
            elif slope < -1e-9:
                s = (lsl - y_use[-1]) / slope
                if 0 < s <= 50: shifts_to_batas = int(s)

            status = ("🔴 Rule Terpicu" if fc_rules_violated else
                      ("🟡 NG Prediksi" if n_fc_ng > 0 else
                       ("⚠ Tren Menuju Batas" if shifts_to_batas else "🟢 Aman")))

            if status == "🟢 Aman":
                pass  # tetap disimpan agar Predictive bisa pakai shared cache

            all_rows.append({
                "Part":          part,
                "Model":         model,
                "Sample":        sno,
                "Ref":           ref,
                "Parameter":     param,
                "KP":            kp,
                "Tren":          trend_lbl,
                "NG Prediksi":   n_fc_ng,
                "Rule Terpicu":  len(fc_rules_violated),
                "Rule List":     ", ".join([f"R{r}" for r in sorted(fc_rules_violated)]) or "-",
                "Est. Shift ke Batas": shifts_to_batas if shifts_to_batas else "-",
                "Status":        status,
                "Slope":         round(slope, 6),
                "n Data":        n_use,
                "Slope (mm/sh)": round(slope, 6),
                # Data untuk chart detail di Predictive
                "_y_use":        y_use,
                "_y_fc":         y_fc,
                "_usl":          usl,
                "_lsl":          lsl,
                "_nom":          nom,
                "_vbr":          vbr_combined,
                "_n_use":        n_use,
            })

        # Sort: Rule Terpicu dulu, lalu NG Prediksi, lalu Tren Menuju Batas
        STATUS_ORDER = {"🔴 Rule Terpicu": 0, "🟡 NG Prediksi": 1, "⚠ Tren Menuju Batas": 2}
        all_rows.sort(key=lambda r: (STATUS_ORDER.get(r["Status"], 9), -r["Rule Terpicu"], -r["NG Prediksi"]))

        # Simpan ke JSON (aman dari background thread)
        _xgb_key_save, *_ = get_xgb_cache_key()
        save_rules(_xgb_key_save, all_rows)
        # Simpan ke session_state kalau di main thread
        try:
            st.session_state[RULE_CACHE_KEY] = all_rows
        except Exception:
            pass
        return all_rows

    except Exception:
        return None


def get_rule_alerts(df_all: pd.DataFrame,
                     filter_part: str = None,
                     filter_model: str = None,
                     limit: int = 20,
                     allow_compute: bool = True) -> list:
    """
    Return top-N alert prediksi rule untuk carousel Dashboard.
    Prioritas: Rule Terpicu > NG Prediksi > Tren Menuju Batas.

    allow_compute=False → non-blocking, return [] kalau cache belum siap.
    """
    rows = run_rule_prediction(df_all, allow_compute=allow_compute)
    if not rows:
        return []

    alerts = []
    for r in rows:
        if r["Status"] == "🟢 Aman":
            continue
        # Filter part/model kalau ada
        if filter_part and r["Part"] != filter_part:
            continue
        if filter_model and r["Model"] != filter_model:
            continue
        # Prioritaskan KP atau Rule Terpicu / NG Prediksi saja
        if not r["KP"] and r["Status"] not in ("🔴 Rule Terpicu", "🟡 NG Prediksi"):
            continue
        rule_list = r["Rule List"] if r["Rule List"] != "-" else ""
        rule_descs = ", ".join(
            RULE_DESC.get(int(rx.replace("R","")), rx)
            for rx in rule_list.split(", ") if rx
        ) if rule_list else ""
        alerts.append({
            "part":       r["Part"],
            "model":      r["Model"],
            "sno":        r["Sample"],
            "ref":        r["Ref"],
            "param":      r["Parameter"],
            "kp":         r["KP"],
            "status":     r["Status"],
            "tren":       r["Tren"],
            "rule_list":  rule_list,
            "rule_descs": rule_descs,
            "n_ng_pred":  r["NG Prediksi"],
            "est_batas":  r["Est. Shift ke Batas"],
            "label":      f"{r['Part']} {r['Model']} No.{r['Sample']} · {r['Ref']} · {r['Parameter']}",
        })
        if len(alerts) >= limit:
            break

    return alerts