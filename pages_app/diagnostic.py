"""
pages/diagnostic.py
────────────────────
Diagnostic — Root Cause Analysis (list view)
OPTIMIZED: @st.fragment, session_state cache, single-pass apply
"""

import streamlit as st
from streamlit_echarts import st_echarts, JsCode
import pandas as pd
import numpy as np

from local_db import (
    RC_CATEGORIES, RC_STATUSES,
    save_root_cause, get_root_causes,
    get_root_cause_by_key, delete_root_cause,
    get_rc_stats,
)

STATUS_COLOR = {
    "Open":         ("#DC2626", "#FEE2E2"),
    "Investigated": ("#D97706", "#FEF3C7"),
    "Resolved":     ("#16A34A", "#DCFCE7"),
}

STATUS_CLR = {
    "Open":         "background-color:#FEE2E2;color:#991B1B;font-weight:600;",
    "Investigated": "background-color:#FEF3C7;color:#92400E;font-weight:600;",
    "Resolved":     "background-color:#DCFCE7;color:#14532D;font-weight:600;",
}

ROLE_BADGE = {
    "Measurement": (
        '<span style="background:#DBEAFE;color:#1E40AF;font-size:9px;'
        'font-weight:700;padding:2px 7px;border-radius:4px;">MEASUREMENT</span>'
    ),
    "Produksi": (
        '<span style="background:#FEF3C7;color:#92400E;font-size:9px;'
        'font-weight:700;padding:2px 7px;border-radius:4px;">PRODUKSI</span>'
    ),
}


# ─────────────────────────────────────────────────────────────────
#  Cache helper — ikuti pola predictive.py
# ─────────────────────────────────────────────────────────────────
def _get_rc_all_cached() -> dict:
    """
    Ambil semua root causes dan simpan ke session_state.
    Di-invalidate setiap kali ada save/delete (lewat flag diag_rc_dirty).
    """
    if st.session_state.get("diag_rc_dirty", True) or "diag_rc_all" not in st.session_state:
        st.session_state["diag_rc_all"] = {
            rc["rc_key"]: rc for rc in get_root_causes()
        }
        st.session_state["diag_rc_dirty"] = False
    return st.session_state["diag_rc_all"]


def _invalidate_rc_cache():
    """Tandai cache RC harus di-refresh pada run berikutnya."""
    st.session_state["diag_rc_dirty"] = True


# ─────────────────────────────────────────────────────────────────
#  Single-pass enrichment — ganti 6x .apply()/.map() terpisah
# ─────────────────────────────────────────────────────────────────
def _enrich_ng(df_ng: pd.DataFrame, rc_all: dict, param_col: str) -> pd.DataFrame:
    """Tambah semua kolom _xxx dalam satu pass — fully vectorized, tanpa .apply()."""
    df = df_ng.copy()
    df["_date_str"] = df["Date"].dt.strftime("%d %b %Y")  # display
    df["_date_key"] = df["_date_str"]  # RC key — sama dengan format notif CSV ("%d %b %Y")
    df["_shift"]    = df["Shift"].astype(str)
    df["_sampleno"] = df["SampleNo"].astype(str)
    df["_kp"]       = df.get("KP", pd.Series(0, index=df.index)).astype(str)

    # Hitung kolom teks sekaligus dalam satu vektorisasi
    has_ref_col   = "ref" in df.columns
    has_id_col    = "ID" in df.columns
    has_param_col = param_col in df.columns

    ref_series = (
        df["ref"].astype(str).str.strip()
        if has_ref_col else pd.Series("", index=df.index)
    )
    id_series = (
        df["ID"].astype(str).str.strip()
        if has_id_col else pd.Series("", index=df.index)
    )
    param_series = (
        df[param_col].astype(str).str.strip()
        if has_param_col else pd.Series("", index=df.index)
    )
    param_fb_series = (
        df["Parameter"].astype(str).str.strip()
        if "Parameter" in df.columns else pd.Series("", index=df.index)
    )

    df["_ref"]   = ref_series.where(~ref_series.isin(["", "-", "nan"]), id_series)
    df["_param"] = param_series.where(~param_series.isin(["", "-", "nan"]), param_fb_series)

    # _dev — vektorisasi dengan format string pandas
    dev = df["Deviation"]
    df["_dev"] = pd.Series(
        np.where(
            dev.notna(),
            dev.map(lambda x: f"{float(x):+.4f}"),
            "-"
        ),
        index=df.index
    )

    # rc_key — vektorisasi string concat, jauh lebih cepat dari .apply(axis=1)
    df["_rc_key"] = (
        df["_date_key"] + "|" +
        df["_shift"]    + "|" +
        df["_sampleno"] + "|" +
        df["PartName"].astype(str) + "|" +
        df["ModelName"].astype(str) + "|" +
        df["_ref"]   + "|" +
        df["_param"]
    )

    # Semua lookup RC dalam satu pass lewat map ke dict
    df["_status"]   = df["_rc_key"].map(lambda k: rc_all[k]["status"]               if k in rc_all else "Open")
    df["_category"] = df["_rc_key"].map(lambda k: rc_all[k].get("category", "")    if k in rc_all else "")
    df["_role"]     = df["_rc_key"].map(lambda k: rc_all[k].get("inputted_role","") if k in rc_all else "")
    df["_pic"]      = df["_rc_key"].map(lambda k: rc_all[k].get("pic", "")          if k in rc_all else "")
    df["_by"]       = df["_rc_key"].map(lambda k: rc_all[k].get("inputted_by", "")  if k in rc_all else "")

    return df


