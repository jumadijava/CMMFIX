import re
"""
utils/filters.py
────────────────
Shared filter builder untuk semua halaman dashboard.
Eliminasi duplikasi blok filter yang sama di setiap page.

Cara pakai:
    from utils.filters import build_filters, apply_filters

    filters = build_filters(self.df_all, session_prefix="dash")
    df      = apply_filters(self.df_all, filters)
"""

import streamlit as st
from datetime import date, timedelta, datetime
import pytz
import pandas as pd


# ─────────────────────────────────────────────────────────────────
#  KONSTANTA
# ─────────────────────────────────────────────────────────────────
TIMEZONE   = "Asia/Jakarta"
try:
    from settings_config import get_target_ok as _get_target_ok
    TARGET_OK = _get_target_ok()
except Exception:
    TARGET_OK = 98.65  # fallback

# Batas jam per shift (inklusif bawah, eksklusif atas)
SHIFT_HOURS = {
    "1": (7, 16),
    "2": (16, 23),
    "3": (23, 7),   # shift 3 melewati tengah malam
}


def _get_current_shift() -> str:
    """Kembalikan shift aktif berdasarkan jam WIB saat ini."""
    tz = pytz.timezone(TIMEZONE)
    hour = datetime.now(tz).hour
    if 6 <= hour < 16:
        return "1"
    elif 16 <= hour < 23:
        return "2"
    else:
        return "3"


