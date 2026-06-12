"""
pages_app/dashboard.py — Halaman Dashboard (ringkasan kualitas real-time).
═══════════════════════════════════════════════════════════════════════
Menampilkan:
  • Alert NG aktual, prediksi XGBoost shift berikutnya, dan rule SPC (carousel)
  • KPI utama (total titik, part diukur, part NG, rasio OK, total titik NG)
  • Chart tren OK rate, distribusi NG, dan status per mesin CMM
Inference berat (XGBoost) dipakai bersama dengan Predictive via utils.xgb_inference
sehingga cache-nya sama (tidak menghitung ulang antar halaman).
"""
import streamlit as st
from streamlit_echarts import st_echarts
import pandas as pd
from datetime import datetime
import pytz
from streamlit_echarts import JsCode

# Import utilitas filter bersama
from utils.filters import build_filters_dashboard, apply_filters, TIMEZONE, TARGET_OK
from utils.xgb_inference import get_prediction_alerts, get_xgb_cache_key, run_xgb_inference
from local_db import get_root_causes

# ── Rekomendasi per kategori RC ──────────────────────────────────
_REKOMENDASI_SINGKAT = {
    "Mesin / Machine":  "Cek kalibrasi probe dan kondisi mesin sebelum lanjut produksi",
    "Setup / Fixture":  "Verifikasi posisi fixture dan datum reference",
    "Material":         "Lakukan incoming inspection — pisahkan material suspect",
    "Operator":         "Brief operator terkait SOP setup titik ini",
    "Program CMM":      "Update program CMM sesuai revisi drawing terbaru",
    "Tooling":          "Cek tool wear — ganti insert jika perlu",
    "Lainnya":          "Investigasi lebih lanjut bersama engineer",
}

_SARAN_PARAM = {
    "posisi": "Cek fixture dan datum reference",
    "position": "Cek fixture dan datum reference",
    "distance": "Verifikasi tool wear dan probe approach",
    "diameter": "Cek tool wear dan kondisi tooling",
    "concentricity": "Verifikasi setup dan centering fixture",
    "flatness": "Cek surface condition dan material",
    "straightness": "Verifikasi setup fixture dan material",
}


@st.cache_data(ttl=120, show_spinner=False)
def _load_rc_lookup():
    """Cache lookup RC per titik → kategori dominan."""
    all_rcs = get_root_causes()
    if not all_rcs:
        return {}
    df = pd.DataFrame(all_rcs)
    lookup = {}
    for (part, model, ref, param), g in df.groupby(["part","model","ref","parameter"]):
        cat_counts = g["category"].value_counts()
        if len(cat_counts):
            top_cat = cat_counts.index[0]
            top_pct = round(cat_counts.iloc[0]/len(g)*100)
            lookup[(str(part), str(model), str(ref), str(param))] = {
                "cat": top_cat, "pct": top_pct, "n": len(g)
            }
    return lookup


def _get_saran(part: str, model: str, ref: str, param: str) -> str:
    """Return satu kalimat saran berdasarkan RC historis atau pola parameter."""
    lookup = _load_rc_lookup()
    key = (str(part), str(model), str(ref), str(param))
    if key in lookup:
        info = lookup[key]
        saran = _REKOMENDASI_SINGKAT.get(info["cat"], "Investigasi bersama engineer")
        return f"{saran} (dominan: {info['cat']} {info['pct']}%)"
    # Fallback berdasarkan nama parameter
    param_lower = str(param).lower()
    for kw, saran in _SARAN_PARAM.items():
        if kw in param_lower:
            return saran
    return "Investigasi penyebab bersama engineer"


@st.cache_resource
def _load_xgb_models():
    """Load semua XGBoost models sekali saja — shared semua session."""
    try:
        import joblib, json
        from pathlib import Path as _Path
        MODEL_DIR = _Path("models")
        if not MODEL_DIR.exists():
            return {}
        models = {}
        for mp in sorted(MODEL_DIR.glob("xgb_*.pkl")):
            stem = mp.stem.replace("xgb_", "")
            ep   = MODEL_DIR / f"encoders_{stem}.pkl"
            ip   = MODEL_DIR / f"model_info_{stem}.json"
            if not ep.exists() or not ip.exists():
                continue
            try:
                models[stem] = {
                    "model":    joblib.load(mp),
                    "encoders": joblib.load(ep),
                    "info":     json.load(open(ip)),
                }
            except Exception:
                continue
        return models
    except Exception:
        return {}