# ─────────────────────────────────────────────────────────────────
#  Page Class
# ─────────────────────────────────────────────────────────────────
class DiagnosticPage:
    def __init__(self, df_all: pd.DataFrame):
        self.df_all = df_all

    def _init(self):
        if "diag_open_key" not in st.session_state:
            st.session_state.diag_open_key = None

    def render(self):
        self._init()
        st.markdown("""
        <style>
        div[data-testid="stExpander"]{
          background:white !important;
          border:1px solid #E2E8F0 !important;
          border-radius:10px !important;
          margin-bottom:10px !important;
          box-shadow:0 1px 2px rgba(15,23,42,0.04) !important;
        }
        div[data-testid="stExpander"] summary{
          background:white !important;
          border-radius:10px !important;
          padding:6px 10px !important;
          position:static !important;
        }
        div[data-testid="stExpander"] details > div{
          background:white !important;
          padding:6px 14px 14px !important;
        }
        details summary { position: static !important; }
        /* ── Selectbox putih (override global abu-abu) ── */
        div[data-testid="stSelectbox"] > div[data-baseweb="select"] > div {
          background:#FFFFFF !important;
          border:1px solid #E2E8F0 !important;
          border-radius:8px !important;
          min-height:38px !important;
        }
        div[data-testid="stSelectbox"] > div[data-baseweb="select"] > div:hover {
          border-color:#CBD5E1 !important;
        }
        div[data-baseweb="select"] > div{
          background:#FFFFFF !important;
          border:1px solid #E2E8F0 !important;
          border-radius:8px !important;
          min-height:38px !important;
        }
        div[data-baseweb="select"] > div:hover{ border-color:#CBD5E1 !important; }
        textarea[data-testid="stTextAreaTextArea"]{
          background:#F1F5F9 !important;
          border:1px solid #E2E8F0 !important;
          border-radius:8px !important;
        }
        textarea[data-testid="stTextAreaTextArea"]:focus{
          border-color:#3B82F6 !important;
          box-shadow:0 0 0 3px rgba(59,130,246,0.1) !important;
        }
        /* Text input — white bg + visible border */
        div[data-testid="stTextInput"] input,
        div[data-testid="stTextInput"] > div > input,
        div[data-baseweb="input"] input {
          background:#FFFFFF !important;
          border:1px solid #D1D5DB !important;
          border-radius:8px !important;
        }
        div[data-baseweb="input"],
        div[data-testid="stTextInput"] > div {
          background:#FFFFFF !important;
          border:1px solid #D1D5DB !important;
          border-radius:8px !important;
        }
        div[data-baseweb="input"]:focus-within,
        div[data-testid="stTextInput"] > div:focus-within {
          border-color:#3B82F6 !important;
          box-shadow:0 0 0 3px rgba(59,130,246,0.1) !important;
        }
        div[data-testid="stExpander"] div[data-testid="stVerticalBlockBorderWrapper"]{
          background:white !important;
          border:1px solid #E2E8F0 !important;
          border-radius:8px !important;
        }
        </style>
        <div class="page-hdr">
          <span class="page-title">Diagnostic</span>
          <span class="page-sub">Root Cause Analysis</span>
        </div>
        """, unsafe_allow_html=True)

        view = st.segmented_control(
            "View",
            options=["Top NG", "Analytics", "Isi Root Cause", "Riwayat"],
            default="Top NG",
            key="diag_view",
            label_visibility="collapsed",
        )
        st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

        _view_desc = {
            "Top NG":           "Ranking titik NG terbanyak · klik untuk input atau lihat root cause.",
            "Analytics":        "Pareto kategori penyebab · heatmap Part × Kategori · tren status per shift.",
            "Isi Root Cause": "Isi root cause per kejadian NG · multi-select untuk bulk edit.",
            "Riwayat":          "Riwayat semua root cause yang sudah diinput · filter dan export.",
        }
        if view in _view_desc:
            st.markdown(f'<div class="section-desc">{_view_desc[view]}</div>', unsafe_allow_html=True)

        if view == "Top NG":
            self._render_top_ng()
        elif view == "Analytics":
            self._render_analytics()
        elif view == "Riwayat":
            self._render_history()
        else:
            self._render_list()

    # ── Filter bar ────────────────────────────────────────────────
    def _render_filters(self, show_status=True):
        from datetime import date, timedelta
        df = self.df_all

        # ── BARIS 1: Time | Shift | Category | KP  (semua selectbox) ─
        col_r1 = st.columns([1.6, 1.2, 1.4, 1.2], gap="small")

        with col_r1[0]:
            time_opts = ["Semua Periode", "Hari Ini", "7 Hari Terakhir", "30 Hari Terakhir", "Custom"]
            if "diag_time_sel" not in st.session_state:
                st.session_state["diag_time_sel"] = "Hari Ini"
            f_time = st.selectbox(
                "Periode", time_opts,
                key="diag_time_sel",
                label_visibility="visible",
            )

        with col_r1[1]:
            shift_opts = ["Semua Shift", "Shift 1", "Shift 2", "Shift 3"]
            try:
                import pytz as _pytz2
                from datetime import datetime as _dt2
                _cur_h = _dt2.now(_pytz2.timezone("Asia/Jakarta")).hour
            except Exception:
                from datetime import datetime as _dt2
                _cur_h = _dt2.now().hour
            _cur_shift_lbl = "Shift 1" if 7 <= _cur_h < 16 else ("Shift 2" if 16 <= _cur_h < 24 else "Shift 3")
            if "diag_shift_sel" not in st.session_state:
                st.session_state["diag_shift_sel"] = _cur_shift_lbl
            f_shift = st.selectbox(
                "Shift", shift_opts,
                key="diag_shift_sel",
                label_visibility="visible",
            )

        with col_r1[2]:
            cat_vals = sorted(df["Category"].dropna().unique().tolist()) if "Category" in df.columns else ["Produksi", "QIS"]
            cat_default_val = "Produksi" if "Produksi" in cat_vals else cat_vals[0] if cat_vals else "Semua Kategori"
            cat_opts = ["Semua Kategori"] + cat_vals
            if st.session_state.get("diag_cat_sel") not in cat_opts:
                st.session_state["diag_cat_sel"] = cat_default_val
            f_cat = st.selectbox(
                "Kategori", cat_opts,
                key="diag_cat_sel",
                label_visibility="visible",
            )

        with col_r1[3]:
            kp_opts = ["Semua Titik", "KP saja"]
            f_kp = st.selectbox(
                "Kritikal Point", kp_opts,
                key="diag_kp_sel",
                label_visibility="visible",
            )

        # ── Terapkan filter Time & Shift & Category ke df_base ────────
        today = date.today()

        # Custom date picker — muncul kalau pilih Custom
        if f_time == "Custom":
            _dc1, _dc2 = st.columns(2, gap="small")
            with _dc1:
                diag_d1 = st.date_input("Dari", value=today - timedelta(days=30),
                                        key="diag_d1", label_visibility="visible")
            with _dc2:
                diag_d2 = st.date_input("Sampai", value=today,
                                        key="diag_d2", label_visibility="visible")

        df_base = df.copy()
        if f_time == "Hari Ini":
            df_base = df_base[df_base["Date"].dt.date == today]
        elif f_time == "7 Hari Terakhir":
            df_base = df_base[df_base["Date"].dt.date >= today - timedelta(days=6)]
        elif f_time == "30 Hari Terakhir":
            df_base = df_base[df_base["Date"].dt.date >= today - timedelta(days=29)]
        elif f_time == "Custom":
            df_base = df_base[
                (df_base["Date"].dt.date >= diag_d1) &
                (df_base["Date"].dt.date <= diag_d2)
            ]

        shift_val_map = {"Shift 1": "1", "Shift 2": "2", "Shift 3": "3"}
        if f_shift != "Semua Shift":
            df_base = df_base[df_base["Shift"].astype(str) == shift_val_map[f_shift]]

        if f_cat != "Semua Kategori" and "Category" in df_base.columns:
            df_base = df_base[df_base["Category"] == f_cat]

        # ── BARIS 2: Part·Model | SampleNo | Ref/Point | Parameter ───
        # Cascade: cat → combo → sampleno → ref → param

        # Combo Part · Model
        combos_df = (
            df_base[["PartName", "ModelName"]]
            .dropna().drop_duplicates()
            .sort_values(["PartName", "ModelName"])
        )
        combo_opts = ["Semua Part & Model"] + [
            f"{r.PartName} · {r.ModelName}" for _, r in combos_df.iterrows()
        ]
        if st.session_state.get("diag_combo_sel") not in combo_opts:
            st.session_state["diag_combo_sel"] = "Semua Part & Model"

        # df setelah combo terpilih (untuk downstream options)
        cur_combo_val = st.session_state.get("diag_combo_sel", "Semua Part & Model")
        df_after_combo = df_base.copy()
        if cur_combo_val != "Semua Part & Model":
            _sp = cur_combo_val.split(" · ", 1)
            if len(_sp) == 2:
                df_after_combo = df_base[
                    (df_base["PartName"] == _sp[0]) &
                    (df_base["ModelName"] == _sp[1])
                ]

        # SampleNo — dinamis dari combo
        sno_vals = sorted(
            df_after_combo["SampleNo"].dropna().astype(str).unique().tolist(),
            key=lambda s: (0, int(s)) if s.isdigit() else (1, s)
        )
        sno_opts = ["Semua Sample"] + sno_vals
        if st.session_state.get("diag_sno_sel") not in sno_opts:
            st.session_state["diag_sno_sel"] = "Semua Sample"

        # df setelah sampleno terpilih
        cur_sno = st.session_state.get("diag_sno_sel", "Semua Sample")
        df_after_sno = df_after_combo.copy()
        if cur_sno != "Semua Sample":
            df_after_sno = df_after_combo[df_after_combo["SampleNo"].astype(str) == cur_sno]

        # Ref / Point — dinamis dari sampleno
        param_col = "point" if "point" in df_after_sno.columns else "Parameter"
        ref_col   = "ref"   if "ref"   in df_after_sno.columns else "ID"

        ref_vals = sorted([
            r for r in df_after_sno[ref_col].dropna().astype(str).unique()
            if r.strip() not in ("", "-", "nan")
        ])
        ref_opts = ["Semua Ref / Point"] + ref_vals
        if st.session_state.get("diag_ref_sel") not in ref_opts:
            st.session_state["diag_ref_sel"] = "Semua Ref / Point"

        # Parameter — dinamis dari ref
        cur_ref = st.session_state.get("diag_ref_sel", "Semua Ref / Point")
        df_after_ref = df_after_sno.copy()
        if cur_ref != "Semua Ref / Point":
            df_after_ref = df_after_sno[df_after_sno[ref_col].astype(str) == cur_ref]

        param_vals = sorted([
            p for p in df_after_ref[param_col].dropna().astype(str).unique()
            if p.strip() not in ("", "-", "nan")
        ])
        param_opts = ["Semua Parameter"] + param_vals
        if st.session_state.get("diag_param_sel") not in param_opts:
            st.session_state["diag_param_sel"] = "Semua Parameter"

        col_r2 = st.columns([2, 1, 1.2, 1.8], gap="small")
        with col_r2[0]:
            f_combo = st.selectbox(
                "Part · Model", combo_opts,
                key="diag_combo_sel",
                label_visibility="visible",
            )
        with col_r2[1]:
            f_sno = st.selectbox(
                "No. Sample", sno_opts,
                key="diag_sno_sel",
                label_visibility="visible",
            )
        with col_r2[2]:
            f_ref = st.selectbox(
                "Ref / Point", ref_opts,
                key="diag_ref_sel",
                label_visibility="visible",
            )
        with col_r2[3]:
            f_param = st.selectbox(
                "Parameter", param_opts,
                key="diag_param_sel",
                label_visibility="visible",
            )

        # ── BARIS 3: Status tetap pills ───────────────────────────────
        status_pill = "Open"
        if show_status:
            st.markdown(
                '<div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:4px;">Status Root Cause</div>',
                unsafe_allow_html=True
            )
            status_pill = st.pills(
                "Status Root Cause",
                ["Semua Status", "Open", "Investigated", "Resolved"],
                default="Open",
                key="diag_status_pill",
                label_visibility="collapsed",
                selection_mode="single",
            ) or "Open"

        st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)

        # ── Terapkan semua filter ke df_base ─────────────────────────
        df_out = df_base.copy()

        # KP
        if f_kp == "KP saja" and "KP" in df_out.columns:
            df_out = df_out[df_out["KP"].astype(str) == "1"]

        # Part · Model
        f_part, f_model = "All", "All"
        if f_combo != "Semua Part & Model":
            _sp = f_combo.split(" · ", 1)
            if len(_sp) == 2:
                f_part, f_model = _sp[0], _sp[1]
                df_out = df_out[
                    (df_out["PartName"] == f_part) &
                    (df_out["ModelName"] == f_model)
                ]

        # SampleNo
        if f_sno != "Semua Sample":
            df_out = df_out[df_out["SampleNo"].astype(str) == f_sno]

        # Ref / Point
        if f_ref != "Semua Ref / Point":
            df_out = df_out[df_out[ref_col].astype(str) == f_ref]

        # Parameter
        if f_param != "Semua Parameter":
            df_out = df_out[df_out[param_col].astype(str) == f_param]

        return df_out, status_pill

    # ── NG LIST — @st.fragment agar klik baris tidak re-run semua ─
    @st.fragment
    def _render_list(self):
        df, status_filter = self._render_filters(show_status=True)
        if df.empty:
            st.info("Tidak ada data.")
            return

        param_col = "point" if "point" in df.columns else "Parameter"
        df_ng = df[df["Judgement"] == "NG"].copy()
        if df_ng.empty:
            st.success("Tidak ada NG pada periode ini.")
            return

        # ── Cache RC dari DB ──────────────────────────────────────
        rc_all = _get_rc_all_cached()

        # ── Enrich dalam satu fungsi ──────────────────────────────
        df_ng = _enrich_ng(df_ng, rc_all, param_col)

        # ── KPI dihitung SEBELUM filter status ────────────────────
        df_ng_all = df_ng.copy()
        n_total = len(df_ng_all)
        n_open  = int((df_ng_all["_status"] == "Open").sum())
        n_inv   = int((df_ng_all["_status"] == "Investigated").sum())
        n_res   = int((df_ng_all["_status"] == "Resolved").sum())
        pct     = round((n_inv + n_res) / n_total * 100) if n_total else 0
        bclr    = "#16A34A" if pct == 100 else "#3B82F6"

        if status_filter != "Semua Status":
            df_ng = df_ng[df_ng["_status"] == status_filter]
        if df_ng.empty:
            st.info(f"Tidak ada NG dengan status **{status_filter}**.")
            return

        df_ng = df_ng.reset_index(drop=True)

        # KPI bar
        st.markdown(
            '<div style="background:white;border:1px solid #E2E8F0;border-radius:10px;'
            'padding:14px 20px;display:flex;align-items:center;gap:0;margin-bottom:14px;'
            'box-shadow:0 1px 2px rgba(15,23,42,.04);">'
            + f'<div style="flex:1;text-align:center;border-right:1px solid #F1F5F9;">'
            f'<div style="font-size:20px;font-weight:700;color:#0F172A;">{n_total}</div>'
            f'<div style="font-size:10px;color:#64748B;font-weight:600;margin-top:2px;'
            f'text-transform:uppercase;letter-spacing:.5px;">Total NG</div></div>'
            f'<div style="flex:1;text-align:center;border-right:1px solid #F1F5F9;">'
            f'<div style="font-size:20px;font-weight:700;color:#DC2626;">{n_open}</div>'
            f'<div style="font-size:10px;color:#64748B;font-weight:600;margin-top:2px;'
            f'text-transform:uppercase;letter-spacing:.5px;">Open</div></div>'
            f'<div style="flex:1;text-align:center;border-right:1px solid #F1F5F9;">'
            f'<div style="font-size:20px;font-weight:700;color:#D97706;">{n_inv}</div>'
            f'<div style="font-size:10px;color:#64748B;font-weight:600;margin-top:2px;'
            f'text-transform:uppercase;letter-spacing:.5px;">Investigated</div></div>'
            f'<div style="flex:1;text-align:center;border-right:1px solid #F1F5F9;">'
            f'<div style="font-size:20px;font-weight:700;color:#16A34A;">{n_res}</div>'
            f'<div style="font-size:10px;color:#64748B;font-weight:600;margin-top:2px;'
            f'text-transform:uppercase;letter-spacing:.5px;">Resolved</div></div>'
            f'<div style="flex:2;padding-left:20px;">'
            f'<div style="display:flex;justify-content:space-between;margin-bottom:5px;">'
            f'<span style="font-size:10px;color:#64748B;font-weight:600;'
            f'text-transform:uppercase;letter-spacing:.5px;">Progress</span>'
            f'<span style="font-size:11px;font-weight:700;color:#0F172A;">{pct}%</span></div>'
            f'<div style="background:#F1F5F9;border-radius:99px;height:5px;overflow:hidden;">'
            f'<div style="width:{pct}%;height:100%;background:{bclr};border-radius:99px;">'
            f'</div></div></div></div>',
            unsafe_allow_html=True
        )

        username   = st.session_state.get("username", "")
        group_cols = ["_date_str", "_shift", "_sampleno", "PartName", "ModelName"]

        # Pagination
        all_groups = list(df_ng.groupby(group_cols, sort=False))
        PAGE_SIZE  = 10
        n_groups   = len(all_groups)
        n_pages    = max(1, (n_groups + PAGE_SIZE - 1) // PAGE_SIZE)
        page_key   = "diag_list_page"
        if st.session_state.get(page_key, 0) >= n_pages:
            st.session_state[page_key] = 0
        cur_page = st.session_state.get(page_key, 0)

        pc1, pc2, pc3 = st.columns([1, 3, 1], gap="small")
        with pc1:
            if st.button("\u276e Sebelumnya", disabled=cur_page == 0, key="diag_prev", use_container_width=True):
                st.session_state[page_key] = cur_page - 1
                st.rerun()
        with pc2:
            st.markdown(
                f'<div style="text-align:center;font-size:12px;color:#64748B;padding-top:8px;">'  
                f'Showing {cur_page * PAGE_SIZE + 1}\u2013{min((cur_page + 1) * PAGE_SIZE, n_groups)} of {n_groups} groups</div>',
                unsafe_allow_html=True
            )
        with pc3:
            if st.button("Berikutnya \u276f", disabled=cur_page >= n_pages - 1, key="diag_next", use_container_width=True):
                st.session_state[page_key] = cur_page + 1
                st.rerun()

        page_groups = all_groups[cur_page * PAGE_SIZE : (cur_page + 1) * PAGE_SIZE]

        for grp_idx, (group_key, group_df) in enumerate(page_groups):
            real_idx = cur_page * PAGE_SIZE + grp_idx
            date_str, shift, sampleno, part, model = group_key
            n_ng     = len(group_df)
            n_g_open = int((group_df["_status"] == "Open").sum())
            n_g_res  = int((group_df["_status"] == "Resolved").sum())
            n_kp_ng  = int((group_df["_kp"] == "1").sum())
            icon     = "🟢" if n_g_open == 0 else ("🔴" if n_g_open == n_ng else "🟡")
            tbl_key  = f"tbl_{real_idx}"

            title = (
                f"{icon}  {part} — {model}"
                f"  \u00b7  Sample {sampleno}"
                f"  \u00b7  Shift {shift}  \u00b7  {date_str}"
                f"  \u00b7  {n_ng} NG"
                f"  \u00b7  {n_g_open} Open  \u00b7  {n_g_res} Resolved"
            )

            with st.expander(title, expanded=False):
                g      = group_df.reset_index(drop=True)
                df_tbl = g[["_ref", "_param", "_dev", "_kp",
                            "_status", "_category", "_role"]].copy()
                df_tbl.columns = [
                    "Ref", "Parameter", "Deviasi", "KP",
                    "Status", "Kategori Root Cause", "Role"
                ]

                def _row_style(row, _cols=df_tbl.columns):
                    styles = [""] * len(row)
                    styles[list(_cols).index("Status")] = STATUS_CLR.get(row["Status"], "")
                    return styles

                # Clear selection kalau ada flag dari save/delete sebelumnya
                if st.session_state.pop(f"clear_{tbl_key}", False):
                    if tbl_key in st.session_state:
                        del st.session_state[tbl_key]
                    # Reset bullet-point pts keys agar form re-init dari DB
                    for _ck in list(st.session_state.keys()):
                        if any(_ck.startswith(_pfx) for _pfx in
                               ("desc_n_","corr_n_","desc_pt_","corr_pt_","cat_","sts_","pic_")):
                            del st.session_state[_ck]

                event = st.dataframe(
                    df_tbl.style.apply(_row_style, axis=1),
                    use_container_width=True,
                    hide_index=True,
                    height=min(400, 42 + len(g) * 36),
                    selection_mode="multi-row",
                    on_select="rerun",
                    key=tbl_key,
                    column_config={
                        "KP": st.column_config.CheckboxColumn("KP", width="small"),
                        "Deviasi": st.column_config.TextColumn("Deviasi", width="small"),
                    }
                )

                sel_rows = [i for i in event.selection.rows if i < len(g)]

                if sel_rows:
                    # Ambil semua baris yang dipilih
                    sel_data  = [g.iloc[i] for i in sel_rows]
                    sel_keys  = [r["_rc_key"] for r in sel_data]
                    n_sel     = len(sel_data)

                    # Pre-populate form dari baris pertama yang punya RC tersimpan
                    first_rc  = next((rc_all[k] for k in sel_keys if k in rc_all), {})
                    safe_key  = str(abs(hash(tbl_key + str(sorted(sel_rows)))))[:8]

                    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
                    with st.container(border=True):
                        # Header — teks berbeda tergantung jumlah dipilih
                        if n_sel == 1:
                            row    = sel_data[0]
                            badge  = ROLE_BADGE.get(first_rc.get("inputted_role", ""), "")
                            kp_tag = "  \U0001f534 KP" if row["_kp"] == "1" else ""
                            st.markdown(
                                f'<div style="font-size:13px;font-weight:700;'
                                f'color:#0F172A;margin-bottom:3px;">'
                                f'{row["_ref"]} \u00b7 {row["_param"]}'
                                f'{kp_tag}&nbsp;&nbsp;{badge}</div>'
                                f'<div style="font-size:11px;color:#64748B;margin-bottom:10px;">'
                                f'Dev: <b style="color:#DC2626;">{row["_dev"]}</b>'
                                f'&nbsp;\u00b7&nbsp;{part} {model}'
                                f'&nbsp;\u00b7&nbsp;Shift {shift}'
                                f'&nbsp;\u00b7&nbsp;{date_str}'
                                f'&nbsp;\u00b7&nbsp;Sample {sampleno}</div>',
                                unsafe_allow_html=True
                            )
                        else:
                            refs_list = ", ".join(
                                f"{r['_ref']} · {r['_param']}" for r in sel_data
                            )
                            st.markdown(
                                f'<div style="background:#EFF6FF;border-radius:8px;'
                                f'padding:8px 12px;margin-bottom:10px;">'
                                f'<span style="font-size:13px;font-weight:700;color:#1D4ED8;">'
                                f'{n_sel} titik dipilih</span>'
                                f'<div style="font-size:11px;color:#3B82F6;margin-top:3px;'
                                f'line-height:1.6;">{refs_list}</div>'
                                f'<div style="font-size:10px;color:#64748B;margin-top:4px;">'
                                f'Form di bawah akan diterapkan ke semua titik yang dipilih.</div>'
                                f'</div>',
                                unsafe_allow_html=True
                            )

                        fc1, fc2 = st.columns(2)
                        with fc1:
                            category = st.selectbox(
                                "Kategori Root Cause", RC_CATEGORIES,
                                index=(RC_CATEGORIES.index(first_rc["category"])
                                       if first_rc.get("category") in RC_CATEGORIES
                                       else 0),
                                key=f"cat_{safe_key}"
                            )
                        with fc2:
                            fstatus = st.selectbox(
                                "Status Root Cause", RC_STATUSES,
                                index=(RC_STATUSES.index(first_rc["status"])
                                       if first_rc.get("status") in RC_STATUSES
                                       else 1),
                                key=f"sts_{safe_key}"
                            )
                        # ── Deskripsi Penyebab — dynamic bullet inputs ──
                        _desc_n_key = f"desc_n_{safe_key}"
                        if _desc_n_key not in st.session_state:
                            _ex_desc = first_rc.get("description", "")
                            _desc_pts = [p.strip() for p in _ex_desc.split("\n") if p.strip()]
                            st.session_state[_desc_n_key] = max(1, len(_desc_pts))
                            for _i, _p in enumerate(_desc_pts):
                                _pk = f"desc_pt_{safe_key}_{_i}"
                                if _pk not in st.session_state:
                                    st.session_state[_pk] = _p
                        _n_desc = st.session_state[_desc_n_key]

                        st.markdown(
                            '<div style="font-size:12px;font-weight:600;color:#374151;'
                            'margin-bottom:4px;">📝 Deskripsi Penyebab *</div>',
                            unsafe_allow_html=True
                        )
                        for _di in range(_n_desc):
                            _dc1, _dc2 = st.columns([12, 1])
                            with _dc1:
                                st.text_input(
                                    f"Poin {_di+1}",
                                    key=f"desc_pt_{safe_key}_{_di}",
                                    placeholder=f"Penyebab {_di+1}...",
                                    label_visibility="collapsed",
                                )
                            with _dc2:
                                if _n_desc > 1 and st.button(
                                    "x", key=f"desc_del_{safe_key}_{_di}",
                                    use_container_width=True
                                ):
                                    for _j in range(_di, _n_desc - 1):
                                        st.session_state[f"desc_pt_{safe_key}_{_j}"] = \
                                            st.session_state.get(f"desc_pt_{safe_key}_{_j+1}", "")
                                    st.session_state[_desc_n_key] -= 1
                                    st.rerun()
                        if st.button("Tambah Poin", key=f"desc_add_{safe_key}"):
                            st.session_state[_desc_n_key] += 1
                            st.rerun()

                        # ── Tindakan Perbaikan — dynamic bullet inputs ──
                        _corr_n_key = f"corr_n_{safe_key}"
                        if _corr_n_key not in st.session_state:
                            _ex_corr = first_rc.get("corrective_action", "")
                            _corr_pts = [p.strip() for p in _ex_corr.split("\n") if p.strip()]
                            st.session_state[_corr_n_key] = max(1, len(_corr_pts))
                            for _i, _p in enumerate(_corr_pts):
                                _pk = f"corr_pt_{safe_key}_{_i}"
                                if _pk not in st.session_state:
                                    st.session_state[_pk] = _p
                        _n_corr = st.session_state[_corr_n_key]

                        st.markdown(
                            '<div style="font-size:12px;font-weight:600;color:#374151;'
                            'margin-top:6px;margin-bottom:4px;">🔧 Tindakan Perbaikan</div>',
                            unsafe_allow_html=True
                        )
                        for _ci in range(_n_corr):
                            _cc1, _cc2 = st.columns([12, 1])
                            with _cc1:
                                st.text_input(
                                    f"Tindakan {_ci+1}",
                                    key=f"corr_pt_{safe_key}_{_ci}",
                                    placeholder=f"Tindakan {_ci+1}...",
                                    label_visibility="collapsed",
                                )
                            with _cc2:
                                if _n_corr > 1 and st.button(
                                    "x", key=f"corr_del_{safe_key}_{_ci}",
                                    use_container_width=True
                                ):
                                    for _j in range(_ci, _n_corr - 1):
                                        st.session_state[f"corr_pt_{safe_key}_{_j}"] = \
                                            st.session_state.get(f"corr_pt_{safe_key}_{_j+1}", "")
                                    st.session_state[_corr_n_key] -= 1
                                    st.rerun()
                        if st.button("Tambah Tindakan", key=f"corr_add_{safe_key}"):
                            st.session_state[_corr_n_key] += 1
                            st.rerun()

                        # Kumpulkan nilai sebelum save
                        description = "\n".join(
                            st.session_state.get(f"desc_pt_{safe_key}_{_i}", "").strip()
                            for _i in range(_n_desc)
                            if st.session_state.get(f"desc_pt_{safe_key}_{_i}", "").strip()
                        )
                        corrective = "\n".join(
                            st.session_state.get(f"corr_pt_{safe_key}_{_i}", "").strip()
                            for _i in range(_n_corr)
                            if st.session_state.get(f"corr_pt_{safe_key}_{_i}", "").strip()
                        )

                        pic = st.text_input(
                            "Penanggung Jawab",
                            value=first_rc.get("pic", ""),
                            placeholder="Nama penanggung jawab...",
                            key=f"pic_{safe_key}"
                        )

                        btn_lbl = f"\U0001f4be Simpan ({n_sel} titik)" if n_sel > 1 else "\U0001f4be Simpan"
                        n_deletable = sum(1 for k in sel_keys if k in rc_all)

                        cs, cd = st.columns([3, 1])
                        with cs:
                            if st.button(btn_lbl, type="primary",
                                         use_container_width=True, key=f"save_{safe_key}"):
                                if not description.strip():
                                    st.warning("Deskripsi wajib diisi.")
                                else:
                                    _role = st.session_state.get("role", "")
                                    for row in sel_data:
                                        save_root_cause({
                                            "rc_key":      row["_rc_key"],
                                            "date":        row["_date_str"],
                                            "shift":       row["_shift"],
                                            "sampleno":    row["_sampleno"],
                                            "part":        row["PartName"],
                                            "model":       row["ModelName"],
                                            "ref":         row["_ref"],
                                            "id_ukur":     str(row.get("ID", "")),
                                            "parameter":   row["_param"],
                                            "deviation":   row["_dev"],
                                            "category":    category,
                                            "description": description.strip(),
                                            "corrective_action": corrective.strip(),
                                            "status":      fstatus,
                                            "inputted_by": username,
                                            "inputted_role": _role,
                                            "pic":         pic.strip(),
                                        })
                                    st.success(f"\u2713 {n_sel} titik tersimpan")
                                    _invalidate_rc_cache()
                                    st.session_state[f"clear_{tbl_key}"] = True
                                    st.rerun()
                        with cd:
                            if n_deletable > 0:
                                del_lbl = f"\U0001f5d1 Hapus ({n_deletable})" if n_deletable > 1 else "\U0001f5d1 Hapus"
                                if st.button(del_lbl, use_container_width=True,
                                             key=f"del_{safe_key}"):
                                    for k in sel_keys:
                                        if k in rc_all:
                                            delete_root_cause(rc_all[k]["id"])
                                    _invalidate_rc_cache()
                                    st.session_state[f"clear_{tbl_key}"] = True
                                    st.rerun()
                else:
                    st.caption("\U0001f446 Pilih satu atau lebih baris untuk input root cause.")

    # ── Helper: filter rcs sesuai filter pills ─────────────────────
    def _filter_rcs(self, rcs: list) -> list:
        """Apply semua filter selectbox ke list root causes (Analytics & Riwayat)."""
        from datetime import date, datetime, timedelta

        f_time  = st.session_state.get("diag_time_sel",  "Semua Periode")
        f_shift = st.session_state.get("diag_shift_sel", "Semua Shift")
        f_combo = st.session_state.get("diag_combo_sel", "Semua Part & Model")
        f_sno   = st.session_state.get("diag_sno_sel",   "Semua Sample")
        f_ref   = st.session_state.get("diag_ref_sel",   "Semua Ref / Point")
        f_param = st.session_state.get("diag_param_sel", "Semua Parameter")

        # pecah combo → part & model
        f_part, f_model = "All", "All"
        if f_combo and f_combo != "Semua Part & Model":
            _sp = f_combo.split(" · ", 1)
            if len(_sp) == 2:
                f_part, f_model = _sp[0], _sp[1]

        today = date.today()
        if f_time == "Hari Ini":
            start = today
        elif f_time == "7 Hari Terakhir":
            start = today - timedelta(days=6)
        elif f_time == "30 Hari Terakhir":
            start = today - timedelta(days=29)
        else:
            start = None

        shift_val_map = {"Shift 1": "1", "Shift 2": "2", "Shift 3": "3"}

        def _parse_date(s):
            try:
                return datetime.strptime(s, "%d %b %Y").date()
            except Exception:
                return None

        out = []
        for r in rcs:
            if start is not None:
                d = _parse_date(r.get("date", ""))
                if d is None or d < start:
                    continue
            if f_shift != "Semua Shift":
                if str(r.get("shift", "")) != shift_val_map.get(f_shift, f_shift):
                    continue
            if f_part != "All" and r.get("part", "") != f_part:
                continue
            if f_model != "All" and r.get("model", "") != f_model:
                continue
            if f_sno != "Semua Sample" and str(r.get("sampleno", "")) != f_sno:
                continue
            if f_ref != "Semua Ref / Point" and str(r.get("ref", "")) != f_ref:
                continue
            if f_param != "Semua Parameter" and str(r.get("parameter", "")) != f_param:
                continue
            out.append(r)
        return out

    def _compute_rc_stats(self, rcs: list) -> dict:
        """Hitung stats dari list rcs yang sudah difilter."""
        cat_counts, pm_cat, ref_cat, ref_counts = {}, {}, {}, {}
        for r in rcs:
            cat = r.get("category", "")
            if not cat:
                continue
            part  = r.get("part",  "")
            model = r.get("model", "")
            ref   = r.get("ref",   "")
            param = r.get("parameter", "")
            pm    = f"{part} {model}".strip() if part or model else "Unknown"
            ref_label = f"{ref} · {param}" if ref else "Unknown"

            cat_counts[cat] = cat_counts.get(cat, 0) + 1
            pm_cat.setdefault(pm, {})
            pm_cat[pm][cat] = pm_cat[pm].get(cat, 0) + 1
            ref_cat.setdefault(ref_label, {})
            ref_cat[ref_label][cat] = ref_cat[ref_label].get(cat, 0) + 1
            ref_counts[ref_label] = ref_counts.get(ref_label, 0) + 1

        return {
            "category_counts": cat_counts,
            "pm_category":     pm_cat,
            "ref_category":    ref_cat,
            "ref_counts":      ref_counts,
        }

    def _compute_shift_param(self, df) -> dict:
        """Hitung NG count per Shift x Parameter dari data CMM aktual."""
        if df.empty:
            return {}
        param_col = "point" if "point" in df.columns else "Parameter"
        df_ng = df[df["Judgement"] == "NG"].copy()
        if df_ng.empty:
            return {}
        result = {}
        for _, row in df_ng.iterrows():
            shift = str(row.get("Shift", "?"))
            param = str(row.get(param_col, "?"))
            result.setdefault(shift, {})
            result[shift][param] = result[shift].get(param, 0) + 1
        return result

    # —— ANALYTICS — @st.fragment + session_state cache ——
    @st.fragment
    # ════════════════════════════════════════════════════════════
    # TOP NG — Ranking titik NG terbanyak + inline RC form
    # ════════════════════════════════════════════════════════════
    def _render_top_ng(self):
        df, status_filter = self._render_filters(show_status=True)
        if df.empty:
            st.info("Tidak ada data.")
            return

        param_col = "point" if "point" in df.columns else "Parameter"
        df_ng_raw = df[df["Judgement"] == "NG"].copy()
        if df_ng_raw.empty:
            st.success("Tidak ada NG pada periode ini.")
            return

        # Cache key berdasarkan filter aktif
        _cache_key = f"topng_df_{hash(df_ng_raw.shape)}{len(df_ng_raw)}"
        rc_all     = _get_rc_all_cached()

        if st.session_state.get("topng_cache_key") != _cache_key:
            df_ng  = _enrich_ng(df_ng_raw, rc_all, param_col)
            grp    = df_ng.groupby(["PartName","ModelName","_ref","_param","_sampleno"])
            _rows  = []
            for (part, model, ref, param, sno), g in grp:
                n_ng      = len(g)
                is_kp     = (g["_kp"] == "1").any()
                worst_dev = g["Deviation"].abs().max() if "Deviation" in g.columns else None
                last_row  = g.sort_values("Date", ascending=False).iloc[0]
                n_open = int((g["_status"]=="Open").sum())
                n_inv  = int((g["_status"]=="Investigated").sum())
                n_res  = int((g["_status"]=="Resolved").sum())
                if n_open == n_ng:    titik_status = "Belum Ada Root Cause"
                elif n_open > 0:      titik_status = "Partial Open"
                elif n_inv > 0:       titik_status = "Investigated"
                else:                 titik_status = "Resolved"
                _rows.append({
                    "part": part, "model": model, "ref": ref, "param": param,
                    "sampleno": sno,
                    "n_ng": n_ng, "is_kp": is_kp, "worst_dev": worst_dev,
                    "last_date": last_row["_date_str"], "last_shift": last_row["_shift"],
                    "n_open": n_open, "n_inv": n_inv, "n_res": n_res,
                    "titik_status": titik_status,
                })
            st.session_state["topng_df_cache"]  = pd.DataFrame(_rows).sort_values("n_ng", ascending=False).reset_index(drop=True)
            st.session_state["topng_df_ng"]     = df_ng
            st.session_state["topng_cache_key"] = _cache_key

        df_top = st.session_state["topng_df_cache"]
        df_ng  = st.session_state["topng_df_ng"]
        username = st.session_state.get("username", "Operator")

        @st.fragment
        def _render_list_fragment():
            _df_top = df_top.copy()
            _status_filter = status_filter

            # ── Apply status filter ───────────────────────────────
            if _status_filter == "Open":
                _df_top = _df_top[_df_top["n_open"] > 0]
            elif _status_filter == "Investigated":
                _df_top = _df_top[_df_top["n_inv"] > 0]
            elif _status_filter == "Resolved":
                _df_top = _df_top[_df_top["n_res"] > 0]

            if _df_top.empty:
                st.info("Tidak ada titik untuk filter ini.")
                return

            n_belum = int((_df_top["titik_status"]=="Belum Ada Root Cause").sum())
            n_kp_t  = int(_df_top["is_kp"].sum())
            st.markdown(
                f'<div style="display:flex;gap:8px;margin-bottom:12px;">'
                f'<span style="background:#F8FAFC;color:#0F172A;border-radius:99px;padding:3px 12px;font-size:11px;font-weight:700;">{len(_df_top)} titik NG unik</span>'
                f'<span style="background:#FEE2E2;color:#DC2626;border-radius:99px;padding:3px 12px;font-size:11px;font-weight:700;">{n_belum} Belum Ada Root Cause</span>'
                f'<span style="background:#EFF6FF;color:#1D4ED8;border-radius:99px;padding:3px 12px;font-size:11px;font-weight:700;">{n_kp_t} KP</span>'
                f'</div>',
                unsafe_allow_html=True
            )

            PAGE_SIZE = 10
            n_pages   = max(1, -(-len(_df_top) // PAGE_SIZE))
            if n_pages > 1:
                pc1, pc2, pc3 = st.columns([1, 3, 1], gap="small")
                cur_page = max(1, min(st.session_state.get("topng_page", 1), n_pages))
                with pc1:
                    if st.button("Sebelumnya", key="topng_prev", disabled=cur_page<=1,
                                 use_container_width=True):
                        st.session_state.topng_page = cur_page - 1
                        st.session_state.topng_open = None
                with pc2:
                    st.markdown(
                        f'<div style="text-align:center;font-size:12px;color:#64748B;padding-top:6px;">'
                        f'Halaman <b>{cur_page}</b> / <b>{n_pages}</b></div>',
                        unsafe_allow_html=True
                    )
                with pc3:
                    if st.button("Berikutnya", key="topng_next", disabled=cur_page>=n_pages,
                                 use_container_width=True):
                        st.session_state.topng_page = cur_page + 1
                        st.session_state.topng_open = None
            else:
                cur_page = 1

            df_page  = _df_top.iloc[(cur_page-1)*PAGE_SIZE : cur_page*PAGE_SIZE]
            open_tid = st.session_state.get("topng_open")

            STATUS_STYLE = {
                "Belum Ada Root Cause":  ("#DC2626","#FEE2E2"),
                "Partial Open":  ("#D97706","#FEF3C7"),
                "Investigated":  ("#0284C7","#E0F2FE"),
                "Resolved":      ("#16A34A","#DCFCE7"),
            }

            for rank, (_, row) in enumerate(df_page.iterrows(), start=(cur_page-1)*PAGE_SIZE+1):
                tid     = f"topng_{row['part']}_{row['model']}_{row['ref']}_{row['param']}_{row['sampleno']}"
                is_open = open_tid == tid
                fc, bg  = STATUS_STYLE.get(row["titik_status"], ("#64748B","#F8FAFC"))
                kp_tag  = '<span style="background:#EFF6FF;color:#1D4ED8;font-size:9px;font-weight:700;padding:1px 6px;border-radius:99px;margin-left:4px;">KP</span>' if row["is_kp"] else ""
                dev_txt = f'<b style="color:#DC2626;">{row["worst_dev"]:+.4f}</b>' if row["worst_dev"] is not None else "—"
                border  = "#EF4444" if row["n_open"] > 0 else "#E2E8F0"

                st.markdown(
                    f'<div style="background:white;border:1px solid {border};'
                    f'border-left:4px solid {border};border-radius:10px;'
                    f'padding:10px 16px;margin-bottom:2px;">'
                    f'<div style="display:flex;align-items:center;justify-content:space-between;">'
                    f'<div style="display:flex;align-items:center;gap:10px;">'
                    f'<span style="font-size:18px;font-weight:800;color:#CBD5E1;min-width:28px;">#{rank}</span>'
                    f'<div>'
                    f'<div style="font-size:13px;font-weight:700;color:#0F172A;">{row["ref"]} · {row["param"]}{kp_tag}</div>'
                    f'<div style="font-size:11px;color:#64748B;margin-top:1px;">'
                    f'<b>{row["part"]} {row["model"]}</b> · Sample <b>{row["sampleno"]}</b>'
                    f' · Terakhir {row["last_date"]} S{row["last_shift"]} · Worst dev: {dev_txt}</div>'
                    f'</div></div>'
                    f'<div style="display:flex;align-items:center;gap:8px;">'
                    f'<span style="background:#0F172A;color:#fff;font-size:14px;font-weight:800;'
                    f'padding:3px 10px;border-radius:99px;">{row["n_ng"]} NG</span>'
                    f'<span style="background:{bg};color:{fc};font-size:10px;font-weight:700;'
                    f'padding:2px 9px;border-radius:99px;">{row["titik_status"]}</span>'
                    f'</div></div></div>',
                    unsafe_allow_html=True
                )

                c_btn, _ = st.columns([1, 5])
                with c_btn:
                    if st.button(
                        "Tutup" if is_open else "Isi Root Cause",
                        key=f"topng_btn_{tid}",
                        use_container_width=False,
                        type="secondary" if is_open else "primary"
                    ):
                        st.session_state.topng_open = None if is_open else tid
                        st.rerun()

                if is_open:
                    g_titik = df_ng[
                        (df_ng["PartName"]==row["part"]) & (df_ng["ModelName"]==row["model"]) &
                        (df_ng["_ref"]==row["ref"]) & (df_ng["_param"]==row["param"]) &
                        (df_ng["_sampleno"]==row["sampleno"])
                    ].sort_values("Date", ascending=False)
                    with st.container():
                        self._render_topng_form(g_titik, rc_all, username, tid, param_col)

                st.markdown('<div style="height:2px;"></div>', unsafe_allow_html=True)

        _render_list_fragment()


    def _render_topng_form(self, g: pd.DataFrame, rc_all: dict,
                           username: str, tid: str, param_col: str):
        """Form RC untuk titik dari Top NG — tabel dengan semua rows otomatis tercentang."""
        tbl_key  = f"topng_tbl_{tid}"

        if st.session_state.pop(f"clear_{tbl_key}", False):
            if tbl_key in st.session_state:
                del st.session_state[tbl_key]
            for _ck in list(st.session_state.keys()):
                if any(_ck.startswith(_pfx) for _pfx in
                       ("desc_n_","corr_n_","desc_pt_","corr_pt_","cat_","sts_","pic_")):
                    del st.session_state[_ck]

        # Pre-select semua rows saat pertama kali dibuka
        if tbl_key not in st.session_state:
            st.session_state[tbl_key] = {
                "selection": {"rows": list(range(len(g))), "columns": []}
            }

        with st.container(border=True):
            STATUS_CLR = {"Open":"#EF4444","Investigated":"#F59E0B","Resolved":"#22C55E"}
            tbl_data = g[["_date_str","_shift","_sampleno","_dev","_status","_kp"]].copy()
            tbl_data.columns = ["Tanggal","Shift","Sample","Deviasi","Status","KP"]

            def _row_style_t(row):
                clr = STATUS_CLR.get(row["Status"], "#94A3B8")
                return [f"border-left:3px solid {clr}"]*len(row)

            event = st.dataframe(
                tbl_data.style.apply(_row_style_t, axis=1),
                use_container_width=True, hide_index=True,
                height=min(380, 42 + len(g)*36),
                selection_mode="multi-row", on_select="rerun",
                key=tbl_key,
                column_config={
                    "KP": st.column_config.CheckboxColumn("KP", width="small"),
                    "Deviasi": st.column_config.TextColumn("Deviasi", width="small"),
                }
            )

            sel_rows = [i for i in event.selection.rows if i < len(g)]
            if not sel_rows:
                st.caption("Pilih baris untuk mengisi Root Cause.")
                return

            sel_data = [g.iloc[i] for i in sel_rows]
            sel_keys = [r["_rc_key"] for r in sel_data]
            n_sel    = len(sel_data)
            first_rc = next((rc_all[k] for k in sel_keys if k in rc_all), {})
            safe_key = str(abs(hash(tbl_key + str(sorted(sel_rows)))))[:8]

            # Form fields
            fc1, fc2 = st.columns(2)
            with fc1:
                category = st.selectbox("Kategori Root Cause", RC_CATEGORIES,
                    index=(RC_CATEGORIES.index(first_rc["category"])
                           if first_rc.get("category") in RC_CATEGORIES else 0),
                    key=f"cat_{safe_key}")
            with fc2:
                fstatus = st.selectbox("Status Root Cause", RC_STATUSES,
                    index=(RC_STATUSES.index(first_rc["status"])
                           if first_rc.get("status") in RC_STATUSES else 1),
                    key=f"sts_{safe_key}")

            # Bullet-point deskripsi
            _desc_n_key = f"desc_n_{safe_key}"
            if _desc_n_key not in st.session_state:
                _pts = [p.strip() for p in first_rc.get("description","").split("\n") if p.strip()]
                st.session_state[_desc_n_key] = max(1, len(_pts))
                for _i, _p in enumerate(_pts):
                    if f"desc_pt_{safe_key}_{_i}" not in st.session_state:
                        st.session_state[f"desc_pt_{safe_key}_{_i}"] = _p
            _n_desc = st.session_state[_desc_n_key]
            st.markdown('<div style="font-size:11px;font-weight:600;color:#374151;margin:8px 0 3px;">📝 Deskripsi Penyebab *</div>', unsafe_allow_html=True)
            for _di in range(_n_desc):
                _dc1, _dc2 = st.columns([12,1])
                with _dc1:
                    st.text_input(f"Poin {_di+1}", key=f"desc_pt_{safe_key}_{_di}",
                                  placeholder=f"Penyebab {_di+1}...", label_visibility="collapsed")
                with _dc2:
                    if _n_desc > 1 and st.button("x", key=f"desc_del_{safe_key}_{_di}", use_container_width=True):
                        for _j in range(_di, _n_desc-1):
                            st.session_state[f"desc_pt_{safe_key}_{_j}"] = st.session_state.get(f"desc_pt_{safe_key}_{_j+1}","")
                        st.session_state[_desc_n_key] -= 1; st.rerun()
            _, _btn_desc = st.columns([6,2])
            with _btn_desc:
                if st.button("Tambah Poin", key=f"desc_add_{safe_key}", use_container_width=True):
                    st.session_state[_desc_n_key] += 1; st.rerun()

            # Bullet-point tindakan
            _corr_n_key = f"corr_n_{safe_key}"
            if _corr_n_key not in st.session_state:
                _pts2 = [p.strip() for p in first_rc.get("corrective_action","").split("\n") if p.strip()]
                st.session_state[_corr_n_key] = max(1, len(_pts2))
                for _i2, _p2 in enumerate(_pts2):
                    if f"corr_pt_{safe_key}_{_i2}" not in st.session_state:
                        st.session_state[f"corr_pt_{safe_key}_{_i2}"] = _p2
            _n_corr = st.session_state[_corr_n_key]
            st.markdown('<div style="font-size:11px;font-weight:600;color:#374151;margin:8px 0 3px;">🔧 Tindakan Perbaikan</div>', unsafe_allow_html=True)
            for _ci in range(_n_corr):
                _cc1, _cc2 = st.columns([12,1])
                with _cc1:
                    st.text_input(f"Tindakan {_ci+1}", key=f"corr_pt_{safe_key}_{_ci}",
                                  placeholder=f"Tindakan {_ci+1}...", label_visibility="collapsed")
                with _cc2:
                    if _n_corr > 1 and st.button("x", key=f"corr_del_{safe_key}_{_ci}", use_container_width=True):
                        for _j in range(_ci, _n_corr-1):
                            st.session_state[f"corr_pt_{safe_key}_{_j}"] = st.session_state.get(f"corr_pt_{safe_key}_{_j+1}","")
                        st.session_state[_corr_n_key] -= 1; st.rerun()
            _, _btn_corr = st.columns([6,2])
            with _btn_corr:
                if st.button("Tambah Tindakan", key=f"corr_add_{safe_key}", use_container_width=True):
                    st.session_state[_corr_n_key] += 1; st.rerun()

            description = "\n".join(
                st.session_state.get(f"desc_pt_{safe_key}_{_i}","").strip()
                for _i in range(_n_desc)
                if st.session_state.get(f"desc_pt_{safe_key}_{_i}","").strip()
            )
            corrective = "\n".join(
                st.session_state.get(f"corr_pt_{safe_key}_{_i}","").strip()
                for _i in range(_n_corr)
                if st.session_state.get(f"corr_pt_{safe_key}_{_i}","").strip()
            )
            pic = st.text_input("Penanggung Jawab", value=first_rc.get("pic",""),
                                placeholder="Nama penanggung jawab...", key=f"pic_{safe_key}")

            n_del  = sum(1 for k in sel_keys if k in rc_all)
            cs, cd = st.columns([3,1])
            with cs:
                if st.button(f"Simpan ({n_sel} baris)", type="primary",
                             use_container_width=True, key=f"save_{safe_key}"):
                    if not description.strip():
                        st.warning("Deskripsi wajib diisi.")
                    else:
                        _role = st.session_state.get("role","")
                        for row in sel_data:
                            save_root_cause({
                                "rc_key": row["_rc_key"], "date": row["_date_str"],
                                "shift": row["_shift"], "sampleno": row["_sampleno"],
                                "part": row["PartName"], "model": row["ModelName"],
                                "ref": row["_ref"], "id_ukur": str(row.get("ID","")),
                                "parameter": row["_param"], "deviation": row["_dev"],
                                "category": category, "description": description.strip(),
                                "corrective_action": corrective.strip(),
                                "status": fstatus, "inputted_by": username,
                                "inputted_role": _role, "pic": pic.strip(),
                            })
                        st.success(f"Tersimpan ({n_sel} baris)")
                        _invalidate_rc_cache()
                        st.session_state["topng_open"] = None
                        st.session_state["topng_cache_key"] = None
                        st.rerun()
            with cd:
                if n_del > 0:
                    if st.button(f"Hapus ({n_del})" if n_del>1 else "Hapus",
                                 use_container_width=True, key=f"del_{safe_key}"):
                        for k in sel_keys:
                            if k in rc_all:
                                from local_db import delete_root_cause
                                delete_root_cause(rc_all[k]["id"])
                        _invalidate_rc_cache()
                        st.session_state[f"clear_{tbl_key}"] = True; st.rerun()


    def _render_analytics(self):
        import time as _time
        df, _ = self._render_filters(show_status=False)

        t     = st.session_state.get("diag_time_sel",  "All")
        s     = st.session_state.get("diag_shift_sel", "All Shift")
        combo = st.session_state.get("diag_combo_sel", "— All Part & Model —")
        sno   = st.session_state.get("diag_sno_sel",   "All")
        ref   = st.session_state.get("diag_ref_sel",   "All")
        param = st.session_state.get("diag_param_sel", "All")
        TTL   = 300

        # Cache RC stats + TTL
        stats_key = f"diag_stats_{t}_{s}_{combo}_{sno}_{ref}_{param}"
        ts_key    = f"{stats_key}_ts"
        dirty     = st.session_state.pop("diag_rc_dirty", False)
        if stats_key not in st.session_state or dirty or \
           _time.time() - st.session_state.get(ts_key, 0) > TTL:
            rcs_filtered = self._filter_rcs(get_root_causes())
            st.session_state[stats_key] = self._compute_rc_stats(rcs_filtered)
            st.session_state[ts_key]    = _time.time()

        # Cache Shift x Param dari data aktual + TTL
        sp_key    = f"diag_sp_{t}_{s}_{combo}_{sno}_{ref}_{param}"
        sp_ts_key = f"{sp_key}_ts"
        if sp_key not in st.session_state or \
           _time.time() - st.session_state.get(sp_ts_key, 0) > TTL:
            st.session_state[sp_key]    = self._compute_shift_param(df)
            st.session_state[sp_ts_key] = _time.time()

        stats       = st.session_state[stats_key]
        cat_counts  = stats["category_counts"]
        pm_cat      = stats["pm_category"]
        ref_cat     = stats.get("ref_category", {})
        ref_counts  = stats.get("ref_counts", {})
        shift_param = st.session_state[sp_key]

        # —— Pareto RC ——
        if not cat_counts:
            st.info("Belum ada root cause untuk filter ini. Isi di tab Isi Root Cause dulu.")
        else:
            sorted_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)
            labels = [c[0] for c in sorted_cats]
            values = [c[1] for c in sorted_cats]
            total  = sum(values)
            run, cum = 0, []
            for v in values:
                run += v
                cum.append(round(run / total * 100, 1))
            st_echarts({
                "title": {"text": "Pareto Root Cause", "left": 12, "top": 8,
                          "textStyle": {"fontSize": 13, "fontWeight": 700, "color": "#0F172A"}},
                "grid": {"top": 50, "right": 60, "bottom": 60, "left": 40},
                "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                "legend": {"data": ["Jumlah", "Cumulative %"], "top": 10, "right": 10,
                           "textStyle": {"fontSize": 11}},
                "xAxis": {"type": "category", "data": labels,
                          "axisLabel": {"rotate": 20, "fontSize": 11}, "axisTick": {"show": False}},
                "yAxis": [
                    {"type": "value", "name": "Jumlah", "axisLabel": {"fontSize": 10},
                     "splitLine": {"lineStyle": {"color": "#F1F5F9", "type": "dashed"}}},
                    {"type": "value", "name": "Cumulative %", "max": 100,
                     "axisLabel": {"formatter": "{value}%", "fontSize": 10}, "splitLine": {"show": False}},
                ],
                "series": [
                    {"name": "Jumlah", "type": "bar", "data": values,
                     "itemStyle": {"color": "#E24B4A", "borderRadius": [4, 4, 0, 0]},
                     "label": {"show": True, "position": "top", "fontSize": 11, "fontWeight": 600}},
                    {"name": "Cumulative %", "type": "line", "data": cum, "yAxisIndex": 1,
                     "symbol": "circle", "symbolSize": 7,
                     "lineStyle": {"color": "#F59E0B", "width": 2}, "itemStyle": {"color": "#F59E0B"},
                     "label": {"show": True, "formatter": "{c}%", "fontSize": 9, "color": "#D97706"}},
                ],
            }, height="300px", key="diag_pareto")

        st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)

        h1, h2 = st.columns(2, gap="medium")
        with h1:
            st.markdown('<div style="font-size:13px;font-weight:600;color:#0F172A;margin-bottom:8px;">Part+Model × Kategori Root Cause</div>',
                        unsafe_allow_html=True)
            if pm_cat:
                self._heatmap(pm_cat, RC_CATEGORIES, sorted(pm_cat.keys()), "diag_hm_pm")
            else:
                st.info("Belum ada data Root Cause.")
        with h2:
            st.markdown('<div style="font-size:13px;font-weight:600;color:#0F172A;margin-bottom:8px;">Shift × Parameter NG</div>',
                        unsafe_allow_html=True)
            if shift_param:
                all_params = {}
                for sh, params in shift_param.items():
                    for p, v in params.items():
                        all_params[p] = all_params.get(p, 0) + v
                top_params = [p for p, _ in sorted(all_params.items(), key=lambda x: -x[1])[:15]]
                shifts     = sorted(shift_param.keys())
                self._heatmap(shift_param, top_params, shifts, "diag_hm_sp")
            else:
                st.info("Belum ada data NG.")

        st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)

        # ── Row 2: Top Ref NG + Heatmap Ref × Kategori ────────────
        r2a, r2b = st.columns(2, gap="medium")

        with r2a:
            st.markdown('<div style="font-size:13px;font-weight:600;color:#0F172A;margin-bottom:8px;">Top Titik NG Berulang</div>',
                        unsafe_allow_html=True)
            if ref_counts:
                # Exclude ref yang "-", kosong, atau "nan"
                EXCLUDE = {"-", "", "nan", "none", "-·", "· "}
                ref_counts_f = {k: v for k, v in ref_counts.items()
                                if k.split(" · ")[0].strip() not in EXCLUDE}
                top_refs = sorted(ref_counts_f.items(), key=lambda x: -x[1])[:15]
                labels_r = [x[0] for x in reversed(top_refs)]
                values_r = [x[1] for x in reversed(top_refs)]
                h_ref    = max(300, len(labels_r) * 28 + 60)
                st_echarts({
                    "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                    "grid":    {"top": 12, "right": 60, "bottom": 8, "left": 8,
                                "containLabel": True},
                    "xAxis":   {"type": "value"},
                    "yAxis":   {"type": "category", "data": labels_r,
                                "axisLabel": {"fontSize": 9}},
                    "dataZoom": [{"type": "slider", "yAxisIndex": 0,
                                  "start": max(0, 100 - round(10/max(len(labels_r),1)*100)),
                                  "end": 100, "width": 15, "right": 5,
                                  "borderColor": "transparent",
                                  "fillerColor": "rgba(239,68,68,0.15)",
                                  "handleStyle": {"color": "#EF4444"}}],
                    "series": [{
                        "type": "bar",
                        "data": values_r,
                        "itemStyle": {"color": "#EF4444", "borderRadius": [0, 4, 4, 0]},
                        "label": {"show": True, "position": "right",
                                  "fontSize": 10, "fontWeight": 600},
                    }],
                }, height=f"{h_ref}px", key="diag_top_ref")
            else:
                st.info("Belum ada data Root Cause.")

        with r2b:
            st.markdown('<div style="font-size:13px;font-weight:600;color:#0F172A;margin-bottom:8px;">Ref/Titik × Kategori Root Cause</div>',
                        unsafe_allow_html=True)
            if ref_cat:
                EXCLUDE = {"-", "", "nan", "none"}
                ref_counts_f2 = {k: v for k, v in ref_counts.items()
                                 if k.split(" · ")[0].strip() not in EXCLUDE}
                top_ref_keys = [x[0] for x in sorted(ref_counts_f2.items(),
                                key=lambda x: -x[1])[:15]]
                h_hm = max(300, len(top_ref_keys) * 28 + 100)
                self._heatmap(ref_cat, RC_CATEGORIES, top_ref_keys, "diag_hm_ref",
                              height=h_hm)

    def _heatmap(self, data_dict, col_keys, row_keys, chart_key, height=None):
        hm, mv = [], 0
        for ri, rk in enumerate(row_keys):
            for ci, ck in enumerate(col_keys):
                v = data_dict.get(rk, {}).get(ck, 0)
                if v > 0:
                    hm.append([ci, ri, v])
                    mv = max(mv, v)
        if not hm:
            st.info("Belum ada data.")
            return
        h = height if height else max(160, len(row_keys) * 34 + 100)
        st_echarts({
            "grid": {"top": 20, "right": 10, "bottom": 90, "left": 80},
            "tooltip": {"formatter": JsCode(
                "function(p){return p.value&&p.value[2]>0?(p.name+'<br/>'+p.value[2]+' kasus'):''}")},
            "xAxis": {"type": "category", "data": col_keys,
                      "axisLabel": {"rotate": 35, "fontSize": 9}, "axisTick": {"show": False},
                      "splitArea": {"show": True}},
            "yAxis": {"type": "category", "data": row_keys,
                      "axisLabel": {"fontSize": 9}, "splitArea": {"show": True}},
            "visualMap": {"min": 0, "max": mv or 1, "calculable": True,
                          "orient": "horizontal", "left": "center", "bottom": 5,
                          "inRange": {"color": ["#FFF7F7", "#FECACA", "#EF4444", "#7F1D1D"]},
                          "textStyle": {"fontSize": 9}},
            "series": [{"type": "heatmap", "data": hm,
                        "label": {"show": True, "fontSize": 9, "fontWeight": 600}}],
        }, height=f"{h}px", key=chart_key)

    @st.fragment
    def _render_history(self):
        self._render_filters(show_status=False)

        all_rcs = get_root_causes()
        rcs     = self._filter_rcs(all_rcs)

        if not rcs:
            st.info("Belum ada root cause tersimpan untuk filter ini.")
            return

        st.markdown(
            f'<div style="font-size:13px;font-weight:600;color:#0F172A;'
            f'margin-bottom:10px;">📚 {len(rcs)} root cause tersimpan</div>',
            unsafe_allow_html=True
        )

        df_rc = pd.DataFrame(rcs)
        show_cols = [
            "date", "shift", "sampleno", "part", "model", "ref", "parameter",
            "deviation", "category", "description", "corrective_action",
            "status", "inputted_role", "pic", "updated_at"
        ]
        show_cols = [c for c in show_cols if c in df_rc.columns]
        df_show   = df_rc[show_cols].copy()

        rename_map = {
            "date": "Tanggal", "shift": "Shift", "sampleno": "Sample",
            "part": "Part", "model": "Model", "ref": "Ref", "parameter": "Parameter",
            "deviation": "Deviasi", "category": "Kategori", "description": "Deskripsi",
            "corrective_action": "Tindakan Perbaikan", "status": "Status",
            "inputted_role": "Role", "pic": "Penanggung Jawab", "updated_at": "Updated",
        }
        df_show.columns = [rename_map.get(c, c) for c in show_cols]

        def color_status(val):
            c, bg = STATUS_COLOR.get(val, ("#64748B", "#F1F5F9"))
            return f"background-color:{bg};color:{c};font-weight:700;"

        def color_role(val):
            if val == "Measurement":
                return "background-color:#DBEAFE;color:#1E40AF;font-weight:700;"
            elif val == "Produksi":
                return "background-color:#FEF3C7;color:#92400E;font-weight:700;"
            return ""

        styled = df_show.style.map(color_status, subset=["Status"])
        if "Role" in df_show.columns:
            styled = styled.map(color_role, subset=["Role"])

        st.dataframe(
            styled,
            use_container_width=True,
            height=min(560, 80 + len(df_show) * 36),
            hide_index=True,
        )