def build_filters(df_all: pd.DataFrame, session_prefix: str) -> dict:
    """
    Render baris filter (10 kolom) dan kembalikan dict nilai filter aktif.
    """
    p = session_prefix  # alias pendek

    # ── Opsi dropdown statis/mandiri ───────────────────────────────
    cmm_opts   = ["Semua Mesin"]    + sorted(df_all["CMMName"].dropna().unique().tolist())
    cat_opts   = ["Semua Kategori"] + sorted(df_all["Category"].dropna().unique().tolist())
    shift_opts = ["Semua Shift"]    + sorted(df_all["Shift"].dropna().unique().tolist())
    kp_opts    = ["Semua Titik"]    + sorted(df_all["KP"].dropna().astype(str).unique().tolist())

    # ── Handle reset flags dari Back button — HARUS SEBELUM curr_part/model dibaca
    if st.session_state.pop(f"_reset_{p}_model", False):
        st.session_state.pop(f"{p}_model", None)
    if st.session_state.pop(f"_reset_{p}_part", False):
        st.session_state.pop(f"{p}_part", None)
        st.session_state.pop(f"{p}_model", None)

    # Ambil status pilihan Part dan Model (setelah reset) ─────────────
    curr_part  = st.session_state.get(f"{p}_part", "Semua Part")
    curr_model = st.session_state.get(f"{p}_model", "Semua Model")

    if curr_part != "Semua Part":
        _tmp_m = df_all[df_all["PartName"] == curr_part]
        model_opts = ["Semua Model"] + sorted(_tmp_m["ModelName"].dropna().unique().tolist())
    else:
        model_opts = ["Semua Model"] + sorted(df_all["ModelName"].dropna().unique().tolist())

    if curr_model != "Semua Model":
        _tmp_p = df_all[df_all["ModelName"] == curr_model]
        part_opts = ["Semua Part"] + sorted(_tmp_p["PartName"].dropna().unique().tolist())
    else:
        part_opts = ["Semua Part"] + sorted(df_all["PartName"].dropna().unique().tolist())

    # ── Opsi SampleNo Dinamis (bergantung pada Part & Model) ───────
    _tmp_s = df_all.copy()
    if curr_part != "Semua Part":
        _tmp_s = _tmp_s[_tmp_s["PartName"] == curr_part]
    if curr_model != "Semua Model":
        _tmp_s = _tmp_s[_tmp_s["ModelName"] == curr_model]

    sampleno_opts = ["Semua Sample"] + sorted(
        _tmp_s["SampleNo"].dropna().astype(str).unique().tolist(),
        key=lambda s: [int(c) if c.isdigit() else c.lower()
                       for c in re.split(r"(\d+)", s)])

    # --- TAMBAHAN FIX STATE NYANGKUT ---
    # Cek current state. Jika nilainya nyangkut di memori tapi tidak ada di opsi baru, reset paksa.
    current_sampleno_state = st.session_state.get(f"{p}_sampleno", "Semua Sample")
    if current_sampleno_state not in sampleno_opts:
        st.session_state[f"{p}_sampleno"] = "Semua Sample"
        current_sampleno_state = "Semua Sample"
        
    # Ambil index yang benar agar selectbox tidak kebingungan
    idx_sampleno = sampleno_opts.index(current_sampleno_state)
    # -----------------------------------

    # ── Render kolom filter (10 kolom, Cycle disembunyikan dari UI) ─
    # ── Default shift otomatis ───────────────────────────────────────
    current_shift  = _get_current_shift()
    shift_opts_str = [str(x) for x in shift_opts]
    default_shift_idx = shift_opts_str.index(current_shift) if current_shift in shift_opts_str else 0

    # ── Label row di atas filter ────────────────────────────────────
    _LBL = '<div style="font-size:11px;font-weight:600;color:#64748B;margin-bottom:3px;">{t}</div>'
    lbl_cols = st.columns([1.3, 1, 1, 1.3, 1.3, 1.3, 1.4, 1.2], gap="small")
    with lbl_cols[0]: st.markdown(_LBL.format(t="Periode"),    unsafe_allow_html=True)
    with lbl_cols[1]: st.markdown(_LBL.format(t="Shift"),      unsafe_allow_html=True)
    with lbl_cols[2]: st.markdown(_LBL.format(t="Mesin CMM"),  unsafe_allow_html=True)
    with lbl_cols[3]: st.markdown(_LBL.format(t="Part"),       unsafe_allow_html=True)
    with lbl_cols[4]: st.markdown(_LBL.format(t="Model"),      unsafe_allow_html=True)
    with lbl_cols[5]: st.markdown(_LBL.format(t="Kategori"),   unsafe_allow_html=True)
    with lbl_cols[6]: st.markdown(_LBL.format(t="KP"),         unsafe_allow_html=True)
    with lbl_cols[7]: st.markdown(_LBL.format(t="Sample No"),  unsafe_allow_html=True)

    # ── Render selectbox ────────────────────────────────────────────
    cols = st.columns([1.3, 1, 1, 1.3, 1.3, 1.3, 1.4, 1.2], gap="small")
    with cols[0]: f_time = st.selectbox("Periode", ["Hari Ini", "7 Hari Terakhir", "30 Hari Terakhir", "Semua Periode", "Custom"],
                                        key=f"{p}_time", label_visibility="collapsed", filter_mode=None)
    with cols[1]:
        f_shift = st.selectbox("Shift", shift_opts,
            index=default_shift_idx, key=f"{p}_shift",
            label_visibility="collapsed",
            format_func=lambda x: f"Shift {x}" if str(x) != "Semua Shift" else x, filter_mode=None)
    with cols[2]: f_cmm   = st.selectbox("Mesin CMM", cmm_opts,   key=f"{p}_cmm",   label_visibility="collapsed", filter_mode=None)
    with cols[3]: f_part  = st.selectbox("Part",      part_opts,  key=f"{p}_part",  label_visibility="collapsed", filter_mode=None)
    with cols[4]: f_model = st.selectbox("Model",     model_opts, key=f"{p}_model", label_visibility="collapsed", filter_mode=None)
    with cols[5]: f_cat   = st.selectbox("Kategori",  cat_opts,   key=f"{p}_cat",   label_visibility="collapsed", filter_mode=None)
    _kp_opts  = ["Semua Titik", "KP saja"] if f_cat == "Produksi" else ["Semua Titik"]
    _kp_state = st.session_state.get(f"{p}_kp", "Semua Titik")
    if _kp_state not in _kp_opts:
        st.session_state[f"{p}_kp"] = "Semua Titik"; _kp_state = "Semua Titik"
    with cols[6]: f_kp = st.selectbox("KP", _kp_opts, key=f"{p}_kp",
                                       label_visibility="collapsed", filter_mode=None,
                                       index=_kp_opts.index(_kp_state))
    _sno_disabled = (curr_part == "Semua Part" or curr_model == "Semua Model")
    if _sno_disabled:
        sampleno_opts = ["Semua Sample"]; idx_sampleno = 0
    with cols[7]:
        f_sampleno = st.selectbox("Sample", sampleno_opts, index=idx_sampleno,
            key=f"{p}_sampleno", label_visibility="collapsed",
            filter_mode=None, disabled=_sno_disabled)

    # ── Rentang tanggal — muncul di baris bawah hanya kalau Kustom ────
    today = date.today()
    if f_time == "Hari Ini":
        d1_val, d2_val = today, today
    elif f_time == "7 Hari Terakhir":
        d1_val, d2_val = today - timedelta(days=7), today
    elif f_time == "Semua Periode":
        d1_val = df_all["Date"].dt.date.min() if not df_all.empty else today
        d2_val = df_all["Date"].dt.date.max() if not df_all.empty else today
    else:
        d1_val, d2_val = today, today

    is_custom = (f_time == "Custom")
    if is_custom:
        dc1, dc2, _ = st.columns([1.5, 1.5, 6], gap="small")
        with dc1: f_d1 = st.date_input("Dari", value=d1_val, key=f"d1_{p}_custom", label_visibility="visible")
        with dc2: f_d2 = st.date_input("Sampai", value=d2_val, key=f"d2_{p}_custom", label_visibility="visible")
    else:
        f_d1, f_d2 = d1_val, d2_val

    return {
        "cmm":      f_cmm,
        "part":     f_part,
        "model":    f_model,
        "cat":      f_cat,
        "kp":       f_kp,
        "time":     f_time,
        "d1":       f_d1,
        "d2":       f_d2,
        "shift":    f_shift,
        "sampleno": f_sampleno,
        "cycle":    st.session_state.get(f"{p}_cycle_hidden", "Semua Periode"),
    }