class DashboardPage:
    def __init__(self, df_all: pd.DataFrame):
        self.df_all = df_all

    # ── SVG icons ──────────────────────────────────────────────────
    def _get_prediction_alerts(self, filter_part=None, filter_model=None, filter_cmm=None) -> list:
        """Delegasi ke shared xgb_inference — cache di-share dengan Predictive.
        Non-blocking: kalau cache belum siap, return [] (jangan compute di main thread,
        biar tidak freeze; compute berat diserahkan ke background warmup thread)."""
        return get_prediction_alerts(
            self.df_all,
            filter_part=filter_part,
            filter_model=filter_model,
            filter_cmm=filter_cmm,
            allow_compute=False,
        )

    def _get_ng_alerts(self, df: pd.DataFrame, limit: int = 20) -> list:
        """Ambil NG terbaru dari df terfilter, sort by Date desc."""
        if df.empty:
            return []
        df_ng = df[df["Judgement"] == "NG"].copy()
        if df_ng.empty:
            return []

        df_ng = df_ng.sort_values("Date", ascending=False).head(limit)

        has_kp    = "KP" in df_ng.columns
        has_ref   = "ref" in df_ng.columns
        has_point = "point" in df_ng.columns

        alerts = []
        for _, row in df_ng.iterrows():
            is_kp = bool(has_kp and str(row.get("KP", "0")) in ("1", "1.0"))

            ref_str   = str(row.get("ref", "")) if has_ref else ""
            if not ref_str or ref_str in ("", "nan", "-"):
                ref_str = str(row.get("ID", ""))
            param_str = str(row.get("point", "")) if has_point else ""
            if not param_str or param_str in ("", "nan", "-"):
                param_str = str(row.get("Parameter", ""))
            top_label = f"{ref_str} · {param_str}" if ref_str and param_str else (ref_str or param_str or "-")

            dev = row.get("Deviation", None)
            dev_str = f"{float(dev):+.4f}" if dev is not None and str(dev) not in ("", "nan") else "-"

            waktu = pd.to_datetime(row["Date"]).strftime("%d %b · %H:%M")

            alerts.append({
                "part":      str(row.get("PartName", "-")),
                "model":     str(row.get("ModelName", "-")),
                "sno":       str(row.get("SampleNo", "-")),
                "is_kp":     is_kp,
                "top_label": top_label,
                "top_dev":   dev_str,
                "waktu":     waktu,
                "label":     f"{row.get('PartName','')} {row.get('ModelName','')} · {row.get('SampleNo','-')}",
                "saran":     _get_saran(
                    str(row.get("PartName","")),
                    str(row.get("ModelName","")),
                    str(row.get("ref","")),
                    str(row.get("point",""))
                ),
            })

        return alerts

    def svg_check(self):
        return '<svg viewBox="0 0 24 24" fill="none" stroke="#2563EB" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'

    def svg_percent(self):
        return '<svg viewBox="0 0 24 24" fill="none" stroke="#15803D" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/></svg>'

    def svg_cross(self):
        return '<svg viewBox="0 0 24 24" fill="none" stroke="#B91C1C" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'

    def svg_alert(self):
        return '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#DC2626" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'

    def svg_shield_ok(self):
        return '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#16A34A" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>'

    # ── Definisi "1 part" ──────────────────────────────────────────
    # 1 part = 1 set titik ukur (sesuai Mapping) dari satu SampleNo yang
    # diukur dalam satu kali pengukuran. Satu file pengukuran = satu
    # timestamp (Date) → kunci unik part instance:
    #   (Date, Shift, Cycle, SampleNo, PartName, ModelName)
    # Kedua KPI (Total Part & Part NG) HARUS pakai kunci yang sama dan
    # sama-sama KHUSUS Category=Produksi agar konsisten.
    _PART_KEYS = ["Date", "Shift", "Cycle", "SampleNo", "PartName", "ModelName"]

    def _produksi_only(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filter khusus Produksi (kalau kolom Category ada)."""
        if "Category" in df.columns:
            return df[df["Category"] == "Produksi"]
        return df

    def _part_group_cols(self, df: pd.DataFrame) -> list:
        return [c for c in self._PART_KEYS if c in df.columns]

    # ── Helper: hitung jumlah part (khusus Category=Produksi) ──────
    def _count_parts(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        df_prod = self._produksi_only(df)
        if df_prod.empty:
            return 0
        return df_prod.groupby(self._part_group_cols(df_prod)).ngroups

    # ── Helper: hitung jumlah part NG (khusus Category=Produksi) ────
    # Sebuah part dihitung NG jika ada minimal 1 titik NG pada instance tsb.
    def _count_ng_parts(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        df_prod = self._produksi_only(df)
        if df_prod.empty:
            return 0
        grp_cols = self._part_group_cols(df_prod)
        # Vektorisasi: flag NG per baris, lalu groupby any() — lebih cepat dari lambda apply
        has_ng_flag = (df_prod["Judgement"] == "NG")
        return int(has_ng_flag.groupby([df_prod[c] for c in grp_cols]).any().sum())

    def render(self):
        # ─────────────────────────────────────────────────────────────
        # HEADER — real-time clock & auto-detect shift
        # ─────────────────────────────────────────────────────────────
        import time
        tz = pytz.timezone(TIMEZONE)
        now = datetime.now(tz)
        hour = now.hour
        current_shift = "1" if 7 <= hour < 16 else ("2" if hour >= 16 else "3")
        formatted_time = now.strftime("%d %b %Y")

        # Track last updated timestamp
        if "dash_last_updated" not in st.session_state:
            st.session_state["dash_last_updated"] = time.time()
        last_updated_str = datetime.fromtimestamp(
            st.session_state["dash_last_updated"], tz=tz
        ).strftime("%H:%M:%S")

        hcol1, hcol2 = st.columns([1, "auto"], gap="small") if hasattr(st, "_legacy") else st.columns([10, 1])
        with hcol1:
            st.markdown(f"""
            <div class="page-hdr" style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #E8ECF2;padding-bottom:12px;margin-bottom:4px;">
              <div>
                <span class="page-title" style="font-size:24px;font-weight:700;color:#0F172A;">Dashboard</span>
                <span class="page-sub" style="margin-left:10px;">Ringkasan kualitas produksi real-time</span>
              </div>
              <div style="font-size:13px;color:#64748B;font-weight:600;display:flex;align-items:center;gap:8px;background:#F8FAFC;padding:6px 16px;border-radius:20px;border:1px solid #E2E8F0;">
                <span style="display:inline-block;width:8px;height:8px;background-color:#22C55E;border-radius:50%;box-shadow:0 0 8px #22C55E;animation:blink 1.5s infinite;"></span>
                <span>{formatted_time} &nbsp;|&nbsp; Shift {current_shift} &nbsp;|&nbsp; Updated {last_updated_str}</span>
              </div>
            </div>
            <div class="section-desc" style="margin-bottom:16px;">Monitor OK rate · alert NG aktif · prediksi shift berikutnya · status mesin CMM secara langsung.</div>
            <style>@keyframes blink {{0%{{opacity:1}}50%{{opacity:0.3}}100%{{opacity:1}}}}</style>
            """, unsafe_allow_html=True)
        with hcol2:
            st.markdown
            if st.button("Refresh", key="dash_refresh", help="Refresh data"):
                # Clear semua cache
                st.cache_data.clear()
                for k in list(st.session_state.keys()):
                    if any(k.startswith(p) for p in ("xgb_cls_","nelson_")):
                        del st.session_state[k]
                st.session_state["dash_last_updated"] = time.time()
                st.rerun()

        # ─────────────────────────────────────────────────────────────
        # FILTERS — shared state dengan Descriptive
        # ─────────────────────────────────────────────────────────────
        filters = build_filters_dashboard(self.df_all, session_prefix="shared")

        self._render_main(filters)

    @st.fragment
    def _render_main(self, filters):
        # Target OK Line — baca dari settings, fallback 98.65
        try:
            from settings_config import get_target_ok as _gtk
            TARGET_OK_LINE = _gtk()
        except Exception:
            TARGET_OK_LINE = 98.65

        df_base = apply_filters(self.df_all, filters)
        f_part  = filters.get("part", "Semua Part")
        f_model = filters.get("model", "Semua Model")
        f_d1 = filters["d1"]
        f_d2 = filters["d2"]

        # ── Apply filter CMM dari filter utama ───────────────────
        _f_cmm = filters.get("cmm", "Semua Mesin")
        if _f_cmm and _f_cmm not in ("Semua Mesin", "All", "Semua", None, ""):
            df = df_base[df_base["CMMName"] == _f_cmm].copy()
        else:
            df = df_base.copy()
        svg_alert    = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#DC2626" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
        svg_shield   = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#16A34A" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>'


        # ── Alert NG Terdeteksi (aktual) — tampil duluan ─────────
        _ng_alerts = self._get_ng_alerts(df)
        if _ng_alerts:
            ng_slides_html = ""
            svg_cross_red = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#DC2626" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
            for i, _a in enumerate(_ng_alerts):
                is_kp  = _a["is_kp"]
                kp_tag = " &nbsp;<span style='font-size:9px;background:#DC2626;color:white;padding:1px 5px;border-radius:4px;'>KP</span>" if is_kp else ""

                dur_ng = len(_ng_alerts) * 12
                ng_slides_html += f"""
                <div class="ng-slide" style="animation-delay:{i * 12}s;animation-duration:{dur_ng}s;">
                  <div style="background:#FEF2F2;border-radius:8px;border:1px solid #FECACA;
                       padding:10px 14px;display:flex;align-items:center;gap:10px;">
                    <div style="width:30px;height:30px;background:#FEE2E2;border-radius:50%;
                         display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                      {svg_cross_red}
                    </div>
                    <div style="flex:1;min-width:0;">
                      <div style="font-size:12px;font-weight:700;color:#991B1B;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                        {_a['label']}{kp_tag}
                        <span style="font-size:10px;color:#94A3B8;font-weight:400;margin-left:6px;">{i+1}/{len(_ng_alerts)}</span>
                      </div>
                      <div style="font-size:11px;color:#DC2626;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                        NG · {_a['top_label']} · dev {_a['top_dev']}</div>
                      <div style="font-size:10px;color:#9A3412;margin-top:1px;">💡 {_a.get('saran','')}</div>
                    </div>
                    <span style="font-size:10px;font-weight:700;color:#DC2626;background:white;
                         padding:3px 10px;border-radius:99px;border:1px solid #FECACA;white-space:nowrap;flex-shrink:0;">
                      🔴 {_a['waktu']}</span>
                  </div>
                </div>"""

            total_ng = len(_ng_alerts)
            dur_ng   = total_ng * 12
            trans_ng = round(0.3 / dur_ng * 100, 2)
            stay_ng  = round(100 / total_ng - trans_ng * 2, 2)

            st.markdown(f"""
            <style>
            .ng-alert-bar {{ position:relative; height:72px; overflow:hidden; margin-bottom:6px; }}
            .ng-slide {{
                position:absolute; width:100%; top:0; left:0;
                opacity:0; animation:ngFade {dur_ng}s infinite;
            }}
            @keyframes ngFade {{
                0%              {{ opacity:0; }}
                {trans_ng}%        {{ opacity:1; }}
                {trans_ng+stay_ng}%   {{ opacity:1; }}
                {trans_ng*2+stay_ng}% {{ opacity:0; }}
                100%            {{ opacity:0; }}
            }}
            </style>
            <div class="ng-alert-bar">{ng_slides_html}</div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(
                '<div style="background:#F0FDF4;border-radius:8px;border:1px solid #BBF7D0;'
                'padding:10px 14px;display:flex;align-items:center;gap:10px;margin-bottom:6px;">'
                f'<div style="width:30px;height:30px;background:#DCFCE7;border-radius:50%;'
                f'display:flex;align-items:center;justify-content:center;flex-shrink:0;">'
                f'{svg_shield}</div>'
                '<span style="font-size:12px;font-weight:700;color:#14532D;">Semua OK — tidak ada NG tercatat</span>'
                '</div>',
                unsafe_allow_html=True
            )

        # ── Alert prediksi shift berikutnya ──────────────
        _f_cmm_alert = filters.get("cmm", "Semua Mesin")
        _alerts = self._get_prediction_alerts(
            filter_part  = f_part       if f_part  not in ("Semua Part","All","Semua Part",None,"") else None,
            filter_model = f_model      if f_model not in ("Semua Model","All","Semua Model",None,"") else None,
            filter_cmm   = _f_cmm_alert if _f_cmm_alert not in ("Semua Mesin","All","Semua",None,"") else None,
        )
        if _alerts:
            slides_html = ""
            for i, _a in enumerate(_alerts):
                _saran_pred = _get_saran(
                    _a.get('part',''), _a.get('model',''),
                    _a.get('top_ref_raw',''), _a.get('top_param','')
                )
                slides_html += f"""
                <div class="alert-slide" style="animation-delay:{i * 15}s;animation-duration:{len(_alerts) * 15}s;">
                  <div style="background:#FFF7ED;border-radius:8px;border:1px solid #FED7AA;
                       padding:10px 14px;display:flex;align-items:center;gap:10px;">
                    <div style="width:30px;height:30px;background:#FFEDD5;border-radius:50%;
                         display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#EA580C" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                    </div>
                    <div style="flex:1;min-width:0;">
                      <div style="font-size:12px;font-weight:700;color:#9A3412;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                        {_a.get('label', f"{_a['part']} · {_a['model']} — Shift {_a['shift']}")}
                        <span style="font-size:10px;color:#94A3B8;font-weight:400;margin-left:6px;">{i+1}/{len(_alerts)}</span>
                      </div>
                      <div style="font-size:11px;color:#EA580C;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                        Prediksi {_a['n_ng']} titik NG · {_a['top_ref']}</div>
                      <div style="font-size:10px;color:#92400E;margin-top:1px;">💡 {_saran_pred}</div>
                    </div>
                    <span style="font-size:10px;font-weight:700;color:#EA580C;background:white;
                         padding:3px 10px;border-radius:99px;border:1px solid #FED7AA;white-space:nowrap;flex-shrink:0;">
                      🟠 {_a['top_prob']:.0f}%</span>
                  </div>
                </div>"""

            total = len(_alerts)
            dur   = total * 15
            trans = round(0.3 / dur * 100, 2)
            stay  = round(100 / total - trans * 2, 2)

            st.markdown(f"""
            <style>
            .alert-carousel {{ position:relative; height:72px; overflow:hidden; margin-bottom:6px; }}
            .alert-slide {{
                position:absolute; width:100%; top:0; left:0;
                opacity:0; animation:alertFade {dur}s infinite;
            }}
            @keyframes alertFade {{
                0%              {{ opacity:0; }}
                {trans}%        {{ opacity:1; }}
                {trans+stay}%   {{ opacity:1; }}
                {trans*2+stay}% {{ opacity:0; }}
                100%            {{ opacity:0; }}
            }}
            </style>
            <div class="alert-carousel">{slides_html}</div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div style="background:#FFF7ED;border-radius:8px;border:1px solid #FED7AA;'
                f'padding:10px 14px;display:flex;align-items:center;gap:10px;margin-bottom:6px;">'
                f'<div style="width:30px;height:30px;background:#FFEDD5;border-radius:50%;'
                f'display:flex;align-items:center;justify-content:center;flex-shrink:0;">'
                f'<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#EA580C" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>'
                f'</div>'
                f'<span style="font-size:12px;font-weight:700;color:#9A3412;">'
                f'Prediksi aman — tidak ada risiko NG shift berikutnya</span>'
                f'</div>',
                unsafe_allow_html=True
            )

        # ── Alert Prediksi Rule SPC ───────────────────────────────
        # Non-blocking: kalau cache belum siap, return [] (jangan compute
        # di main thread; background warmup thread yang akan menyiapkannya).
        from utils.xgb_inference import get_rule_alerts
        _rule_alerts = get_rule_alerts(
            self.df_all,
            filter_part  = f_part  if f_part  not in ("Semua Part","All","Semua Part",None,"")  else None,
            filter_model = f_model if f_model not in ("Semua Model","All","Semua Model",None,"") else None,
            allow_compute=False,
        )

        if _rule_alerts:
            svg_rule = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#7C3AED" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>'
            rule_slides = ""
            for i, _r in enumerate(_rule_alerts):
                kp_tag = " &nbsp;<span style='font-size:9px;background:#7C3AED;color:white;padding:1px 5px;border-radius:4px;'>KP</span>" if _r["kp"] else ""
                rule_info = f" · ⚠ {_r['rule_list']}" if _r['rule_list'] else ""
                ng_info   = f" · NG dlm {_r['n_ng_pred']} shift" if _r['n_ng_pred'] > 0 else ""
                batas_info= f" · Batas ±{_r['est_batas']} shift" if _r['est_batas'] != '-' else ""
                dur_r = len(_rule_alerts) * 12
                rule_slides += f"""
                <div class="rule-slide" style="animation-delay:{i*12}s;animation-duration:{dur_r}s;">
                  <div style="background:#F5F3FF;border-radius:8px;border:1px solid #DDD6FE;
                       padding:10px 14px;display:flex;align-items:center;gap:10px;">
                    <div style="width:30px;height:30px;background:#EDE9FE;border-radius:50%;
                         display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                      {svg_rule}
                    </div>
                    <div style="flex:1;min-width:0;">
                      <div style="font-size:12px;font-weight:700;color:#4C1D95;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                        {_r['part']} {_r['model']} No.{_r['sno']}{kp_tag}
                        <span style="font-size:10px;color:#94A3B8;font-weight:400;margin-left:6px;">{i+1}/{len(_rule_alerts)}</span>
                      </div>
                      <div style="font-size:11px;color:#6D28D9;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                        {_r['ref']} · {_r['param']}{rule_info}{ng_info}{batas_info}</div>
                      <div style="font-size:10px;color:#7C3AED;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                        📐 {_r['tren']} · {(_r.get('rule_descs','')[:70] + '...' if len(_r.get('rule_descs','')) > 70 else _r.get('rule_descs','')) or _r['status']}</div>
                    </div>
                    <span style="font-size:10px;font-weight:700;color:#6D28D9;background:white;
                         padding:3px 10px;border-radius:99px;border:1px solid #DDD6FE;white-space:nowrap;flex-shrink:0;">
                      {_r['status']}</span>
                  </div>
                </div>"""

            total_r = len(_rule_alerts)
            dur_r   = total_r * 12
            trans_r = round(0.3 / dur_r * 100, 2)
            stay_r  = round(100 / total_r - trans_r * 2, 2)
            st.markdown(f"""
            <style>
            .rule-alert-bar {{ position:relative; height:72px; overflow:hidden; margin-bottom:6px; }}
            .rule-slide {{
                position:absolute; width:100%; top:0; left:0;
                opacity:0; animation:ruleFade {dur_r}s infinite;
            }}
            @keyframes ruleFade {{
                0%              {{ opacity:0; }}
                {trans_r}%        {{ opacity:1; }}
                {trans_r+stay_r}%   {{ opacity:1; }}
                {trans_r*2+stay_r}% {{ opacity:0; }}
                100%            {{ opacity:0; }}
            }}
            </style>
            <div class="rule-alert-bar">{rule_slides}</div>
            """, unsafe_allow_html=True)

        # ─────────────────────────────────────────────────────────────
        # ROW 1 — KPI CARDS (4 metrik utama)
        # ─────────────────────────────────────────────────────────────
        TOTAL_CHECKED = len(df)
        NG_COUNT = int((df["Judgement"] == "NG").sum())
        OK_COUNT = int((df["Judgement"] == "OK").sum())
        OK_RATIO = round(OK_COUNT / TOTAL_CHECKED * 100, 2) if TOTAL_CHECKED > 0 else 0.0
        total_part = self._count_parts(df)
        ng_parts   = self._count_ng_parts(df)

        c1, c2, c3, c4, c5 = st.columns(5, gap="medium")

        if float(OK_RATIO) >= TARGET_OK_LINE:
            _ok_clr, _ok_bg = "#15803D", "#F0FDF4"
        elif float(OK_RATIO) >= 80:
            _ok_clr, _ok_bg = "#D97706", "#FFFBEB"
        else:
            _ok_clr, _ok_bg = "#B91C1C", "#FEF2F2"
        _svg_pct = (f'<svg viewBox="0 0 24 24" fill="none" stroke="{_ok_clr}" stroke-width="2.5"'
                    f' stroke-linecap="round" stroke-linejoin="round">'
                    f'<line x1="19" y1="5" x2="5" y2="19"/>'
                    f'<circle cx="6.5" cy="6.5" r="2.5"/>'
                    f'<circle cx="17.5" cy="17.5" r="2.5"/></svg>')

        with c1:
            st.markdown(f'<div class="kpi-card"><div class="kpi-icon kpi-blue">{self.svg_check()}</div><div><div class="kpi-val">{TOTAL_CHECKED:,}</div><div class="kpi-lbl">Total Titik Diukur</div><div class="kpi-sub">Semua titik ukur</div></div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="kpi-card"><div class="kpi-icon kpi-blue" style="background:#F5F3FF;"><svg viewBox="0 0 24 24" fill="none" stroke="#7C3AED" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 3H8"/></svg></div><div><div class="kpi-val" style="color:#7C3AED;">{total_part:,}</div><div class="kpi-lbl">Total Part Diukur</div><div class="kpi-sub">Unik per siklus</div></div></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="kpi-card"><div class="kpi-icon kpi-red" style="background:#FEF2F2;"><svg viewBox="0 0 24 24" fill="none" stroke="#DC2626" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 3H8"/><line x1="9" y1="14" x2="15" y2="14"/></svg></div><div><div class="kpi-val kpi-val-red">{ng_parts:,}</div><div class="kpi-lbl">Part NG</div><div class="kpi-sub">dari {total_part:,} part</div></div></div>', unsafe_allow_html=True)
        with c4:
            st.markdown(
                f'<div class="kpi-card">'
                f'<div class="kpi-icon" style="background:{_ok_bg};">{_svg_pct}</div>'
                f'<div>'
                f'<div class="kpi-val" style="color:{_ok_clr};">{OK_RATIO}%</div>'
                f'<div class="kpi-lbl">Rata-rata Rasio OK</div>'
                f'<div class="kpi-sub">Target {TARGET_OK_LINE:.2f}%</div>'
                f'</div></div>',
                unsafe_allow_html=True
            )
        with c5:
            st.markdown(f'<div class="kpi-card"><div class="kpi-icon kpi-red">{self.svg_cross()}</div><div><div class="kpi-val kpi-val-red">{NG_COUNT:,}</div><div class="kpi-lbl">Total Titik NG</div><div class="kpi-sub">dari {TOTAL_CHECKED:,} titik</div></div></div>', unsafe_allow_html=True)
        st.markdown('<div class="row-gap"></div>', unsafe_allow_html=True)

        # ─────────────────────────────────────────────────────────────
        # ROW 2 — MACHINE STATUS CARDS (auto dari data)
        # ─────────────────────────────────────────────────────────────
        IDLE_WARN_MIN    = 10
        IDLE_OFFLINE_MIN = 30

        # Auto-detect mesin dari data, filter by part + filter CMM utama
        _cmm_df = self.df_all
        if f_part not in ("Semua Part", "All", "Semua Part", None, ""):
            _cmm_df = _cmm_df[_cmm_df["PartName"] == f_part]
        cmm_names = sorted(_cmm_df["CMMName"].dropna().unique().tolist())
        _sc = filters.get("cmm", "Semua Mesin")
        if _sc and _sc not in ("Semua Mesin", "All", "Semua", None, ""):
            cmm_names = [c for c in cmm_names if c == _sc]

        MACHINES = [{"cmm": c} for c in cmm_names]

        st.markdown(
            '<div style="font-size:14px;font-weight:700;color:#0F172A;'
            'margin-bottom:10px;">Status Mesin CMM</div>',
            unsafe_allow_html=True,
        )

        if not MACHINES:
            st.info("Tidak ada data mesin CMM untuk filter yang dipilih.")
            return

        mcols = st.columns(len(MACHINES), gap="medium")

        for mi, mach in enumerate(MACHINES):
            cmm_name  = mach["cmm"]

            # ── Ambil data dari df_all (bukan df yg sudah difilter)
            #    supaya status mesin selalu real, tidak terpengaruh filter tanggal
            df_cmm = self.df_all[self.df_all["CMMName"] == cmm_name].copy()

            if df_cmm.empty:
                # Mesin belum pernah ada data
                with mcols[mi]:
                    st.markdown(f"""
                    <div style="background:white;border-radius:8px;border:1px solid #E2E8F0;
                         padding:16px;box-shadow:0 1px 2px rgba(0,0,0,.05);">
                      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                        <span style="font-size:14px;font-weight:700;color:#0F172A;">{cmm_name}</span>
                        <span style="font-size:10px;font-weight:700;color:#94A3B8;
                              background:#F1F5F9;padding:3px 10px;border-radius:10px;">NO DATA</span>
                      </div>
                      <div style="font-size:11px;color:#94A3B8;">Belum ada data masuk dari mesin ini.</div>
                    </div>
                    """, unsafe_allow_html=True)
                continue

            # ── Last row dari mesin ini ──────────────────────────────
            last_row  = df_cmm.sort_values("Date").iloc[-1]
            last_time = pd.to_datetime(last_row["Date"])
            last_str  = last_time.strftime("%d %b · %H:%M")

            # Selisih menit dari sekarang
            tz_aware  = last_time.tz_localize(None) if last_time.tzinfo else last_time
            diff_min  = (datetime.now() - tz_aware).total_seconds() / 60

            if diff_min <= IDLE_WARN_MIN:
                st_color, st_bg, st_dot, st_text = "#16A34A","#DCFCE7","#22C55E","ACTIVE"
            elif diff_min <= IDLE_OFFLINE_MIN:
                st_color, st_bg, st_dot, st_text = "#D97706","#FEF3C7","#F59E0B","IDLE"
            else:
                st_color, st_bg, st_dot, st_text = "#64748B","#F1F5F9","#94A3B8","OFFLINE"

            last_sample  = str(last_row.get("SampleNo", "-"))
            last_part    = str(last_row.get("PartName", "-"))
            last_model   = str(last_row.get("ModelName", "-"))
            last_judgement = str(last_row.get("Judgement", "-"))
            j_color      = "#16A34A" if last_judgement == "OK" else "#DC2626"
            j_bg         = "#DCFCE7" if last_judgement == "OK" else "#FEE2E2"

            # ── Statistik dari df yang sudah difilter ────────────────
            df_stat_cmm  = df[df["CMMName"] == cmm_name]
            stat_total   = len(df_stat_cmm)
            shift_ok     = int((df_stat_cmm["Judgement"] == "OK").sum()) if stat_total > 0 else 0
            shift_ng     = int((df_stat_cmm["Judgement"] == "NG").sum()) if stat_total > 0 else 0
            shift_ok_pct = round(shift_ok / stat_total * 100, 1) if stat_total > 0 else 0.0
            parts_ukur   = self._count_parts(df_stat_cmm)
            parts_ng_cmm = self._count_ng_parts(df_stat_cmm)

            # KP NG
            kp_ng_str = ""
            if "KP" in df_stat_cmm.columns and stat_total > 0:
                kp_ng = int(((df_stat_cmm["KP"] == 1) & (df_stat_cmm["Judgement"] == "NG")).sum())
                if kp_ng > 0:
                    kp_ng_str = (
                        f'<div style="margin-top:6px;padding:5px 10px;background:#FEE2E2;'
                        f'border-radius:6px;display:flex;justify-content:space-between;">'
                        f'<span style="font-size:11px;font-weight:700;color:#991B1B;">⚠ KP Critical NG</span>'
                        f'<span style="font-size:12px;font-weight:800;color:#DC2626;">{kp_ng}</span>'
                        f'</div>'
                    )

            # ── Idle duration label ──────────────────────────────────
            if diff_min < 1:
                idle_str = "Baru saja"
            elif diff_min < 60:
                idle_str = f"{int(diff_min)} menit lalu"
            else:
                idle_str = f"{int(diff_min // 60)} jam {int(diff_min % 60)} mnt lalu"

            with mcols[mi]:
                st.markdown(f"""
                <div style="background:white;border-radius:10px;border:1px solid #E2E8F0;
                     padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06);">

                  <!-- Header: nama mesin + badge status -->
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                    <div style="display:flex;align-items:center;gap:7px;">
                      <span style="width:8px;height:8px;border-radius:50%;background:{st_dot};
                            box-shadow:0 0 5px {st_dot};display:inline-block;flex-shrink:0;"></span>
                      <span style="font-size:13px;font-weight:700;color:#0F172A;white-space:nowrap;
                            overflow:hidden;text-overflow:ellipsis;max-width:120px;">{cmm_name}</span>
                    </div>
                    <span style="font-size:9.5px;font-weight:700;color:{st_color};
                          background:{st_bg};padding:2px 9px;border-radius:20px;
                          border:1px solid {st_dot}33;white-space:nowrap;">{st_text}</span>
                  </div>

                  <!-- Last measurement block -->
                  <div style="background:#F8FAFC;border-radius:7px;padding:8px 10px;margin-bottom:10px;">
                    <div style="font-size:9px;color:#94A3B8;font-weight:700;text-transform:uppercase;
                         letter-spacing:.5px;margin-bottom:4px;">LAST MEASUREMENT</div>
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px;">
                      <div style="flex:1;min-width:0;">
                        <div style="font-size:12px;font-weight:700;color:#0F172A;
                             white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                          {last_part} &ndash; {last_sample}
                        </div>
                        <div style="font-size:10px;color:#64748B;margin-top:2px;">{last_str} &nbsp;&middot;&nbsp; {idle_str}</div>
                      </div>
                      <span style="font-size:11px;font-weight:800;color:{j_color};
                            background:{j_bg};padding:3px 9px;border-radius:6px;
                            white-space:nowrap;flex-shrink:0;">{last_judgement}</span>
                    </div>
                  </div>

                  <!-- Stats: 2 baris × 2 kolom + OK Rate full width -->
                  <div style="font-size:9px;color:#94A3B8;font-weight:700;text-transform:uppercase;
                       letter-spacing:.5px;margin-bottom:6px;">PERIODE FILTER</div>

                  <!-- OK Rate — full width -->
                  <div style="background:#F0FDF4;border-radius:7px;padding:8px 12px;
                       display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <span style="font-size:11px;font-weight:600;color:#166534;">OK Rate</span>
                    <span style="font-size:18px;font-weight:800;
                          color:{'#16A34A' if shift_ok_pct >= 98 else ('#D97706' if shift_ok_pct >= 80 else '#DC2626')};">{shift_ok_pct}%</span>
                  </div>

                  <!-- 2×2 grid: Parts | Parts NG | OK Pts | NG Pts -->
                  <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;">
                    <div style="background:#EFF6FF;border-radius:7px;padding:7px 10px;">
                      <div style="font-size:16px;font-weight:800;color:#1D4ED8;">{parts_ukur:,}</div>
                      <div style="font-size:9.5px;color:#3B82F6;font-weight:600;margin-top:1px;">Parts Diukur</div>
                    </div>
                    <div style="background:#FEF2F2;border-radius:7px;padding:7px 10px;">
                      <div style="font-size:16px;font-weight:800;color:#DC2626;">{parts_ng_cmm:,}</div>
                      <div style="font-size:9.5px;color:#EF4444;font-weight:600;margin-top:1px;">Parts NG</div>
                    </div>
                    <div style="background:#F0FDF4;border-radius:7px;padding:7px 10px;">
                      <div style="font-size:16px;font-weight:800;color:#16A34A;">{shift_ok:,}</div>
                      <div style="font-size:9.5px;color:#22C55E;font-weight:600;margin-top:1px;">OK Pts</div>
                    </div>
                    <div style="background:#FEF2F2;border-radius:7px;padding:7px 10px;">
                      <div style="font-size:16px;font-weight:800;color:#DC2626;">{shift_ng:,}</div>
                      <div style="font-size:9.5px;color:#EF4444;font-weight:600;margin-top:1px;">NG Pts</div>
                    </div>
                  </div>

                  {kp_ng_str}
                </div>
                """, unsafe_allow_html=True)


        # ─────────────────────────────────────────────────────────────
        # ROW 3 — STATUS KUALITAS PER PART (auto + target pemantauan)
        # ─────────────────────────────────────────────────────────────
        # Target sample per shift per model — tambahkan model baru di sini
        # Target sample — (part, model, shift): angka
        # Shift "0" = default kalau shift tidak ditemukan
        # Sample targets dari settings.json
        try:
            from settings_config import get_sample_target as _gst
        except Exception:
            _gst = None

        def _get_target(part, model, shift):
            """Ambil target sample dari settings_config, fallback 0."""
            if _gst:
                return _gst(part, model, str(shift))
            return 0

        # Hitung dynamic target per model dengan mempertimbangkan target per shift
        def _dynamic_target(part, model, df_filtered):
            if df_filtered.empty:
                return 0
            total = 0
            for (date, shift), _ in df_filtered.groupby([df_filtered["Date"].dt.date, "Shift"]):
                total += _get_target(part, model, shift)
            return total

        st.markdown('<div style="font-size:14px;font-weight:700;color:#0F172A;margin-top:4px;margin-bottom:10px;">Status Kualitas per Part</div>', unsafe_allow_html=True)

        # Daftar part selalu dari df_all — supaya part tanpa data hari ini tetap muncul
        _df_src = self.df_all
        if f_part  not in ("Semua Part",  "All", "Semua Part",  None, ""):
            _df_src = _df_src[_df_src["PartName"]  == f_part]
        if f_model not in ("Semua Model", "All", "Semua Model", None, ""):
            _df_src = _df_src[_df_src["ModelName"] == f_model]
        parts_in_data = sorted(_df_src["PartName"].dropna().unique().tolist())

        if not parts_in_data:
            st.markdown(
                '<div style="background:#F8FAFC;border-radius:8px;border:1px solid #E2E8F0;'
                'padding:16px;text-align:center;color:#94A3B8;font-size:13px;">'
                '📭 Belum ada data part yang terdaftar.</div>',
                unsafe_allow_html=True,
            )
        else:
            for part in parts_in_data:
                df_part = df[df["PartName"] == part]
                # Fallback ke df_all tapi TETAP ikuti f_model
                _df_part_all = self.df_all[self.df_all["PartName"] == part]
                if f_model not in ("Semua Model", "All", "Semua Model", None, ""):
                    _df_part_all = _df_part_all[_df_part_all["ModelName"] == f_model]
                # Selalu dari df_all — model tanpa data hari ini tetap muncul
                models = sorted(_df_part_all["ModelName"].dropna().unique().tolist())
                if not models:
                    continue

                # Header part
                st.markdown(
                    f'<div style="font-size:12px;font-weight:700;color:#475569;'
                    f'text-transform:uppercase;letter-spacing:.5px;'
                    f'margin:10px 0 6px;">{part}</div>',
                    unsafe_allow_html=True
                )

                cols = st.columns(len(models), gap="small")
                for ci, model in enumerate(models):
                    df_m   = df_part[df_part["ModelName"] == model]
                    tot    = len(df_m)
                    ok     = int((df_m["Judgement"] == "OK").sum())
                    ng     = int((df_m["Judgement"] == "NG").sum())
                    pct    = round(ok / tot * 100, 2) if tot else 0.0
                    ng_parts_m = self._count_ng_parts(df_m)

                    # KP NG
                    kp_ng = int(((df_m.get("KP", pd.Series(0, index=df_m.index)) == 1) &
                                 (df_m["Judgement"] == "NG")).sum()) if tot > 0 else 0

                    # Target pemantauan per shift
                    dynamic_target = _dynamic_target(part, model, df_m)
                    # Kalau df_m kosong, hitung target dari shift filter/aktif
                    if dynamic_target == 0:
                        _f_sh = filters.get("shift", "Semua Shift")
                        if str(_f_sh) not in ("Semua Shift", "All", "", "None"):
                            _tgt_sh = str(_f_sh)
                        else:
                            _h = datetime.now(pytz.timezone(TIMEZONE)).hour
                            _tgt_sh = "1" if 7 <= _h < 16 else ("2" if _h >= 16 else "3")
                        dynamic_target = _get_target(part, model, _tgt_sh)
                        if dynamic_target == 0:
                            dynamic_target = _get_target(part, model, "0")
                    actual_parts   = self._count_parts(df_m)
                    target_pct     = min(int(actual_parts / dynamic_target * 100), 100) if dynamic_target > 0 else 0

                    if dynamic_target > 0:
                        if target_pct < 50:   t_clr = "#EF4444"
                        elif target_pct < 100: t_clr = "#F59E0B"
                        else:                  t_clr = "#10B981"
                        target_html = f"""
                        <div style="margin-top:10px;padding-top:10px;border-top:1px solid #F1F5F9;">
                          <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                            <span style="font-size:10px;color:#64748B;font-weight:600;">Pemantauan</span>
                            <span style="font-size:10px;font-weight:700;color:{t_clr};">{actual_parts}/{dynamic_target}</span>
                          </div>
                          <div style="background:#F1F5F9;border-radius:999px;height:5px;overflow:hidden;">
                            <div style="background:{t_clr};width:{target_pct}%;height:100%;border-radius:999px;"></div>
                          </div>
                          <div style="text-align:right;margin-top:2px;">
                            <span style="font-size:9px;color:#94A3B8;">{target_pct}% tercapai</span>
                          </div>
                        </div>"""
                    else:
                        target_html = ""

                    # Status badge
                    if tot == 0:
                        status_color, status_bg, status_text, ratio_color = "#94A3B8","#F1F5F9","No Data","#94A3B8"
                    elif pct >= TARGET_OK_LINE:
                        status_color, status_bg, status_text, ratio_color = "#16A34A","#DCFCE7","Healthy","#16A34A"
                    elif pct >= 80:
                        status_color, status_bg, status_text, ratio_color = "#D97706","#FEF3C7","Watch","#D97706"
                    else:
                        status_color, status_bg, status_text, ratio_color = "#DC2626","#FEE2E2","Critical","#DC2626"

                    kp_badge = f'<span style="font-size:9px;font-weight:700;color:#991B1B;background:#FEE2E2;padding:1px 6px;border-radius:8px;margin-left:4px;">KP {kp_ng}</span>' if kp_ng > 0 else ""

                    with cols[ci]:
                        st.markdown(f"""
                        <div style="background:white;border-radius:8px;border:1px solid #E2E8F0;
                             box-shadow:0 1px 2px rgba(0,0,0,0.05);padding:14px;
                             min-height:180px;display:flex;flex-direction:column;justify-content:space-between;">
                          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                            <div style="font-size:13px;font-weight:700;color:#0F172A;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:60%;">{model}{kp_badge}</div>
                            <span style="font-size:10px;font-weight:700;color:{status_color};background:{status_bg};
                                  padding:3px 8px;border-radius:10px;white-space:nowrap;flex-shrink:0;">{status_text}</span>
                          </div>
                          <div style="display:flex;align-items:baseline;gap:6px;margin-bottom:8px;">
                            <span style="font-size:28px;font-weight:800;color:{ratio_color};line-height:1;">{pct}%</span>
                            <span style="font-size:11px;color:#64748B;font-weight:600;">OK Ratio</span>
                          </div>
                          <div style="display:flex;gap:12px;padding-top:8px;border-top:1px solid #F1F5F9;flex:1;align-items:flex-end;">
                            <div style="min-width:0;">
                              <div style="font-size:13px;font-weight:700;color:#22C55E;white-space:nowrap;">{ok:,}</div>
                              <div style="font-size:9px;color:#64748B;font-weight:600;white-space:nowrap;">OK</div>
                            </div>
                            <div style="min-width:0;">
                              <div style="font-size:13px;font-weight:700;color:#EF4444;white-space:nowrap;">{ng:,}</div>
                              <div style="font-size:9px;color:#64748B;font-weight:600;white-space:nowrap;">NG</div>
                            </div>
                            <div style="min-width:0;">
                              <div style="font-size:13px;font-weight:700;color:#0F172A;white-space:nowrap;">{tot:,}</div>
                              <div style="font-size:9px;color:#64748B;font-weight:600;white-space:nowrap;">Total</div>
                            </div>
                            <div style="margin-left:auto;text-align:right;min-width:0;flex-shrink:0;">
                              <div style="font-size:13px;font-weight:700;color:#DC2626;white-space:nowrap;">{ng_parts_m:,}</div>
                              <div style="font-size:9px;color:#64748B;font-weight:600;white-space:nowrap;">Parts NG</div>
                            </div>
                          </div>
                          {target_html}
                        </div>
                        """, unsafe_allow_html=True)
        st.markdown('<div class="row-gap"></div>', unsafe_allow_html=True)

        # ── KPI per SampleNo (muncul kalau filter Part dipilih) ──────
        if f_part not in ("Semua Part", "All", "Semua Part", None, ""):

            _sec_title = (f"{f_part} · {f_model}"
                          if f_model not in ("Semua Model", "All", "Semua Model", None, "")
                          else f_part)
            # ── Kualitas per Sample ───────────────────────────────────
            st.markdown(
                f'<div style="font-size:14px;font-weight:700;color:#0F172A;'
                f'margin-bottom:10px;">Kualitas per Sample — {_sec_title}</div>',
                unsafe_allow_html=True
            )
            # Ikuti filter Part + Model — fallback ke df_all kalau df kosong
            _df_sno_src = df if not df.empty else self.df_all
            if f_part not in ("Semua Part", "All", "Semua Part", None, ""):
                _df_sno_src = _df_sno_src[_df_sno_src["PartName"] == f_part]
            if f_model not in ("Semua Model", "All", "Semua Model", None, ""):
                _df_sno_src = _df_sno_src[_df_sno_src["ModelName"] == f_model]
            raw_samples = _df_sno_src["SampleNo"].dropna().astype(str).unique().tolist()
            def _sno_key(s):
                try: return (0, int(s))
                except ValueError: return (1, s)
            samples = sorted(raw_samples, key=_sno_key)

            if samples:
                cards_html = ""
                for sno in samples:
                    df_s = df[df["SampleNo"].astype(str) == sno]
                    tot  = len(df_s)
                    ok   = int((df_s["Judgement"] == "OK").sum())
                    ng   = int((df_s["Judgement"] == "NG").sum())
                    pct  = round(ok / tot * 100, 1) if tot else 0.0
                    # Total Part & Parts NG per sample
                    tot_part  = self._count_parts(df_s)   if hasattr(self, "_count_parts")   else df_s["PartName"].nunique()
                    part_ng_s = self._count_ng_parts(df_s) if hasattr(self, "_count_ng_parts") else 0
                    if pct >= TARGET_OK_LINE:   clr = "#16A34A"
                    elif pct >= 80: clr = "#D97706"
                    else:           clr = "#DC2626"
                    cards_html += f"""
                    <div style="background:white;border-radius:8px;
                         border:1px solid #E2E8F0;border-top:3px solid {clr};
                         padding:12px;text-align:center;">
                      <div style="font-size:13px;font-weight:700;color:#0F172A;margin-bottom:6px;">{sno}</div>
                      <div style="font-size:22px;font-weight:800;color:{clr};line-height:1;">{pct}%</div>
                      <div style="font-size:10px;color:#64748B;margin:4px 0 6px;">OK Ratio</div>
                      <div style="height:4px;background:#F1F5F9;border-radius:99px;overflow:hidden;margin-bottom:8px;">
                        <div style="width:{pct}%;height:100%;background:{clr};border-radius:99px;"></div>
                      </div>
                      <div style="display:flex;justify-content:center;gap:10px;margin-bottom:6px;">
                        <span style="font-size:11px;color:#22C55E;font-weight:700;">{ok} OK</span>
                        <span style="font-size:11px;color:#EF4444;font-weight:700;">{ng} NG</span>
                      </div>
                      <div style="display:flex;justify-content:center;gap:8px;padding-top:6px;border-top:1px solid #F1F5F9;">
                        <div style="text-align:center;">
                          <div style="font-size:12px;font-weight:700;color:#0F172A;">{tot_part}</div>
                          <div style="font-size:8px;color:#64748B;font-weight:600;">Total Part</div>
                        </div>
                        <div style="width:1px;background:#E2E8F0;"></div>
                        <div style="text-align:center;">
                          <div style="font-size:12px;font-weight:700;color:#DC2626;">{part_ng_s}</div>
                          <div style="font-size:8px;color:#64748B;font-weight:600;">Part NG</div>
                        </div>
                      </div>
                    </div>"""
                st.markdown(
                    f'<div style="display:grid;grid-template-columns:repeat(6,1fr);'
                    f'gap:8px;margin-bottom:16px;">{cards_html}</div>',
                    unsafe_allow_html=True
                )

        # ─────────────────────────────────────────────────────────────
        # ROW 5 — QUALITY TREND (Dinamis)
        #   • 1 hari  → 2 chart berdampingan, X = SampleNo per part
        #   • > 1 hari → 1 chart gabungan, X = "dd MMM · S{shift}"
        # ─────────────────────────────────────────────────────────────
        st.markdown('<div class="row-gap"></div>', unsafe_allow_html=True)

        TARGET_PARTS = [
            {"part": p, "model": m, "color_ok": "#22C55E", "color_ng": "#EF4444"}
            for p, m in (df[["PartName","ModelName"]]
                         .drop_duplicates()
                         .sort_values(["PartName","ModelName"])
                         .itertuples(index=False, name=None))
        ] if not df.empty else []


        # ── Helper: hitung trend_df dari df + kolom X_Axis ──────────
        def _build_trend_df(d: pd.DataFrame) -> pd.DataFrame:
            grp = d.groupby("X_Axis", sort=False)
            ok_s = grp.apply(lambda x: (x["Judgement"] == "OK").sum()).rename("OK")
            ng_s = grp.apply(lambda x: (x["Judgement"] == "NG").sum()).rename("NG")
            t = pd.concat([ok_s, ng_s], axis=1).reset_index()
            t["Total"]  = t["OK"] + t["NG"]
            t["OK_Pct"] = (t["OK"] / t["Total"] * 100).round(2).fillna(0)
            t["NG_Pct"] = (t["NG"] / t["Total"] * 100).round(2).fillna(0)

            # Hitung jumlah part fisik OK / NG per X_Axis
            part_total = grp.apply(
                lambda g: g.groupby([g["Date"].dt.date, "Shift", "Cycle", "SampleNo"]).ngroups
            ).rename("TotalPart").reset_index()
            part_ok = grp.apply(
                lambda g: g.groupby([g["Date"].dt.date, "Shift", "Cycle", "SampleNo"])
                           .apply(lambda p: (p["Judgement"] == "OK").all()).sum()
            ).rename("PartOK").reset_index()
            t = t.merge(part_total, on="X_Axis", how="left")
            t = t.merge(part_ok,    on="X_Axis", how="left")
            t["PartNG"] = t["TotalPart"] - t["PartOK"]
            return t

        # ── Helper: konversi trend_df ke list dict untuk echarts ────
        def _to_series_data(t: pd.DataFrame, pct_col: str) -> list:
            return [
                {"value": row[pct_col], "ok_pt": row["OK"], "ng_pt": row["NG"],
                 "total_pt": row["Total"], "part_total": row["TotalPart"],
                 "part_ok": row["PartOK"], "part_ng": row["PartNG"]}
                for _, row in t.iterrows()
            ]

        # ── Tooltip JS (reusable) ────────────────────────────────────
        tooltip_js = JsCode("""
        function(params) {
            if (!params || params.length === 0) return '';
            var d = params[0].data;
            if (!d || typeof d !== 'object') return params[0].axisValue;
            var html = '<div style="font-family:Inter;line-height:1.8;min-width:230px">'
                     + '<b>' + params[0].axisValue + '</b><br/>';
            params.forEach(function(p) {
                var pd = p.data;
                if (!pd || typeof pd !== 'object') return;
                html += p.marker + ' <b>' + p.seriesName + '</b>: ' + pd.value + '%'
                      + ' &nbsp;|&nbsp; '
                      + 'Point: ' + pd.ok_pt + ' OK / ' + pd.ng_pt + ' NG'
                      + ' &nbsp;(' + pd.total_pt + ' total)<br/>';
            });
            html += '</div>';
            return html;
        }
        """)

        # ── CABANG UTAMA ─────────────────────────────────────────────
        delta_days = (f_d2 - f_d1).days

        # ── Toggle mode tren ────────────────────────────────────────
        part_selected = f_part not in ("Semua Part", "All", "Semua Part", None, "")

        if part_selected:
            trend_opts = ["Gabungan", "Per SampleNo"]
        else:
            trend_opts = ["Gabungan", "Per Part & Model"]

        # Reset pill kalau opsinya berubah
        if st.session_state.get("dash_trend_mode") not in trend_opts:
            st.session_state["dash_trend_mode"] = "Gabungan"

        trend_mode = st.pills(
            "Mode tren", trend_opts,
            default="Gabungan",
            key="dash_trend_mode",
            selection_mode="single",
            label_visibility="collapsed",
        ) or "Gabungan"

        PALETTE = [
            "#6366f1","#0ea5e9","#10b981","#f59e0b","#ef4444",
            "#8b5cf6","#ec4899","#14b8a6","#f97316","#84cc16",
        ]

        df_trend = df.copy()  # CMM sudah terfilter dari filter bar

        if delta_days == 0:
            # ════════════════════════════════════════════════════
            # MODE 1 — 1 HARI: X = Shift, konteks 3 shift terakhir
            # ════════════════════════════════════════════════════
            # Ambil 3 shift terakhir dari df_all (tidak terfilter tanggal)
            df_ctx = self.df_all.copy().sort_values("Date")
            df_ctx["_shift_key"] = (
                df_ctx["Date"].dt.strftime("%d %b") + " · S" + df_ctx["Shift"].astype(str)
            )
            # Ambil 3 shift terakhir berdasarkan waktu SEKARANG
            try:
                import pytz as _pytz
                _tz = _pytz.timezone("Asia/Jakarta")
                _now = pd.Timestamp.now(tz=_tz)
            except Exception:
                _now = pd.Timestamp.now()

            # Samakan timezone dengan kolom Date di df_ctx
            _date_col = df_ctx["Date"]
            if hasattr(_date_col.dtype, "tz") and _date_col.dtype.tz is not None:
                # df punya timezone — pastikan _now juga timezone-aware
                if _now.tzinfo is None:
                    _now = _now.tz_localize("Asia/Jakarta")
            else:
                # df timezone-naive — strip timezone dari _now
                if _now.tzinfo is not None:
                    _now = _now.tz_localize(None)

            # Hanya shift yang sudah ada data sampai sekarang
            _past = df_ctx[df_ctx["Date"] <= _now].copy()
            if _past.empty:
                _past = df_ctx.copy()

            _key_min = _past.groupby("_shift_key")["Date"].min().reset_index()
            _key_min.columns = ["_shift_key", "_min_date"]
            _key_min = _key_min.sort_values("_min_date")
            ctx_keys = _key_min["_shift_key"].tail(3).tolist()

            # Build df untuk chart — dari df_all, filter ke ctx_keys + filter part/model
            df_ctx2 = df_ctx[df_ctx["_shift_key"].isin(ctx_keys)].copy()
            if f_part not in ("Semua Part", "All", "Semua Part", None, ""):
                df_ctx2 = df_ctx2[df_ctx2["PartName"] == f_part]
            if f_model not in ("Semua Model", "All", "Semua Model", None, ""):
                df_ctx2 = df_ctx2[df_ctx2["ModelName"] == f_model]

            if df_trend.empty or df_ctx2.empty:
                st.info("Belum ada data untuk periode yang dipilih.")
            else:
                if trend_mode in ("Per SampleNo", "Per Part & Model"):
                    # ── Per SampleNo atau Per Part·Model ──────────────
                    if part_selected and trend_mode == "Per SampleNo":
                        # Filter ke part yang dipilih
                        df_ctx2_f = df_ctx2[df_ctx2["PartName"] == f_part].copy() if f_part not in ("Semua Part","") else df_ctx2.copy()
                        raw_sno   = df_ctx2_f["SampleNo"].astype(str).unique().tolist()
                        sno_order = sorted(raw_sno, key=lambda s: (0,int(s)) if s.isdigit() else (1,s))
                        series_list, legend_list = [], []
                        for si, sno in enumerate(sno_order):
                            df_s = df_ctx2_f[df_ctx2_f["SampleNo"].astype(str)==sno]
                            pts  = []
                            for sk in ctx_keys:
                                sub = df_s[df_s["_shift_key"]==sk]
                                if sub.empty:
                                    pts.append(None)
                                else:
                                    ok=int((sub["Judgement"]=="OK").sum()); tot=len(sub)
                                    pts.append({"value":round(ok/tot*100,1),"ok_pt":ok,"ng_pt":tot-ok,"total_pt":tot})
                            clr = PALETTE[si%len(PALETTE)]
                            legend_list.append(str(sno))
                            series_list.append({
                                "name":str(sno),"type":"bar","data":pts,
                                "itemStyle":{"color":clr,"borderRadius":[4,4,0,0]},
                                "label":{"show":True,"position":"top",
                                         "formatter":f"{str(sno)}","fontSize":9,"color":clr},
                            })
                        title_text = f"Trend — {f_part}"
                        subtext    = "OK% per SampleNo · X = Shift"
                    else:
                        # Per Part & Model
                        combos = (df_ctx2[["PartName","ModelName"]]
                                  .drop_duplicates()
                                  .sort_values(["PartName","ModelName"])
                                  .itertuples(index=False,name=None))
                        series_list, legend_list = [], []
                        for si,(pn,mn) in enumerate(combos):
                            label = f"{pn} · {mn}"
                            df_pm = df_ctx2[(df_ctx2["PartName"]==pn)&(df_ctx2["ModelName"]==mn)]
                            pts   = []
                            for sk in ctx_keys:
                                sub = df_pm[df_pm["_shift_key"]==sk]
                                if sub.empty:
                                    pts.append(None)
                                else:
                                    ok=int((sub["Judgement"]=="OK").sum()); tot=len(sub)
                                    pts.append({"value":round(ok/tot*100,1),"ok_pt":ok,"ng_pt":tot-ok,"total_pt":tot})
                            clr = PALETTE[si%len(PALETTE)]
                            legend_list.append(label)
                            series_list.append({
                                "name":label,"type":"bar","data":pts,
                                "itemStyle":{"color":clr,"borderRadius":[4,4,0,0]},
                                "label":{"show":True,"position":"top",
                                         "formatter":label,"fontSize":8,"color":clr},
                            })
                        title_text = "Quality Trend — All Parts"
                        subtext    = "OK% per Part · Model"

                    if series_list:
                        series_list[0]["markLine"] = {
                            "silent":True,
                            "lineStyle":{"color":"#94A3B8","type":"dashed","width":1},
                            "label":{"formatter":f"Target {TARGET_OK_LINE}%","position":"end","fontSize":10,"color":"#64748B"},
                            "data":[{"yAxis":TARGET_OK_LINE}],
                        }
                    st_echarts({
                        "title":{"text":title_text,"subtext":subtext,
                                 "left":16,"top":8,
                                 "textStyle":{"color":"#0F172A","fontSize":13,"fontWeight":700,"fontFamily":"Inter"},
                                 "subtextStyle":{"color":"#94A3B8","fontSize":10}},
                        "grid":{"top":50,"right":20,"bottom":55,"left":42},
                        "tooltip":{"trigger":"axis","backgroundColor":"#1E293B","borderColor":"#334155",
                                   "textStyle":{"color":"#F8FAFC","fontSize":12},"formatter":tooltip_js},
                        "xAxis":{"type":"category","data":ctx_keys,
                                 "axisLine":{"lineStyle":{"color":"#E2E8F0"}},
                                 "axisTick":{"show":False},
                                 "axisLabel":{"color":"#94A3B8","fontSize":10,"interval":0,"rotate":15},
                                 "splitLine":{"show":False}},
                        "yAxis":{"type":"value","min":0,"max":100,
                                 "axisLine":{"show":False},"axisTick":{"show":False},
                                 "axisLabel":{"color":"#94A3B8","fontSize":10,"formatter":"{value}%"},
                                 "splitLine":{"lineStyle":{"color":"#F1F5F9","type":"dashed"}}},
                        "series":series_list,
                        "dataZoom":[{"type":"inside","start":0,"end":100},
                                    {"type":"slider","bottom":5,"height":18}],
                        "toolbox":{"feature":{"magicType":{"type":["line","bar"],"right":16,"top":10}}},
                    }, height="320px", key="trend_chart_1d")

                else:
                    # ── Gabungan: 1 line OK%, X = Shift ──────────────
                    pts_ok = []
                    for sk in ctx_keys:
                        sub = df_ctx2[df_ctx2["_shift_key"]==sk]
                        if sub.empty:
                            pts_ok.append(None)
                        else:
                            ok=int((sub["Judgement"]=="OK").sum()); tot=len(sub)
                            pts_ok.append({"value":round(ok/tot*100,1),"ok_pt":ok,"ng_pt":tot-ok,"total_pt":tot})
                    pts_ng = []
                    for sk in ctx_keys:
                        sub = df_ctx2[df_ctx2["_shift_key"]==sk]
                        if sub.empty:
                            pts_ng.append(None)
                        else:
                            ok=int((sub["Judgement"]=="OK").sum()); tot=len(sub)
                            pts_ng.append({"value":round((tot-ok)/tot*100,1),"ok_pt":ok,"ng_pt":tot-ok,"total_pt":tot})
                    st_echarts({
                        "title":{"text":"Quality Trend","subtext":"OK% gabungan · X = Shift (3 terakhir)",
                                 "left":16,"top":8,
                                 "textStyle":{"color":"#0F172A","fontSize":13,"fontWeight":700,"fontFamily":"Inter"},
                                 "subtextStyle":{"color":"#94A3B8","fontSize":10}},
                        "legend":{"data":["OK %","NG %"],"right":16,"top":12,
                                  "icon":"circle","itemWidth":8,
                                  "textStyle":{"color":"#64748B","fontSize":11}},
                        "grid":{"top":60,"right":20,"bottom":55,"left":42},
                        "tooltip":{"trigger":"axis","backgroundColor":"#1E293B","borderColor":"#334155",
                                   "textStyle":{"color":"#F8FAFC","fontSize":12},"formatter":tooltip_js},
                        "xAxis":{"type":"category","data":ctx_keys,
                                 "axisLine":{"lineStyle":{"color":"#E2E8F0"}},
                                 "axisTick":{"show":False},
                                 "axisLabel":{"color":"#94A3B8","fontSize":10,"interval":0,"rotate":15},
                                 "splitLine":{"show":False}},
                        "yAxis":{"type":"value","min":0,"max":100,
                                 "axisLine":{"show":False},"axisTick":{"show":False},
                                 "axisLabel":{"color":"#94A3B8","fontSize":10,"formatter":"{value}%"},
                                 "splitLine":{"lineStyle":{"color":"#F1F5F9","type":"dashed"}}},
                        "series":[
                            {"name":"OK %","type":"line","data":pts_ok,
                             "connectNulls":False,"smooth":True,
                             "symbol":"circle","symbolSize":7,
                             "lineStyle":{"color":"#22C55E","width":2.5},
                             "itemStyle":{"color":"#22C55E"},
                             "areaStyle":{"color":"#22C55E","opacity":0.08},
                             "markLine":{"silent":True,
                                         "lineStyle":{"color":"#94A3B8","type":"dashed","width":1},
                                         "label":{"formatter":f"Target {TARGET_OK_LINE}%","position":"end","fontSize":10,"color":"#64748B"},
                                         "data":[{"yAxis":TARGET_OK_LINE}]}},
                            {"name":"NG %","type":"line","data":pts_ng,
                             "connectNulls":False,"smooth":True,
                             "symbol":"circle","symbolSize":7,
                             "lineStyle":{"color":"#EF4444","width":2,"type":"dashed"},
                             "itemStyle":{"color":"#EF4444"}},
                        ],
                        "dataZoom":[{"type":"inside","start":0,"end":100},
                                    {"type":"slider","bottom":5,"height":18}],
                        "toolbox":{"feature":{"magicType":{"type":["line","bar"],"right":16,"top":10}}},
                    }, height="320px", key="trend_chart_1d")

        else:
            # ════════════════════════════════════════════════════
            # MODE 2 — MULTI-HARI
            # ════════════════════════════════════════════════════
            if not df_trend.empty:
                df_m = df_trend.copy().sort_values("Date")
                df_m["X_Axis"] = (
                    df_m["Date"].dt.strftime("%d %b") + " · S" + df_m["Shift"].astype(str)
                )
                x_order = df_m.drop_duplicates("X_Axis").sort_values("Date")["X_Axis"].tolist()

                if trend_mode == "Per SampleNo":
                    # 1 line per SampleNo, X = Date·Shift
                    raw_sno  = df_m["SampleNo"].astype(str).unique().tolist()
                    sno_ord  = sorted(raw_sno, key=lambda s: (0,int(s)) if s.isdigit() else (1,s))
                    series_sno_m = []
                    for si, sno in enumerate(sno_ord):
                        df_s = df_m[df_m["SampleNo"].astype(str)==sno]
                        pts  = []
                        for t_key in x_order:
                            sub = df_s[df_s["X_Axis"]==t_key]
                            if sub.empty: pts.append(None)
                            else:
                                ok=int((sub["Judgement"]=="OK").sum()); tot=len(sub)
                                pts.append({"value":round(ok/tot*100,1),"ok_pt":ok,"ng_pt":tot-ok,"total_pt":tot})
                        clr = PALETTE[si%len(PALETTE)]
                        series_sno_m.append({"name":str(sno),"type":"bar","data":pts,
                                             "itemStyle":{"color":clr,"borderRadius":[4,4,0,0]},
                                             "label":{"show":True,"position":"top","formatter":str(sno),
                                                      "fontSize":8,"color":clr}})
                    if series_sno_m:
                        series_sno_m[0]["markLine"] = {"silent":True,
                            "lineStyle":{"color":"#94A3B8","type":"dashed","width":1},
                            "label":{"formatter":f"Target {TARGET_OK_LINE}%","position":"end","fontSize":10,"color":"#64748B"},
                            "data":[{"yAxis":TARGET_OK_LINE}]}
                    st_echarts({
                        "title":{"text":f"Trend — {f_part}","subtext":"OK% per SampleNo",
                                 "left":16,"top":8,"textStyle":{"color":"#0F172A","fontSize":13,"fontWeight":700},
                                 "subtextStyle":{"color":"#94A3B8","fontSize":10}},
                        "grid":{"top":50,"right":20,"bottom":55,"left":45},
                        "tooltip":{"trigger":"axis","backgroundColor":"#1E293B","borderColor":"#334155",
                                   "textStyle":{"color":"#F8FAFC","fontSize":12},"formatter":tooltip_js},
                        "xAxis":{"type":"category","data":x_order,
                                 "axisLine":{"lineStyle":{"color":"#E2E8F0"}},"axisTick":{"show":False},
                                 "axisLabel":{"color":"#94A3B8","fontSize":10,"interval":0,"rotate":30},
                                 "splitLine":{"show":False}},
                        "yAxis":{"type":"value","min":0,"max":100,"axisLine":{"show":False},"axisTick":{"show":False},
                                 "axisLabel":{"color":"#94A3B8","fontSize":10,"formatter":"{value}%"},
                                 "splitLine":{"lineStyle":{"color":"#F1F5F9","type":"dashed"}}},
                        "series":series_sno_m,
                        "dataZoom":[{"type":"inside","start":0,"end":100},{"type":"slider","bottom":5,"height":18}],
                        "toolbox":{"feature":{"magicType":{"type":["bar","line"],"right":16,"top":10}}},
                    }, height="320px", key="trend_chart_per_sampleno")

                elif trend_mode == "Per Part & Model":
                    # 1 line per Part·Model combo
                    combos = (df_m[["PartName","ModelName"]]
                              .drop_duplicates()
                              .sort_values(["PartName","ModelName"])
                              .itertuples(index=False, name=None))
                    series_multi = []
                    combo_names  = []
                    for si, (pn, mn) in enumerate(combos):
                        label  = f"{pn} · {mn}"
                        df_pm  = df_m[(df_m["PartName"]==pn) & (df_m["ModelName"]==mn)]
                        pts    = []
                        for t_key in x_order:
                            sub = df_pm[df_pm["X_Axis"] == t_key]
                            if sub.empty:
                                pts.append(None)
                            else:
                                ok    = int((sub["Judgement"]=="OK").sum())
                                total = len(sub)
                                pts.append({
                                    "value": round(ok/total*100, 1),
                                    "ok_pt": ok, "ng_pt": total-ok, "total_pt": total,
                                })
                        clr = PALETTE[si % len(PALETTE)]
                        combo_names.append(label)
                        series_multi.append({
                            "name": label, "type": "bar",
                            "data": pts,
                            "itemStyle": {"color": clr, "borderRadius": [4,4,0,0]},
                            "label": {"show": True, "position": "top",
                                      "formatter": label, "fontSize": 8, "color": clr},
                        })
                    if series_multi:
                        series_multi[0]["markLine"] = {
                            "silent": True,
                            "lineStyle": {"color": "#94A3B8", "type": "dashed", "width": 1},
                            "label": {"formatter": f"Target {TARGET_OK_LINE}%",
                                      "position": "end", "fontSize": 10, "color": "#64748B"},
                            "data": [{"yAxis": TARGET_OK_LINE}],
                        }

                    st_echarts({
                        "title": {
                            "text": "Quality Trend — Per Part",
                            "subtext": "OK% per Part",
                            "left": 16, "top": 8,
                            "textStyle": {"color": "#0F172A", "fontSize": 13, "fontWeight": 700},
                            "subtextStyle": {"color": "#94A3B8", "fontSize": 10},
                        },
                        "grid": {"top": 50, "right": 20, "bottom": 55, "left": 45},
                        "tooltip": {"trigger": "axis", "backgroundColor": "#1E293B", "borderColor": "#334155",
                                    "textStyle": {"color": "#F8FAFC", "fontSize": 12}, "formatter": tooltip_js},
                        "xAxis": {
                            "type": "category", "data": x_order,
                            "axisLine": {"lineStyle": {"color": "#E2E8F0"}},
                            "axisTick": {"show": False},
                            "axisLabel": {"color": "#94A3B8", "fontSize": 10, "interval": 0, "rotate": 30},
                            "splitLine": {"show": False},
                        },
                        "yAxis": {
                            "type": "value", "min": 0, "max": 100,
                            "axisLine": {"show": False}, "axisTick": {"show": False},
                            "axisLabel": {"color": "#94A3B8", "fontSize": 10, "formatter": "{value}%"},
                            "splitLine": {"lineStyle": {"color": "#F1F5F9", "type": "dashed"}},
                        },
                        "series": series_multi,
                        "dataZoom": [{"type": "inside", "start": 0, "end": 100},
                                     {"type": "slider", "bottom": 5, "height": 18}],
                        "toolbox": {"feature": {"magicType": {"type": ["bar", "line"], "right": 16, "top": 10}}},
                    }, height="320px", key="trend_chart_per_sampel")

                else:
                    # ── Gabungan: X = Date·Shift, combined OK%/NG% ──────────
                    t = _build_trend_df(df_m)
                    t = pd.DataFrame({"X_Axis": x_order}).merge(t, on="X_Axis", how="left")

                    ok_data = [
                        {"value": row["OK_Pct"],
                         "ok_pt":    int(row["OK"])    if pd.notna(row["OK"])    else 0,
                         "ng_pt":    int(row["NG"])    if pd.notna(row["NG"])    else 0,
                         "total_pt": int(row["Total"]) if pd.notna(row["Total"]) else 0}
                        if pd.notna(row["OK_Pct"]) else None
                        for _, row in t.iterrows()
                    ]
                    ng_data = [
                        {"value": row["NG_Pct"],
                         "ok_pt":    int(row["OK"])    if pd.notna(row["OK"])    else 0,
                         "ng_pt":    int(row["NG"])    if pd.notna(row["NG"])    else 0,
                         "total_pt": int(row["Total"]) if pd.notna(row["Total"]) else 0}
                        if pd.notna(row["NG_Pct"]) else None
                        for _, row in t.iterrows()
                    ]

                    st_echarts({
                        "title": {
                            "text": "Quality Trend — All Parts",
                            "subtext": "Per Shift · OK%",
                            "left": 16, "top": 8,
                            "textStyle": {"color": "#0F172A", "fontSize": 13, "fontWeight": 700, "fontFamily": "Inter"},
                            "subtextStyle": {"color": "#94A3B8", "fontSize": 10},
                        },
                        "legend": {
                            "data": ["OK %", "NG %"], "right": 70, "top": 12,
                            "icon": "circle", "itemWidth": 8,
                            "textStyle": {"color": "#64748B", "fontSize": 11, "fontFamily": "Inter"},
                        },
                        "grid": {"top": 60, "right": 20, "bottom": 40, "left": 42},
                        "tooltip": {"trigger": "axis", "backgroundColor": "#1E293B", "borderColor": "#334155",
                                    "textStyle": {"color": "#F8FAFC", "fontSize": 12}, "formatter": tooltip_js},
                        "xAxis": {
                            "type": "category", "data": x_order,
                            "axisLine": {"lineStyle": {"color": "#E2E8F0"}},
                            "axisTick": {"show": False},
                            "axisLabel": {"color": "#94A3B8", "fontSize": 10, "interval": 0, "rotate": 30},
                            "splitLine": {"show": False},
                        },
                        "yAxis": {
                            "type": "value", "min": 0, "max": 100,
                            "axisLine": {"show": False}, "axisTick": {"show": False},
                            "axisLabel": {"color": "#94A3B8", "fontSize": 10, "formatter": "{value}%"},
                            "splitLine": {"lineStyle": {"color": "#F1F5F9", "type": "dashed"}},
                        },
                        "series": [
                            {
                                "name": "OK %", "type": "line", "smooth": True,
                                "data": ok_data, "connectNulls": False,
                                "symbol": "circle", "symbolSize": 7,
                                "lineStyle": {"color": "#22C55E", "width": 2.5},
                                "itemStyle": {"color": "#22C55E"},
                                "areaStyle": {"color": "#22C55E", "opacity": 0.08},
                                "markLine": {
                                    "silent": True,
                                    "lineStyle": {"color": "#94A3B8", "type": "dashed", "width": 1},
                                    "label": {"formatter": f"Target {TARGET_OK_LINE}%",
                                              "position": "end", "fontSize": 10, "color": "#64748B"},
                                    "data": [{"yAxis": TARGET_OK_LINE}],
                                },
                            },
                            {
                                "name": "NG %", "type": "line", "smooth": True,
                                "data": ng_data, "connectNulls": False,
                                "symbol": "circle", "symbolSize": 7,
                                "lineStyle": {"color": "#EF4444", "width": 2, "type": "dashed"},
                                "itemStyle": {"color": "#EF4444"},
                            },
                        ],
                        "dataZoom": [{"type": "inside", "start": 0, "end": 100},
                                     {"type": "slider", "bottom": 5, "height": 18}],
                        "toolbox": {"feature": {"magicType": {"type": ["line", "bar"], "right": 16, "top": 10}}},
                    }, height="320px", key="trend_chart_combined")
            else:
                st.markdown(
                    '<div style="background:#F8FAFC;border-radius:8px;border:1px solid #E2E8F0;'
                    'padding:32px;text-align:center;color:#94A3B8;">'
                    '<div style="font-size:28px;margin-bottom:8px;">📉</div>'
                    '<div style="font-size:13px;font-weight:600;">Belum ada data untuk periode ini</div>'
                    '<div style="font-size:11px;margin-top:4px;">Ubah filter periode atau tunggu data masuk</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
        # ─────────────────────────────────────────────────────────────
        # ROW 5 — LATEST INCOMING DATA (clean table view)
        # ─────────────────────────────────────────────────────────────
        st.markdown('<div style="font-size:16px;font-weight:700;color:#0F172A;margin-top:28px;margin-bottom:12px;">Data Terbaru</div>', unsafe_allow_html=True)
 
        if not self.df_all.empty:
            df_latest_raw = self.df_all.sort_values("Date", ascending=False).head(10).reset_index(drop=True)
 
            # ── Build kolom-kolom penting saja (8 kolom, bukan 19) ──
            sample_col = df_latest_raw["SampleNo"] if "SampleNo" in df_latest_raw.columns else pd.Series(["-"] * len(df_latest_raw))
            df_show = pd.DataFrame({
                "Waktu": pd.to_datetime(df_latest_raw["Date"]).dt.strftime("%d %b · %H:%M"),
                "Shift": df_latest_raw["Shift"],
                "Sample": sample_col,
                "Part / Model": df_latest_raw["PartName"].astype(str) + "  /  " + df_latest_raw["ModelName"].astype(str),
                "CMM": df_latest_raw["CMMName"],
                "Parameter": df_latest_raw["Parameter"],
                "Deviasi": df_latest_raw["Deviation"],
                "Status": df_latest_raw["Judgement"],
            })
 
            # ── Row highlight: KP+NG → merah tegas, NG biasa → kuning ──
            def highlight_rows(row):
                idx = row.name
                orig = df_latest_raw.loc[idx]
                is_kp = False
                if "KP" in orig.index:
                    try:
                        is_kp = int(orig["KP"]) == 1
                    except (ValueError, TypeError):
                        is_kp = False
                is_ng = orig.get("Judgement") == "NG"
 
                if is_kp and is_ng:
                    return ['background-color:#FEE2E2;color:#991B1B;font-weight:700;'] * len(row)
                elif is_ng:
                    return ['background-color:#FEF3C7;color:#92400E;'] * len(row)
                return [''] * len(row)
 
            styled = df_show.style.format({
                "Deviasi": "{:+.4f}",
            }).apply(highlight_rows, axis=1)
 
            st.dataframe(
                styled,
                use_container_width=True,
                height=380,
                hide_index=True,
                column_config={
                    "Waktu":        st.column_config.TextColumn("Waktu", width="small"),
                    "Shift":        st.column_config.NumberColumn("Shift", width="small"),
                    "Sample":       st.column_config.TextColumn("Sample", width="small"),
                    "Part / Model": st.column_config.TextColumn("Part / Model", width="medium"),
                    "CMM":          st.column_config.TextColumn("CMM", width="small"),
                    "Parameter":    st.column_config.TextColumn("Parameter", width="medium"),
                    "Deviasi":      st.column_config.NumberColumn("Deviasi", width="small", help="Selisih Actual − Nominal"),
                    "Status":       st.column_config.TextColumn("Status", width="small"),
                },
            )
 
            # Legend
            st.markdown("""
            <div style="display:flex;gap:18px;margin-top:10px;font-size:11px;color:#64748B;align-items:center;">
                <div style="display:flex;align-items:center;gap:6px;">
                    <span style="width:14px;height:14px;background:#FEE2E2;border:1px solid #FECACA;border-radius:3px;display:inline-block;"></span>
                    <span style="font-weight:600;color:#991B1B;">KP Critical NG</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                    <span style="width:14px;height:14px;background:#FEF3C7;border:1px solid #FDE68A;border-radius:3px;display:inline-block;"></span>
                    <span style="font-weight:600;color:#92400E;">Regular NG</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                    <span style="width:14px;height:14px;background:white;border:1px solid #E2E8F0;border-radius:3px;display:inline-block;"></span>
                    <span style="font-weight:600;color:#475569;">OK</span>
                </div>
                <div style="margin-left:auto;font-size:11px;color:#64748B;font-weight:500;">
                    10 entri terbaru
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Belum ada data produksi yang masuk.")