def build_filters_dashboard(df_all: pd.DataFrame, session_prefix: str = "shared") -> dict:
    """
    Filter Dashboard — 1 baris, selectbox + markdown label.
    Urutan: Periode | Shift | Kategori | Mesin CMM | Pilih Part
    """
    p = session_prefix

    # ── Opsi ─────────────────────────────────────────────────────────
    TIME_OPTS = ["Hari Ini", "7 Hari Terakhir", "30 Hari Terakhir", "Semua Periode", "Custom"]
    TIME_MAP  = {
        "Hari Ini": "Hari Ini",
        "7 Hari Terakhir": "7 Hari Terakhir",
        "30 Hari Terakhir": "30 Hari Terakhir",
        "Semua Periode": "Semua Periode",
        "Custom": "Custom",
    }
    current_shift = _get_current_shift()
    SHIFT_OPTS    = ["Semua Shift", "Shift 1", "Shift 2", "Shift 3"]
    SHIFT_VAL_MAP = {"Semua Shift": "Semua Shift", "Shift 1": "1", "Shift 2": "2", "Shift 3": "3"}
    default_shift_label = f"Shift {current_shift}" if f"Shift {current_shift}" in SHIFT_OPTS else "Semua Shift"
    default_shift_idx   = SHIFT_OPTS.index(default_shift_label)

    cat_vals = sorted(df_all["Category"].dropna().unique().tolist())
    CAT_OPTS = ["Semua Kategori"] + cat_vals
    CAT_MAP  = {"Semua Kategori": "Semua Kategori"} | {c: c for c in cat_vals}

    cmm_vals = sorted(df_all["CMMName"].dropna().unique().tolist())
    CMM_OPTS = ["Semua Mesin"] + cmm_vals
    CMM_MAP  = {"Semua Mesin": "Semua Mesin"} | {c: c for c in cmm_vals}

    combos     = (df_all[["PartName","ModelName"]].dropna().drop_duplicates()
                  .sort_values(["PartName","ModelName"]))
    combo_opts = ["Semua Part"] + [f"{r.PartName} · {r.ModelName}" for _, r in combos.iterrows()]

    # ── Baca state custom sebelum render ────────────────────────────
    _cur_time = st.session_state.get(f"{p}_dash_time", "Hari Ini")
    is_custom = (_cur_time == "Custom")

    # ── Layout 5 kolom ──────────────────────────────────────────────
    cols = st.columns([1.8, 1.6, 1.4, 1.6, 2.2], gap="small")
    col_time, col_shift, col_cat, col_cmm, col_combo = cols

    _MD = '<p style="font-size:14px;font-weight:600;color:#374151;margin-bottom:4px;">{label}</p>'

    with col_time:
        st.markdown(_MD.format(label="Periode"), unsafe_allow_html=True)
        f_time_sel = st.selectbox(
            "Periode", TIME_OPTS,
            key=f"{p}_dash_time",
            label_visibility="collapsed",
            filter_mode=None,
        )
    f_time = TIME_MAP[f_time_sel]
    is_custom = (f_time_sel == "Custom")

    with col_shift:
        st.markdown(_MD.format(label="Shift"), unsafe_allow_html=True)
        # Pastikan default index valid — cek state sekarang
        _cur_shift_state = st.session_state.get(f"{p}_dash_shift", default_shift_label)
        if _cur_shift_state not in SHIFT_OPTS:
            _cur_shift_state = default_shift_label
        f_shift_sel = st.selectbox(
            "Shift", SHIFT_OPTS,
            index=SHIFT_OPTS.index(_cur_shift_state),
            key=f"{p}_dash_shift",
            label_visibility="collapsed",
            filter_mode=None,
        )
    f_shift = SHIFT_VAL_MAP[f_shift_sel]

    with col_cat:
        st.markdown(_MD.format(label="Kategori"), unsafe_allow_html=True)
        _def_cat = "Produksi" if "Produksi" in CAT_OPTS else "Semua Kategori"
        if st.session_state.get(f"{p}_dash_cat") not in CAT_OPTS:
            st.session_state[f"{p}_dash_cat"] = _def_cat
        f_cat_sel = st.selectbox(
            "Kategori", CAT_OPTS,
            key=f"{p}_dash_cat",
            label_visibility="collapsed",
            filter_mode=None,
        )
    f_cat = CAT_MAP[f_cat_sel]

    with col_cmm:
        st.markdown(_MD.format(label="Mesin CMM"), unsafe_allow_html=True)
        f_cmm_sel = st.selectbox(
            "Mesin CMM", CMM_OPTS,
            key=f"{p}_dash_cmm",
            label_visibility="collapsed",
            filter_mode=None,
        )
    f_cmm = CMM_MAP[f_cmm_sel]

    with col_combo:
        st.markdown(_MD.format(label="Part"), unsafe_allow_html=True)
        f_combo = st.selectbox(
            "Part", combo_opts,
            key=f"{p}_combo",
            label_visibility="collapsed",
            filter_mode=None,
        )

    # ── Rentang tanggal final ─────────────────────────────────────
    today = date.today()
    if f_time == "Hari Ini":
        f_d1, f_d2 = today, today
    elif f_time == "7 Hari Terakhir":
        f_d1, f_d2 = today - timedelta(days=6), today
    elif f_time == "30 Hari Terakhir":
        f_d1, f_d2 = today - timedelta(days=29), today
    elif f_time == "Semua Periode":
        f_d1 = df_all["Date"].dt.date.min() if not df_all.empty else today
        f_d2 = df_all["Date"].dt.date.max() if not df_all.empty else today
    else:
        f_d1, f_d2 = today, today

    if is_custom:
        _dc = st.columns([1, 1, 5])
        with _dc[0]:
            f_d1 = st.date_input("Dari",   value=f_d1, key=f"d1_{p}_custom", label_visibility="visible")
        with _dc[1]:
            f_d2 = st.date_input("Sampai", value=f_d2, key=f"d2_{p}_custom", label_visibility="visible")

    # ── Pecah combo → part & model ────────────────────────────────
    if f_combo == "Semua Part":
        f_part, f_model = "Semua Part", "Semua Model"
    else:
        parts   = f_combo.split(" · ", 1)
        f_part  = parts[0]
        f_model = parts[1] if len(parts) > 1 else "Semua Model"

    return {
        "cmm":      f_cmm,
        "part":     f_part,
        "model":    f_model,
        "cat":      f_cat,
        "kp":       "Semua Titik",
        "time":     f_time,
        "d1":       f_d1,
        "d2":       f_d2,
        "shift":    f_shift,
        "sampleno": "Semua Sample",
        "cycle":    "Semua Periode",
    }


def build_filters_quick(df_all: pd.DataFrame, session_prefix: str = "shared") -> dict:
    """
    Filter ringkas untuk Descriptive Quick mode — Time + Shift + Category.
    Part·Model tidak ada karena Quick mode drill-down via klik bar pareto.
    Return dict kompatibel dengan apply_filters.
    """
    p = session_prefix

    # ── Konstanta pills ───────────────────────────────────────────
    TIME_OPTS = ["Hari Ini", "7 Hari Terakhir", "30 Hari Terakhir", "Semua Periode", "Custom"]
    TIME_MAP  = {
        "Hari Ini": "Hari Ini",
        "7 Hari Terakhir": "7 Hari Terakhir",
        "30 Hari Terakhir": "30 Hari Terakhir",
        "Semua Periode": "Semua Periode",
        "Custom": "Custom",
    }
    SHIFT_OPTS    = ["Semua", "1", "2", "3"]
    SHIFT_MAP     = {"Semua": "Semua Shift", "1": "1", "2": "2", "3": "3"}
    current_shift = _get_current_shift()
    SHIFT_DEFAULT = current_shift if current_shift in SHIFT_OPTS else "Semua"

    cat_vals  = sorted(df_all["Category"].dropna().unique().tolist())
    CAT_OPTS  = ["Semua"] + cat_vals
    CAT_MAP   = {"Semua": "Semua Kategori"} | {c: c for c in cat_vals}

    # ── Baca state Time untuk keputusan layout (Kustom?) ─────────
    _cur_time = st.session_state.get(f"{p}_dash_time", "Hari Ini")
    is_custom = (_cur_time == "Custom")

    # ── Layout: Time | Shift | Cat | KP (+ Date From | To kalau Custom) ────
    if is_custom:
        cols = st.columns([1.6, 1.4, 1.4, 0.8, 1.0, 1.0], gap="small")
        col_time, col_shift, col_cat, col_kp, col_d1, col_d2 = cols
    else:
        cols = st.columns([1.6, 1.4, 1.4, 0.8], gap="small")
        col_time, col_shift, col_cat, col_kp = cols
        col_d1 = col_d2 = None

    _LBL2 = '<div style="font-size:11px;font-weight:600;color:#64748B;margin-bottom:3px;">{t}</div>'
    with col_time:  st.markdown(_LBL2.format(t="Periode"),  unsafe_allow_html=True)
    with col_shift: st.markdown(_LBL2.format(t="Shift"),    unsafe_allow_html=True)
    with col_cat:   st.markdown(_LBL2.format(t="Kategori"), unsafe_allow_html=True)
    with col_kp:    st.markdown(_LBL2.format(t="KP"),       unsafe_allow_html=True)

    # ── Time selectbox ───────────────────────────────────────────
    with col_time:
        f_time_pill = st.selectbox(
            "Periode", TIME_OPTS,
            index=TIME_OPTS.index(st.session_state.get(f"{p}_dash_time", "Hari Ini"))
                  if st.session_state.get(f"{p}_dash_time", "Hari Ini") in TIME_OPTS else 0,
            key=f"{p}_dash_time",
            label_visibility="collapsed",
        ) or "Hari Ini"
    f_time = TIME_MAP[f_time_pill]

    # ── Shift selectbox ───────────────────────────────────────────
    with col_shift:
        f_shift_pill = st.selectbox(
            "Shift", SHIFT_OPTS,
            index=SHIFT_OPTS.index(st.session_state.get(f"{p}_dash_shift", SHIFT_DEFAULT))
                  if st.session_state.get(f"{p}_dash_shift", SHIFT_DEFAULT) in SHIFT_OPTS else 0,
            key=f"{p}_dash_shift",
            label_visibility="collapsed",
            format_func=lambda x: "Semua Shift" if x == "Semua" else f"Shift {x}",
        ) or SHIFT_DEFAULT
    f_shift = SHIFT_MAP[f_shift_pill]

    # ── Category selectbox (default Produksi) ─────────────────────
    default_cat = "Produksi" if "Produksi" in CAT_OPTS else "Semua"
    with col_cat:
        f_cat_pill = st.selectbox(
            "Kategori", CAT_OPTS,
            index=CAT_OPTS.index(st.session_state.get(f"{p}_dash_cat", default_cat))
                  if st.session_state.get(f"{p}_dash_cat", default_cat) in CAT_OPTS else
                  (CAT_OPTS.index(default_cat) if default_cat in CAT_OPTS else 0),
            key=f"{p}_dash_cat",
            label_visibility="collapsed",
        ) or default_cat
    f_cat = CAT_MAP.get(f_cat_pill, f_cat_pill)

    # ── KP selectbox ──────────────────────────────────────────────
    _kp_q_opts = ["Semua Titik", "KP saja"] if f_cat_pill == "Produksi" else ["Semua Titik"]
    _kp_q_st   = st.session_state.get(f"{p}_dash_kp", "Semua Titik")
    if _kp_q_st not in _kp_q_opts: _kp_q_st = "Semua Titik"
    f_kp = "Semua Titik"
    with col_kp:
        kp_val = st.selectbox(
            "KP", _kp_q_opts,
            key=f"{p}_dash_kp",
            label_visibility="collapsed",
            index=_kp_q_opts.index(_kp_q_st),
        ) or "Semua Titik"
    f_kp = "1" if kp_val == "KP saja" else "Semua Titik"

    # ── Rentang tanggal sesuai preset ────────────────────────────
    today = date.today()
    if f_time == "Hari Ini":
        d1_val, d2_val = today, today
    elif f_time == "7 Hari Terakhir":
        d1_val, d2_val = today - timedelta(days=6), today
    elif f_time == "30 Hari Terakhir":
        d1_val, d2_val = today - timedelta(days=29), today
    elif f_time == "Semua Periode":
        d1_val = df_all["Date"].dt.date.min() if not df_all.empty else today
        d2_val = df_all["Date"].dt.date.max() if not df_all.empty else today
    else:
        d1_val, d2_val = today, today

    # ── Date input (hanya saat Custom) ───────────────────────────
    if is_custom and col_d1 is not None:
        with col_d1:
            f_d1 = st.date_input(
                "Dari", value=d1_val,
                key=f"d1_{p}_custom",
                label_visibility="visible",
            )
        with col_d2:
            f_d2 = st.date_input(
                "Sampai", value=d2_val,
                key=f"d2_{p}_custom",
                label_visibility="visible",
            )
    else:
        f_d1, f_d2 = d1_val, d2_val

    return {
        "cmm":      "Semua Mesin",
        "part":     "Semua Part",
        "model":    "Semua Model",
        "cat":      f_cat,
        "kp":       f_kp,
        "time":     f_time,
        "d1":       f_d1,
        "d2":       f_d2,
        "shift":    f_shift,
        "sampleno": "Semua Sample",
        "cycle":    "Semua Periode",
    }


def apply_filters(df_all: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """
    Terapkan filters (hasil build_filters) ke df_all.
    Tidak melakukan .copy() yang tidak perlu — langsung chain boolean mask.
    """
    mask = pd.Series(True, index=df_all.index)

    if filters.get("cmm")      not in ("Semua Mesin", "All CMM", None):      mask &= df_all["CMMName"]  == filters["cmm"]
    if filters.get("part")     not in ("Semua Part",  "All Part", None):     mask &= df_all["PartName"]  == filters["part"]
    if filters.get("model")    not in ("Semua Model", "All Model", None):    mask &= df_all["ModelName"] == filters["model"]
    if filters.get("cat")      not in ("Semua Kategori", "All Category", None): mask &= df_all["Category"]  == filters["cat"]
    if filters.get("kp")       not in ("Semua Titik", "All KP", None):       mask &= df_all["KP"].astype(str) == filters["kp"]
    if filters.get("shift")    not in ("Semua Shift", "All Shift", None):    mask &= df_all["Shift"].astype(str) == str(filters["shift"])
    if filters.get("sampleno") not in ("Semua Sample", "All SampleNo", None): mask &= df_all["SampleNo"].astype(str) == filters["sampleno"]

    # Logika cycle tetap dipertahankan
    if filters.get("cycle", "Semua Periode") not in ("Semua Periode", "All Cycle", None):
        mask &= df_all["Cycle"].astype(str) == filters["cycle"]

    mask &= (df_all["Date"].dt.date >= filters["d1"]) & (df_all["Date"].dt.date <= filters["d2"])

    return df_all[mask]