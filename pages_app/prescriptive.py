"""
pages_app/prescriptive.py
─────────────────────────
Prescriptive Analytics — Rekomendasi Tindakan
"""
import streamlit as st
import pandas as pd
from streamlit_echarts import st_echarts

from local_db import (
    get_root_causes,
    RC_CATEGORIES, RC_STATUSES,
)

STATUS_COLOR = {
    "Open":         ("#DC2626", "#FEE2E2"),
    "Investigated": ("#D97706", "#FEF3C7"),
    "Resolved":     ("#16A34A", "#DCFCE7"),
}


# ── Module-level cached helpers ──────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _get_cat_map(_df_all: pd.DataFrame) -> pd.DataFrame:
    """Cache mapping Part+Model+ref+point → Category dominan. TTL 5 menit."""
    if _df_all.empty or "Category" not in _df_all.columns:
        return pd.DataFrame(columns=["part","model","ref","parameter","_cmm_cat"])
    cat_map = (
        _df_all.groupby(["PartName","ModelName","ref","point"])["Category"]
        .agg(lambda x: x.mode()[0] if len(x) > 0 else "Produksi")
        .reset_index()
    )
    cat_map.columns = ["part","model","ref","parameter","_cmm_cat"]
    return cat_map


@st.cache_data(ttl=300, show_spinner=False)
def _get_rc_df() -> pd.DataFrame:
    """Cache semua root causes sebagai DataFrame. TTL 5 menit."""
    all_rcs = get_root_causes()
    if not all_rcs:
        return pd.DataFrame(
            columns=["part","model","ref","parameter","status","category",
                     "description","corrective_action","date","shift",
                     "sampleno","inputted_by","inputted_role","pic","updated_at","id"]
        )
    df = pd.DataFrame(all_rcs)
    df["_date_dt"] = pd.to_datetime(df["date"], format="%d %b %Y", errors="coerce")
    return df


@st.cache_data(ttl=300, show_spinner=False)
def _compute_scores_cached(_df_ng: pd.DataFrame, _df_rc: pd.DataFrame) -> pd.DataFrame:
    """
    Hitung priority scores semua titik NG — module-level agar cache reliable.
    TTL 5 menit. Prefix _ → Streamlit skip hashing DataFrame.
    """
    if _df_ng.empty:
        return pd.DataFrame()
    pc = "point" if "point" in _df_ng.columns else "Parameter"
    sno_col = "SampleNo" if "SampleNo" in _df_ng.columns else None
    grp_cols = ["PartName","ModelName","ref", pc] + ([sno_col] if sno_col else [])

    agg = _df_ng.groupby(grp_cols).agg(
        n_ng         = (pc, "count"),
        last_date_ts = ("Date", "max"),
    ).reset_index()
    agg["last_date"] = pd.to_datetime(agg["last_date_ts"]).dt.strftime("%d %b %Y")

    idx_max = _df_ng.groupby(grp_cols)["Date"].idxmax()
    agg["last_shift"] = _df_ng.loc[idx_max, "Shift"].values.astype(str) if "Shift" in _df_ng.columns else "—"

    if "KP" in _df_ng.columns:
        kp_grp = _df_ng.groupby(grp_cols)["KP"].apply(
            lambda x: bool(x.astype(str).isin(["1","1.0","True"]).any())
        ).reset_index(name="is_kp")
        agg = agg.merge(kp_grp, on=grp_cols, how="left")
        agg["is_kp"] = agg["is_kp"].fillna(False)
    else:
        agg["is_kp"] = False

    agg = agg.rename(columns={"PartName":"part","ModelName":"model", pc:"parameter"})
    if sno_col:
        agg = agg.rename(columns={sno_col:"sampleno"})
        agg["sampleno"] = agg["sampleno"].astype(str)
    else:
        agg["sampleno"] = "-"

    if not _df_rc.empty and "status" in _df_rc.columns:
        rc_agg = _df_rc.copy()
        rc_agg["sampleno"] = rc_agg["sampleno"].astype(str) if "sampleno" in rc_agg.columns else "-"
        rc_agg["ref"]       = rc_agg["ref"].astype(str)
        rc_agg["parameter"] = rc_agg["parameter"].astype(str)
        merge_cols = ["part","model","ref","parameter","sampleno"]
        rc_stats = rc_agg.groupby(merge_cols).agg(
            n_open     = ("status", lambda x: (x=="Open").sum()),
            n_invest   = ("status", lambda x: (x=="Investigated").sum()),
            n_resolved = ("status", lambda x: (x=="Resolved").sum()),
            top_cat    = ("category", lambda x: x.value_counts().index[0] if len(x) else "—"),
        ).reset_index()
        agg = agg.merge(rc_stats, on=merge_cols, how="left")
        agg["n_open"]     = agg["n_open"].fillna(0).astype(int)
        agg["n_invest"]   = agg["n_invest"].fillna(0).astype(int)
        agg["n_resolved"] = agg["n_resolved"].fillna(0).astype(int)
        agg["top_cat"]    = agg["top_cat"].fillna("—")
    else:
        agg["n_open"] = agg["n_invest"] = agg["n_resolved"] = 0
        agg["top_cat"] = "—"

    agg["has_rc"] = (agg["n_open"] + agg["n_invest"] + agg["n_resolved"]) > 0
    agg["score"]  = (agg["n_ng"] * 3) + (agg["n_open"] * 4) + (agg["n_invest"] * 1) + (agg["is_kp"].astype(int) * 10)

    result = agg[["part","model","ref","parameter","sampleno",
                  "n_ng","is_kp","has_rc","n_open","n_invest","n_resolved",
                  "top_cat","last_date","last_shift","score"]].copy()
    df_with    = result[result["has_rc"]].sort_values("score", ascending=False)
    df_without = result[~result["has_rc"]].sort_values("n_ng", ascending=False)
    return pd.concat([df_with, df_without], ignore_index=True)

REKOMENDASI = {
    "Mesin / Machine": [
        "Lakukan kalibrasi probe CMM sebelum shift berikutnya",
        "Cek kondisi spindle dan thermal compensation mesin",
        "Verifikasi backlash pada axis yang bermasalah",
        "Jadwalkan preventive maintenance jika belum dilakukan",
    ],
    "Setup / Fixture": [
        "Verifikasi posisi fixture sesuai drawing sebelum produksi",
        "Pastikan semua clamp terkunci sempurna",
        "Cek datum reference — pastikan tidak ada burr atau kotoran",
        "Lakukan re-setup dan verifikasi dengan sampel pertama",
    ],
    "Material": [
        "Lakukan incoming inspection material sebelum diproses",
        "Koordinasi dengan supplier untuk review dimensi raw material",
        "Pisahkan material suspect — jangan proses dulu",
        "Minta sample report dari supplier untuk batch ini",
    ],
    "Operator": [
        "Brief operator sebelum shift dimulai untuk titik ini",
        "Review SOP setup dan mounting bersama operator",
        "Assign operator berpengalaman untuk titik kritis",
        "Lakukan observasi langsung saat setup pertama",
    ],
    "Program CMM": [
        "Update program CMM sesuai revisi drawing terbaru",
        "Verifikasi reference point dan approach speed",
        "Test run program dengan part master sebelum produksi",
        "Review path program untuk potensi probe collision",
    ],
    "Tooling": [
        "Ganti tool yang wear — verifikasi dengan tool life record",
        "Cek kondisi insert dan holder sebelum produksi",
        "Verifikasi coolant flow tidak tersumbat",
        "Ukur dimensi tool aktual sebelum dipakai",
    ],
    "Lainnya": [
        "Lakukan investigasi lebih lanjut bersama engineer",
        "Dokumentasikan temuan untuk analisis root cause",
        "Eskalasi ke supervisor jika belum teridentifikasi",
    ],
}


# Keyword fallback category untuk titik tanpa RC
_PARAM_CAT_MAP = {
    "position": "Setup / Fixture", "posisi": "Setup / Fixture",
    "distance": "Tooling",         "diameter": "Tooling",
    "concentricity": "Setup / Fixture", "flatness": "Material",
    "straightness": "Setup / Fixture",  "profile": "Mesin / Machine",
    "angle": "Setup / Fixture",         "radius": "Tooling",
}

class PrescriptivePage:
    def __init__(self, df_all: pd.DataFrame):
        self.df_all = df_all

    def render(self):
        st.markdown(
            '<div class="page-hdr">'
            '<span class="page-title">Prescriptive</span>'
            '<span class="page-sub">Rekomendasi Tindakan</span>'
            '</div>'
            '<div class="section-desc">Rekomendasi tindakan berdasarkan pola root cause historis · prioritas titik berdasarkan frekuensi NG dan status investigasi.</div>',
            unsafe_allow_html=True
        )

        # Pakai module-level cached function — reliable, tidak buat closure baru tiap render
        df_rc = _get_rc_df()

        from datetime import timedelta as _td
        _now = pd.Timestamp.now()

        # ── BARIS 1: Periode | Status | Kategori | KP ────────────
        col_r1 = st.columns([1.6, 1.4, 1.4, 1.2], gap="small")

        with col_r1[0]:
            time_opts = ["Semua Periode", "Hari Ini", "7 Hari Terakhir", "30 Hari Terakhir", "Custom"]
            f_time = st.selectbox("Periode", time_opts,
                                  key="presc_time", label_visibility="visible")

        with col_r1[1]:
            status_opts = ["Semua Status", "Belum Diisi", "Open", "Investigated", "Resolved"]
            if st.session_state.get("presc_status") not in status_opts:
                st.session_state["presc_status"] = "Semua Status"
            f_status = st.selectbox("Status Root Cause", status_opts,
                                    key="presc_status", label_visibility="visible")

        with col_r1[2]:
            cat_filter_opts = ["Semua Kategori", "Produksi", "QIS"]
            if st.session_state.get("presc_cat_filter") not in cat_filter_opts:
                st.session_state["presc_cat_filter"] = "Produksi"
            f_cat_filter = st.selectbox("Kategori", cat_filter_opts,
                                        key="presc_cat_filter", label_visibility="visible")

        with col_r1[3]:
            kp_opts = ["Semua Titik", "KP saja"]
            if st.session_state.get("presc_kp") not in kp_opts:
                st.session_state["presc_kp"] = "Semua Titik"
            f_kp = st.selectbox("Kritikal Point", kp_opts,
                                key="presc_kp", label_visibility="visible")

        # ── Apply filter waktu ke df_f_base ──────────────────────
        if f_time == "Custom":
            from datetime import timedelta as _td2
            _cd1, _cd2 = st.columns(2, gap="small")
            with _cd1:
                d_from = st.date_input("Dari", value=(_now - _td(days=30)).date(),
                                       key="presc_d1", label_visibility="visible")
            with _cd2:
                d_to = st.date_input("Sampai", value=_now.date(),
                                     key="presc_d2", label_visibility="visible")

        df_f_base = df_rc.copy()
        if f_time == "Hari Ini":
            df_f_base = df_f_base[df_f_base["_date_dt"].dt.date == _now.date()]
        elif f_time == "7 Hari Terakhir":
            df_f_base = df_f_base[df_f_base["_date_dt"] >= _now - _td(days=6)]
        elif f_time == "30 Hari Terakhir":
            df_f_base = df_f_base[df_f_base["_date_dt"] >= _now - _td(days=29)]
        elif f_time == "Custom":
            df_f_base = df_f_base[
                (df_f_base["_date_dt"].dt.date >= d_from) &
                (df_f_base["_date_dt"].dt.date <= d_to)
            ]

        # ── BARIS 2: Part·Model | SampleNo | Ref | Parameter (cascade) ──
        # Combo Part · Model dari df_all (semua NG, bukan hanya yang sudah ada RC)
        _src_combo = self.df_all if not self.df_all.empty else pd.DataFrame(columns=["PartName","ModelName"])
        combos_df = (
            _src_combo[["PartName","ModelName"]].dropna().drop_duplicates()
            .sort_values(["PartName","ModelName"])
            .rename(columns={"PartName":"part","ModelName":"model"})
        )
        combo_opts = ["Semua Part & Model"] + [
            f"{r['part']} · {r['model']}" for _, r in combos_df.iterrows()
        ]
        if st.session_state.get("presc_combo") not in combo_opts:
            st.session_state["presc_combo"] = "Semua Part & Model"

        cur_combo = st.session_state.get("presc_combo", "Semua Part & Model")
        df_after_combo = df_f_base.copy()
        if cur_combo != "Semua Part & Model":
            _sp = cur_combo.split(" · ", 1)
            if len(_sp) == 2:
                df_after_combo = df_f_base[
                    (df_f_base["part"] == _sp[0]) & (df_f_base["model"] == _sp[1])
                ]

        # SampleNo cascade dari combo
        sno_vals = sorted(
            df_after_combo["sampleno"].dropna().astype(str).unique().tolist(),
            key=lambda s: (0, int(s)) if s.isdigit() else (1, s)
        ) if "sampleno" in df_after_combo.columns else []
        sno_opts = ["Semua Sample"] + sno_vals
        if st.session_state.get("presc_sno") not in sno_opts:
            st.session_state["presc_sno"] = "Semua Sample"

        cur_sno = st.session_state.get("presc_sno", "Semua Sample")
        df_after_sno = df_after_combo.copy()
        if cur_sno != "Semua Sample" and "sampleno" in df_after_sno.columns:
            df_after_sno = df_after_combo[df_after_combo["sampleno"].astype(str) == cur_sno]

        # Ref cascade dari sampleno
        ref_vals = sorted([
            r for r in df_after_sno["ref"].dropna().astype(str).unique()
            if r.strip() not in ("", "-", "nan")
        ]) if "ref" in df_after_sno.columns else []
        ref_opts = ["Semua Ref / Point"] + ref_vals
        if st.session_state.get("presc_ref") not in ref_opts:
            st.session_state["presc_ref"] = "Semua Ref / Point"

        cur_ref = st.session_state.get("presc_ref", "Semua Ref / Point")
        df_after_ref = df_after_sno.copy()
        if cur_ref != "Semua Ref / Point" and "ref" in df_after_ref.columns:
            df_after_ref = df_after_sno[df_after_sno["ref"].astype(str) == cur_ref]

        # Parameter cascade dari ref
        param_vals = sorted([
            p for p in df_after_ref["parameter"].dropna().astype(str).unique()
            if p.strip() not in ("", "-", "nan")
        ]) if "parameter" in df_after_ref.columns else []
        param_opts = ["Semua Parameter"] + param_vals
        if st.session_state.get("presc_param") not in param_opts:
            st.session_state["presc_param"] = "Semua Parameter"

        col_r2 = st.columns([2, 1, 1.2, 1.8], gap="small")
        with col_r2[0]:
            f_combo = st.selectbox("Part · Model", combo_opts,
                                   key="presc_combo", label_visibility="visible")
        with col_r2[1]:
            f_sno = st.selectbox("No. Sample", sno_opts,
                                 key="presc_sno", label_visibility="visible")
        with col_r2[2]:
            f_ref = st.selectbox("Ref / Point", ref_opts,
                                 key="presc_ref", label_visibility="visible")
        with col_r2[3]:
            f_param = st.selectbox("Parameter", param_opts,
                                   key="presc_param", label_visibility="visible")

        # ── Terapkan semua filter ─────────────────────────────────
        df_f = df_f_base.copy()

        # Filter Kategori (Produksi/QIS dari CMM data) — pakai cached cat_map
        if f_cat_filter != "Semua Kategori":
            if not self.df_all.empty and "Category" in self.df_all.columns:
                _cat_map = _get_cat_map(self.df_all)
                df_f = df_f.merge(_cat_map, on=["part","model","ref","parameter"], how="left")
                df_f["_cmm_cat"] = df_f["_cmm_cat"].fillna("Produksi")
                df_f = df_f[df_f["_cmm_cat"] == f_cat_filter].drop(columns=["_cmm_cat"], errors="ignore")

        # Filter KP — dari df_all, vektorisasi lewat merge bukan apply(axis=1)
        if f_kp == "KP saja" and not self.df_all.empty and "KP" in self.df_all.columns:
            kp_ref = (
                self.df_all[self.df_all["KP"].astype(str).isin(["1","1.0","True"])]
                [["PartName","ModelName","ref","point"]]
                .drop_duplicates()
                .rename(columns={"PartName":"part","ModelName":"model","point":"parameter"})
            )
            kp_ref["_is_kp"] = True
            df_f = df_f.merge(kp_ref, on=["part","model","ref","parameter"], how="left")
            df_f = df_f[df_f["_is_kp"] == True].drop(columns=["_is_kp"])

        # Part · Model
        if f_combo != "Semua Part & Model":
            _sp = f_combo.split(" · ", 1)
            if len(_sp) == 2:
                df_f = df_f[(df_f["part"] == _sp[0]) & (df_f["model"] == _sp[1])]

        # SampleNo
        if f_sno != "Semua Sample" and "sampleno" in df_f.columns:
            df_f = df_f[df_f["sampleno"].astype(str) == f_sno]

        # Ref
        if f_ref != "Semua Ref / Point" and "ref" in df_f.columns:
            df_f = df_f[df_f["ref"].astype(str) == f_ref]

        # Parameter
        if f_param != "Semua Parameter" and "parameter" in df_f.columns:
            df_f = df_f[df_f["parameter"].astype(str) == f_param]

        # Status
        if f_status != "Semua Status":
            df_f = df_f[df_f["status"] == f_status]

        if df_f.empty:
            st.info("Tidak ada data untuk filter ini.")
            return

        # ── Filter df_all untuk KPI (periode+part+kp+cat) ──────────
        _df_kpi = self.df_all.copy() if not self.df_all.empty else pd.DataFrame()
        if not _df_kpi.empty:
            if f_time == "Hari Ini":
                _df_kpi = _df_kpi[_df_kpi["Date"].dt.date == _now.date()]
            elif f_time == "7 Hari Terakhir":
                _df_kpi = _df_kpi[_df_kpi["Date"] >= _now - _td(days=6)]
            elif f_time == "30 Hari Terakhir":
                _df_kpi = _df_kpi[_df_kpi["Date"] >= _now - _td(days=29)]
            elif f_time == "Custom":
                _df_kpi = _df_kpi[(_df_kpi["Date"].dt.date >= d_from) & (_df_kpi["Date"].dt.date <= d_to)]
            _sp2 = f_combo.split(" · ", 1) if f_combo != "Semua Part & Model" else None
            if _sp2 and len(_sp2)==2:
                _df_kpi = _df_kpi[(_df_kpi["PartName"]==_sp2[0]) & (_df_kpi["ModelName"]==_sp2[1])]
            if f_kp == "KP saja" and "KP" in _df_kpi.columns:
                _df_kpi = _df_kpi[_df_kpi["KP"].astype(str).isin(["1","1.0","True"])]
            if f_cat_filter != "Semua Kategori" and "Category" in _df_kpi.columns:
                _df_kpi = _df_kpi[_df_kpi["Category"] == f_cat_filter]

        # ── KPI Cards — hitung dari df_all (semua NG) + rc_lookup ─
        _pc_kpi  = "point" if "point" in _df_kpi.columns else "Parameter"
        _sno_kpi = "SampleNo" if "SampleNo" in _df_kpi.columns else None
        df_ng_kpi = _df_kpi[_df_kpi["Judgement"]=="NG"] if not _df_kpi.empty and "Judgement" in _df_kpi.columns else pd.DataFrame()

        # Build rc_lookup untuk KPI
        _rc_kpi: dict = {}
        for _, _r in df_rc.iterrows():
            _k = (str(_r["part"]),str(_r["model"]),str(_r.get("sampleno","-")),str(_r["ref"]),str(_r["parameter"]))
            _rc_kpi[_k] = _r.get("status","Open")

        # Hitung per titik unik
        n_total = 0; n_open = 0; n_invest = 0; n_resolved = 0
        if not df_ng_kpi.empty:
            _grp_kpi = ["PartName","ModelName","ref",_pc_kpi] + ([_sno_kpi] if _sno_kpi else [])
            for keys, _ in df_ng_kpi.groupby(_grp_kpi):
                if _sno_kpi:
                    part, model, ref, param, sno = keys
                else:
                    part, model, ref, param = keys; sno = "-"
                _k = (str(part),str(model),str(sno),str(ref),str(param))
                n_total += 1
                _st = _rc_kpi.get(_k)
                if   _st == "Open":         n_open    += 1
                elif _st == "Investigated": n_invest  += 1
                elif _st == "Resolved":     n_resolved+= 1
                else:                       n_open    += 1  # belum ada RC = Open
        pct_done = round(n_resolved / n_total * 100, 1) if n_total else 0

        st.markdown(
            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px;">'
            + "".join([
                f'<div style="background:{bg};border-radius:10px;border:1px solid {bc};'
                f'padding:16px;text-align:center;">'
                f'<div style="font-size:26px;font-weight:800;color:{fc};">{val}</div>'
                f'<div style="font-size:11px;font-weight:600;color:#64748B;margin-top:4px;">{lbl}</div>'
                f'</div>'
                for bg, bc, fc, val, lbl in [
                    ("#F8FAFC","#E2E8F0","#0F172A", n_total,      "Total Root Cause"),
                    ("#FEF2F2","#FECACA","#DC2626", n_open,       "Open"),
                    ("#FFFBEB","#FDE68A","#D97706", n_invest,     "Investigated"),
                    ("#F0FDF4","#BBF7D0","#16A34A", n_resolved,   "Resolved"),
                ]
            ])
            + '</div>',
            unsafe_allow_html=True
        )

        # ── Tabs ──────────────────────────────────────────────────
        tab1, tab2 = st.tabs([
            "Prioritas Tindakan",
            "Pola & Tren",
        ])

        # ── Terapkan filter waktu+part+kp+cat ke df_all ─────────────
        df_all_f = self.df_all.copy() if not self.df_all.empty else pd.DataFrame()
        if not df_all_f.empty:
            if f_time == "Hari Ini":
                df_all_f = df_all_f[df_all_f["Date"].dt.date == _now.date()]
            elif f_time == "7 Hari Terakhir":
                df_all_f = df_all_f[df_all_f["Date"] >= _now - _td(days=6)]
            elif f_time == "30 Hari Terakhir":
                df_all_f = df_all_f[df_all_f["Date"] >= _now - _td(days=29)]
            elif f_time == "Custom":
                df_all_f = df_all_f[
                    (df_all_f["Date"].dt.date >= d_from) &
                    (df_all_f["Date"].dt.date <= d_to)
                ]
            if f_combo != "Semua Part & Model":
                _sp = f_combo.split(" · ", 1)
                if len(_sp) == 2:
                    df_all_f = df_all_f[
                        (df_all_f["PartName"]==_sp[0]) & (df_all_f["ModelName"]==_sp[1])
                    ]
            if f_kp == "KP saja" and "KP" in df_all_f.columns:
                df_all_f = df_all_f[df_all_f["KP"].astype(str).isin(["1","1.0","True"])]
            if f_cat_filter != "Semua Kategori" and "Category" in df_all_f.columns:
                df_all_f = df_all_f[df_all_f["Category"] == f_cat_filter]
            if f_ref != "Semua Ref / Point" and "ref" in df_all_f.columns:
                df_all_f = df_all_f[df_all_f["ref"].astype(str) == f_ref]

        with tab1:
            @st.fragment
            def _tab1():
                self._render_prioritas(df_all_f, df_rc, f_status)
            _tab1()
        with tab2:
            @st.fragment
            def _tab2():
                self._render_pola(df_f)
            _tab2()

    # ════════════════════════════════════════════════════════════
    # TAB 1 — PRIORITAS TINDAKAN
    # ════════════════════════════════════════════════════════════
    def _render_prioritas(self, df_all_f: pd.DataFrame, df_rc: pd.DataFrame, f_status: str):
        if df_all_f.empty:
            st.info("Tidak ada data NG untuk filter ini.")
            return

        df_ng_f  = df_all_f[df_all_f["Judgement"] == "NG"] if "Judgement" in df_all_f.columns else df_all_f
        df_score = _compute_scores_cached(df_ng_f, df_rc)

        if df_score.empty:
            st.info("Tidak ada titik NG untuk filter ini.")
            return

        # ── Apply status filter ───────────────────────────────────
        if f_status == "Belum Diisi":
            df_score = df_score[~df_score["has_rc"]]
        elif f_status == "Open":
            df_score = df_score[df_score["n_open"] > 0]
        elif f_status == "Investigated":
            df_score = df_score[df_score["n_invest"] > 0]
        elif f_status == "Resolved":
            df_score = df_score[df_score["n_resolved"] > 0]

        if df_score.empty:
            st.info("Tidak ada titik untuk filter status ini.")
            return

        # ── Pagination ────────────────────────────────────────────
        PAGE_SIZE = 10
        n_total_items = len(df_score)
        n_pages = max(1, -(-n_total_items // PAGE_SIZE))

        if n_pages > 1:
            pc1, pc2, pc3 = st.columns([1, 3, 1], gap="small")
            cur_page = st.session_state.get("presc_page", 1)
            cur_page = max(1, min(cur_page, n_pages))
            with pc1:
                if st.button("Sebelumnya", key="presc_prev", disabled=cur_page<=1,
                             use_container_width=True):
                    st.session_state.presc_page = cur_page - 1
                    st.session_state.presc_open_titik = None
                    st.rerun()
            with pc2:
                st.markdown(
                    f'<div style="text-align:center;font-size:12px;color:#64748B;padding-top:6px;">'
                    f'Halaman <b>{cur_page}</b> / <b>{n_pages}</b> &nbsp;·&nbsp; {n_total_items} titik</div>',
                    unsafe_allow_html=True
                )
            with pc3:
                if st.button("Berikutnya", key="presc_next", disabled=cur_page>=n_pages,
                             use_container_width=True):
                    st.session_state.presc_page = cur_page + 1
                    st.session_state.presc_open_titik = None
                    st.rerun()
        else:
            cur_page = 1

        start_idx = (cur_page - 1) * PAGE_SIZE
        df_page   = df_score.iloc[start_idx : start_idx + PAGE_SIZE]

        def _priority(score, is_kp):
            if score >= 20 or is_kp: return ("🔴 Kritis",  "#DC2626","#FEE2E2")
            if score >= 10:          return ("🟡 Tinggi",  "#D97706","#FEF3C7")
            return                          ("🟢 Sedang",  "#16A34A","#DCFCE7")

        open_titik = st.session_state.get("presc_open_titik")

        for _, row in df_page.iterrows():
            label   = f"{row['ref']} · {row['parameter']}"
            tid     = f"{row['part']}_{row['model']}_{row['ref']}_{row['parameter']}_{row['sampleno']}"
            p_lbl, p_fc, p_bg = _priority(row["score"], row["is_kp"])
            is_open = open_titik == tid
            has_rc  = bool(row["has_rc"])

            # Status badge
            if not has_rc:
                status_badge = '<span style="background:#FEE2E2;color:#DC2626;font-size:10px;font-weight:700;padding:2px 9px;border-radius:99px;">⚠ Belum Ada RC</span>'
            else:
                _so = row["n_open"]; _si = row["n_invest"]; _sr = row["n_resolved"]
                status_badge = " ".join(filter(None, [
                    f'<span style="background:#FEE2E2;color:#DC2626;font-size:10px;font-weight:700;padding:2px 9px;border-radius:99px;">{_so} Open</span>' if _so else "",
                    f'<span style="background:#FEF3C7;color:#D97706;font-size:10px;font-weight:700;padding:2px 9px;border-radius:99px;">{_si} Investigated</span>' if _si else "",
                    f'<span style="background:#DCFCE7;color:#16A34A;font-size:10px;font-weight:700;padding:2px 9px;border-radius:99px;">{_sr} Resolved</span>' if _sr else "",
                ]))

            kp_tag    = '<span style="background:#EFF6FF;color:#1D4ED8;font-size:9px;font-weight:700;padding:1px 7px;border-radius:99px;margin-left:4px;">KP</span>' if row["is_kp"] else ""
            border    = "#EF4444" if not has_rc or row["n_open"] > 0 else "#E2E8F0"

            st.markdown(
                f'<div style="background:white;border:1px solid {border};'
                f'border-left:4px solid {border};border-radius:10px;'
                f'padding:12px 16px;margin-bottom:4px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<div style="flex:1;min-width:0;">'
                f'<div style="font-size:14px;font-weight:700;color:#0F172A;">{label}{kp_tag}</div>'
                f'<div style="font-size:11px;color:#64748B;margin-top:3px;display:flex;flex-wrap:wrap;gap:4px;align-items:center;">'
                f'<b>{row["part"]} {row["model"]}</b>'
                f'&nbsp;·&nbsp; Sample <b>{row["sampleno"]}</b>'
                f'&nbsp;·&nbsp; {row["n_ng"]} NG'
                f'&nbsp;·&nbsp; Terakhir {row["last_date"]} S{row["last_shift"]}'
                f'{"&nbsp;·&nbsp; Dominan: <b>" + row["top_cat"] + "</b>" if has_rc else ""}'
                f'</div>'
                f'<div style="display:flex;gap:4px;margin-top:5px;">{status_badge}</div>'
                f'</div>'
                f'<span style="background:{p_bg};color:{p_fc};font-size:10px;'
                f'font-weight:700;padding:3px 10px;border-radius:99px;flex-shrink:0;margin-left:8px;">{p_lbl}</span>'
                f'</div></div>',
                unsafe_allow_html=True
            )

            col_btn, _ = st.columns([1, 6])
            with col_btn:
                btn_lbl = "Tutup" if is_open else "Rekomendasi"
                if st.button(btn_lbl, key=f"presc_btn_{tid}",
                             use_container_width=True,
                             type="secondary" if is_open else "primary"):
                    st.session_state.presc_open_titik = None if is_open else tid
                    st.rerun()

            if is_open:
                self._render_rekomendasi_detail(row, df_rc, df_all_f)

            st.markdown('<div style="height:4px;"></div>', unsafe_allow_html=True)


    def _render_rekomendasi_detail(self, row: pd.Series, df_rc: pd.DataFrame, df_all_f: pd.DataFrame = None):
        df_titik = df_rc[
            (df_rc["part"]==row["part"]) & (df_rc["model"]==row["model"]) &
            (df_rc["ref"]==row["ref"]) & (df_rc["parameter"]==row["parameter"])
        ]

        # ── No-RC case: tampil info NG + arahkan ke Diagnostic ───
        if df_titik.empty:
            with st.container(border=True):
                st.markdown(
                    f'<div style="background:#FEF2F2;border-left:4px solid #EF4444;'
                    f'border-radius:0 10px 10px 0;padding:10px 14px;margin-bottom:12px;">'
                    f'<div style="font-size:13px;font-weight:700;color:#DC2626;">'
                    f'Belum ada Root Cause untuk {row["ref"]} · {row["parameter"]}</div>'
                    f'<div style="font-size:11px;color:#64748B;margin-top:4px;">'
                    f'Silakan buka halaman <b>Diagnostic → Isi Root Cause</b> '
                    f'dan isi penyebab NG untuk titik ini.</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
                # Tampil data NG terbaru dari df_all
                if df_all_f is not None and not df_all_f.empty:
                    _pc = "point" if "point" in df_all_f.columns else "Parameter"
                    df_ng_titik = df_all_f[
                        (df_all_f["PartName"]==row["part"]) &
                        (df_all_f["ModelName"]==row["model"]) &
                        (df_all_f["ref"].astype(str)==str(row["ref"])) &
                        (df_all_f[_pc].astype(str)==str(row["parameter"])) &
                        (df_all_f["Judgement"]=="NG")
                    ].sort_values("Date", ascending=False).head(5)

                    if not df_ng_titik.empty:
                        st.markdown(
                            '<div style="font-size:12px;font-weight:700;color:#0F172A;margin-bottom:6px;">'
                            'Data NG Terbaru</div>',
                            unsafe_allow_html=True
                        )
                        dev_col = "Deviation" if "Deviation" in df_ng_titik.columns else (
                                  "deviation" if "deviation" in df_ng_titik.columns else None)
                        rows_html = ""
                        for _, _r in df_ng_titik.iterrows():
                            _date_s  = _r["Date"].strftime("%d %b %Y") if hasattr(_r["Date"], "strftime") else str(_r["Date"])
                            _shift_s = str(_r.get("Shift", "—"))
                            _dev_s   = f'<b style="color:#DC2626;">{round(_r[dev_col],4)}</b>' if dev_col else "—"
                            rows_html += (
                                f'<div style="display:flex;justify-content:space-between;'
                                f'padding:5px 8px;border-bottom:1px solid #F1F5F9;font-size:11px;">'
                                f'<span style="color:#374151;">{_date_s} · S{_shift_s}</span>'
                                f'<span>Dev: {_dev_s}</span>'
                                f'</div>'
                            )
                        st.markdown(
                            f'<div style="background:#FFF8F8;border-radius:8px;border:1px solid #FEE2E2;">'
                            f'{rows_html}</div>',
                            unsafe_allow_html=True
                        )

                # Fallback rekomendasi berdasarkan keyword parameter
                _param_lower = str(row["parameter"]).lower()
                _fb_cat = next(
                    (cat for kw, cat in _PARAM_CAT_MAP.items() if kw in _param_lower),
                    "Lainnya"
                )
                st.markdown(
                    f'<div style="font-size:12px;font-weight:700;color:#0F172A;'
                    f'margin:12px 0 8px;">Saran Tindakan — berdasarkan tipe parameter</div>',
                    unsafe_allow_html=True
                )
                st.markdown(
                    f'<div style="font-size:11px;color:#64748B;margin-bottom:8px;">'
                    f'Belum ada root cause. Saran berdasarkan tipe <b>{_fb_cat}</b>.</div>',
                    unsafe_allow_html=True
                )
                for _i, _rec in enumerate(REKOMENDASI.get(_fb_cat, REKOMENDASI["Lainnya"]), 1):
                    st.markdown(
                        f'<div style="display:flex;gap:8px;align-items:flex-start;margin-bottom:6px;">'
                        f'<span style="background:#F1F5F9;color:#64748B;border-radius:50%;'
                        f'width:18px;height:18px;display:flex;align-items:center;'
                        f'justify-content:center;font-size:9px;font-weight:700;flex-shrink:0;">{_i}</span>'
                        f'<span style="font-size:11px;color:#334155;">{_rec}</span></div>',
                        unsafe_allow_html=True
                    )
            return

        cat_counts = df_titik["category"].value_counts()
        top_cat    = cat_counts.index[0] if len(cat_counts) else "Lainnya"
        top_pct    = round(cat_counts.iloc[0]/len(df_titik)*100) if len(df_titik) else 0
        shift_counts = df_titik["shift"].value_counts() if "shift" in df_titik.columns else None

        # ── Warna tema berdasar kategori dominan ─────────────────
        CAT_COLOR = {
            "Mesin / Machine": "#EF4444", "Setup / Fixture": "#F59E0B",
            "Material":        "#8B5CF6", "Operator":        "#06B6D4",
            "Program CMM":     "#10B981", "Tooling":         "#6366F1",
            "Lainnya":         "#94A3B8",
        }
        theme_clr = CAT_COLOR.get(top_cat, "#6366F1")

        with st.container(border=True):

            # ── Header insight ────────────────────────────────────
            ref_str   = str(row["ref"])
            param_str = str(row["parameter"])
            shift_insight = ""
            if shift_counts is not None and len(shift_counts) > 0:
                top_shift     = shift_counts.index[0]
                top_shift_pct = round(shift_counts.iloc[0] / len(df_titik) * 100)
                shift_insight = (
                    f'<span style="background:#EFF6FF;color:#1D4ED8;border-radius:99px;'
                    f'padding:2px 10px;font-size:10px;font-weight:600;margin-left:6px;">'
                    f'Shift {top_shift} dominan ({top_shift_pct}%)</span>'
                )

            n_o = int((df_titik["status"]=="Open").sum())
            n_i = int((df_titik["status"]=="Investigated").sum())
            n_r = int((df_titik["status"]=="Resolved").sum())
            _badges = (
                (f'<span style="background:#FEE2E2;color:#DC2626;border-radius:99px;padding:2px 9px;font-size:10px;font-weight:700;">{n_o} Open</span> ' if n_o else "") +
                (f'<span style="background:#FEF3C7;color:#D97706;border-radius:99px;padding:2px 9px;font-size:10px;font-weight:700;">{n_i} Investigated</span> ' if n_i else "") +
                (f'<span style="background:#DCFCE7;color:#16A34A;border-radius:99px;padding:2px 9px;font-size:10px;font-weight:700;">{n_r} Resolved</span>' if n_r else "")
            )

            st.markdown(
                f'<div style="display:flex;align-items:center;justify-content:space-between;'
                f'background:linear-gradient(135deg,{theme_clr}18,{theme_clr}08);'
                f'border-left:4px solid {theme_clr};border-radius:0 10px 10px 0;'
                f'padding:10px 14px;margin-bottom:14px;">'
                f'<div>'
                f'<span style="font-size:13px;font-weight:700;color:#0F172A;">{ref_str} · {param_str}</span>'
                f'<span style="background:{theme_clr}22;color:{theme_clr};border-radius:99px;'
                f'padding:2px 10px;font-size:10px;font-weight:700;margin-left:8px;">{top_cat} {top_pct}%</span>'
                f'{shift_insight}'
                f'</div>'
                f'<div style="display:flex;gap:4px;flex-shrink:0;">{_badges}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

            col_a, col_b = st.columns([1, 1.15], gap="large")

            # ── Col A: Distribusi Penyebab ────────────────────────
            with col_a:
                st.markdown(
                    f'<div style="font-size:12px;font-weight:700;color:#0F172A;'
                    f'border-bottom:2px solid {theme_clr};padding-bottom:5px;margin-bottom:10px;">'
                    f'Distribusi Penyebab</div>',
                    unsafe_allow_html=True
                )
                if shift_counts is not None and len(shift_counts) > 1:
                    shift_cat_df = df_titik.groupby(["shift","category"]).size().reset_index(name="n")
                    shifts_u = sorted(df_titik["shift"].dropna().unique())
                    COLORS_P = ["#EF4444","#F59E0B","#8B5CF6","#06B6D4","#10B981","#6366F1","#94A3B8"]
                    ser_sc = []
                    for i2, cat2 in enumerate(RC_CATEGORIES):
                        vals2 = [int(shift_cat_df[(shift_cat_df["shift"]==sh2)&(shift_cat_df["category"]==cat2)]["n"].sum())
                                 if not shift_cat_df[(shift_cat_df["shift"]==sh2)&(shift_cat_df["category"]==cat2)].empty else 0
                                 for sh2 in shifts_u]
                        if any(v2>0 for v2 in vals2):
                            ser_sc.append({"name":cat2,"type":"bar","stack":"s","data":vals2,
                                           "itemStyle":{"color":COLORS_P[i2%len(COLORS_P)]}})
                    st_echarts({
                        "tooltip":{"trigger":"axis","axisPointer":{"type":"shadow"}},
                        "legend":{"bottom":0,"icon":"roundRect","itemWidth":8,"textStyle":{"fontSize":8}},
                        "grid":{"top":8,"bottom":60,"left":30,"right":8},
                        "xAxis":{"type":"category","data":[f"S{s2}" for s2 in shifts_u]},
                        "yAxis":{"type":"value","axisLabel":{"fontSize":9}},
                        "series":ser_sc,
                    }, height="200px", key=f"presc_shift_{row['ref']}_{row['parameter']}")
                else:
                    st_echarts({
                        "tooltip": {"trigger":"item","formatter":"{b}: {c} ({d}%)"},
                        "series": [{"type":"pie","radius":["45%","72%"],
                            "center":["50%","48%"],
                            "data":[{"name":l,"value":v} for l,v in zip(cat_counts.index.tolist(),cat_counts.values.tolist())],
                            "label":{"show":True,"formatter":"{b}\n{d}%","fontSize":10,"lineHeight":14},
                            "itemStyle":{"borderRadius":6,"borderWidth":2,"borderColor":"#fff"}}],
                        "color":["#EF4444","#F59E0B","#8B5CF6","#06B6D4","#10B981","#6366F1","#94A3B8"],
                    }, height="180px", key=f"presc_pie_{row['ref']}_{row['parameter']}")

                # ── Stats bawah chart ─────────────────────────────
                n_total_rc  = len(df_titik)
                last_date   = df_titik["date"].iloc[-1] if "date" in df_titik.columns and len(df_titik) else "—"
                last_shift  = df_titik["shift"].iloc[-1] if "shift" in df_titik.columns and len(df_titik) else "—"

                # Shift breakdown pills
                _shift_pills = ""
                if shift_counts is not None and len(shift_counts) > 0:
                    for sh, cnt in shift_counts.items():
                        pct_sh = round(cnt / n_total_rc * 100)
                        _shift_pills += (
                            f'<div style="display:flex;justify-content:space-between;'
                            f'align-items:center;padding:5px 8px;margin-bottom:4px;'
                            f'background:#F8FAFC;border-radius:6px;border:1px solid #E2E8F0;">'
                            f'<span style="font-size:11px;font-weight:600;color:#374151;">Shift {sh}</span>'
                            f'<div style="display:flex;align-items:center;gap:6px;">'
                            f'<div style="width:60px;height:5px;background:#E2E8F0;border-radius:99px;">'
                            f'<div style="width:{pct_sh}%;height:100%;background:{theme_clr};border-radius:99px;"></div>'
                            f'</div>'
                            f'<span style="font-size:11px;color:{theme_clr};font-weight:700;">{cnt}x</span>'
                            f'</div></div>'
                        )

                st.markdown(
                    f'<div style="margin-top:10px;">'
                    f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px;">'
                    f'<div style="background:{theme_clr}12;border-radius:8px;padding:8px 10px;text-align:center;">'
                    f'<div style="font-size:20px;font-weight:800;color:{theme_clr};">{n_total_rc}</div>'
                    f'<div style="font-size:10px;color:#64748B;margin-top:1px;">Total RC Tercatat</div>'
                    f'</div>'
                    f'<div style="background:#F8FAFC;border-radius:8px;padding:8px 10px;text-align:center;">'
                    f'<div style="font-size:13px;font-weight:700;color:#0F172A;">{last_date}</div>'
                    f'<div style="font-size:10px;color:#64748B;margin-top:1px;">Terakhir · S{last_shift}</div>'
                    f'</div>'
                    f'</div>'
                    f'{_shift_pills}'
                    f'</div>',
                    unsafe_allow_html=True
                )

            # ── Col B: Rekomendasi + Penyebab + Action ────────────
            with col_b:
                # Rekomendasi Tindakan
                st.markdown(
                    f'<div style="font-size:12px;font-weight:700;color:#0F172A;'
                    f'border-bottom:2px solid {theme_clr};padding-bottom:5px;margin-bottom:10px;">'
                    f'Rekomendasi Tindakan</div>',
                    unsafe_allow_html=True
                )
                _rekomendasi_html = "".join(
                    f'<div style="display:flex;gap:8px;align-items:flex-start;margin-bottom:7px;">'
                    f'<span style="background:{theme_clr};color:#fff;border-radius:50%;'
                    f'width:18px;height:18px;display:flex;align-items:center;justify-content:center;'
                    f'font-size:9px;font-weight:700;flex-shrink:0;">{i}</span>'
                    f'<span style="font-size:11px;color:#334155;line-height:1.5;">{rec}</span></div>'
                    for i, rec in enumerate(REKOMENDASI.get(top_cat, REKOMENDASI["Lainnya"]), 1)
                )
                st.markdown(_rekomendasi_html, unsafe_allow_html=True)

                # Penyebab Tercatat
                _ST_DOT = {"Open":"#EF4444","Investigated":"#F59E0B","Resolved":"#22C55E"}
                _penyebab = df_titik[
                    df_titik["description"].notna() &
                    (df_titik["description"].astype(str).str.strip() != "")
                ].sort_values("updated_at", ascending=False).head(5)

                if not _penyebab.empty:
                    st.markdown(
                        '<div style="font-size:12px;font-weight:700;color:#0F172A;margin:16px 0 8px;">'
                        'Penyebab Tercatat</div>',
                        unsafe_allow_html=True
                    )
                    for _, _pr in _penyebab.iterrows():
                        _dot_clr = _ST_DOT.get(str(_pr.get("status","")), "#94A3B8")
                        _cat_p   = str(_pr.get("category","—"))
                        _date_p  = str(_pr.get("date",""))
                        _shift_p = str(_pr.get("shift",""))
                        _date_lbl = f"{_date_p} · S{_shift_p}" if _date_p and _shift_p else _date_p
                        _desc_p   = str(_pr.get("description","")).strip()
                        _desc_pts = [p.strip() for p in _desc_p.split("\n") if p.strip()]
                        if len(_desc_pts) == 1:
                            _desc_html = (
                                f'<div style="font-size:11px;color:#334155;'
                                f'margin-top:4px;line-height:1.5;">"{_desc_pts[0]}"</div>'
                            )
                        else:
                            _desc_html = "".join(
                                f'<div style="display:flex;gap:7px;align-items:flex-start;margin-top:4px;">'
                                f'<span style="background:{_dot_clr}22;color:{_dot_clr};border-radius:50%;'
                                f'width:16px;height:16px;display:flex;align-items:center;justify-content:center;'
                                f'font-size:8px;font-weight:700;flex-shrink:0;">{_di}</span>'
                                f'<span style="font-size:11px;color:#334155;line-height:1.5;">{_dp}</span></div>'
                                for _di, _dp in enumerate(_desc_pts, 1)
                            )
                        st.markdown(
                            f'<div style="border:1px solid {_dot_clr}44;border-left:3px solid {_dot_clr};'
                            f'padding:8px 12px;margin-bottom:6px;'
                            f'background:#fff;border-radius:0 8px 8px 0;">'
                            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:2px;">'
                            f'<span style="font-size:11px;font-weight:700;color:#0F172A;">{_cat_p}</span>'
                            f'<span style="font-size:10px;color:#94A3B8;">{_date_lbl}</span>'
                            f'</div>{_desc_html}</div>',
                            unsafe_allow_html=True
                        )

                # Action yang Pernah Berhasil
                _resolved_df = df_titik[
                    (df_titik["status"]=="Resolved") &
                    df_titik["corrective_action"].notna() &
                    (df_titik["corrective_action"].astype(str).str.strip() != "")
                ].sort_values("updated_at", ascending=False)

                if not _resolved_df.empty:
                    st.markdown(
                        '<div style="font-size:12px;font-weight:700;color:#16A34A;margin:16px 0 8px;">'
                        'Tindakan yang Pernah Berhasil</div>',
                        unsafe_allow_html=True
                    )
                    for _, _rv in _resolved_df.head(3).iterrows():
                        act         = str(_rv["corrective_action"]).strip()
                        _date_r     = str(_rv.get("date",""))
                        _shift_r    = str(_rv.get("shift",""))
                        _date_lbl_r = f"{_date_r} · S{_shift_r}" if _date_r and _shift_r else _date_r
                        _act_pts    = [p.strip() for p in act.split("\n") if p.strip()]
                        if len(_act_pts) <= 1:
                            _act_body = (
                                f'<span style="font-size:11px;color:#166534;">'
                                f'✓ {_act_pts[0] if _act_pts else act}</span>'
                            )
                        else:
                            _act_body = "".join(
                                f'<div style="display:flex;gap:7px;align-items:flex-start;margin-top:4px;">'
                                f'<span style="background:#16A34A;color:#fff;border-radius:50%;'
                                f'width:16px;height:16px;display:flex;align-items:center;justify-content:center;'
                                f'font-size:8px;font-weight:700;flex-shrink:0;">{_ai}</span>'
                                f'<span style="font-size:11px;color:#166534;line-height:1.5;">{_ap}</span></div>'
                                for _ai, _ap in enumerate(_act_pts, 1)
                            )
                        st.markdown(
                            f'<div style="background:#F0FDF4;border:1px solid #BBF7D0;'
                            f'border-left:3px solid #16A34A;border-radius:0 8px 8px 0;'
                            f'padding:8px 12px;margin-bottom:6px;">'
                            f'<div style="font-size:10px;color:#86EFAC;margin-bottom:2px;">{_date_lbl_r}</div>'
                            f'{_act_body}</div>',
                            unsafe_allow_html=True
                        )

    # ════════════════════════════════════════════════════════════
    # TAB 2 — POLA & TREN
    # ════════════════════════════════════════════════════════════
    def _render_pola(self, df_f: pd.DataFrame):
        if df_f.empty:
            st.info("Tidak ada data.")
            return

        COLORS = ["#EF4444","#F59E0B","#8B5CF6","#06B6D4","#10B981","#6366F1","#94A3B8"]

        # ── Row 1: RC per Shift + Tren Status ────────────────────
        col1, col2 = st.columns(2, gap="medium")

        with col1:
            if "shift" in df_f.columns:
                shift_cat = df_f.groupby(["shift","category"]).size().reset_index(name="n")
                shifts    = sorted(df_f["shift"].dropna().unique())
                series_sc = []
                for i, cat in enumerate(RC_CATEGORIES):
                    vals = []
                    for sh in shifts:
                        sub = shift_cat[(shift_cat["shift"]==sh)&(shift_cat["category"]==cat)]
                        vals.append(int(sub["n"].sum()) if not sub.empty else 0)
                    if any(v>0 for v in vals):
                        series_sc.append({"name":cat,"type":"bar","stack":"total","data":vals,
                                          "itemStyle":{"color":COLORS[i%len(COLORS)]}})
                st_echarts({
                    "title":{"text":"Pola Root Cause per Shift","textStyle":{"fontSize":13,"fontWeight":700}},
                    "tooltip":{"trigger":"axis","axisPointer":{"type":"shadow"}},
                    "legend":{"bottom":0,"icon":"roundRect","itemWidth":10,"textStyle":{"fontSize":9}},
                    "grid":{"top":36,"bottom":80,"left":40,"right":10},
                    "xAxis":{"type":"category","data":[f"S{s}" for s in shifts],"axisLabel":{"fontSize":11}},
                    "yAxis":{"type":"value","axisLabel":{"fontSize":10}},
                    "series":series_sc,
                }, height="320px", key="presc_shift_cat")

        with col2:
            if "inputted_at" in df_f.columns:
                df_t = df_f.copy()
                df_t["_day"] = pd.to_datetime(df_t["inputted_at"], errors="coerce").dt.strftime("%d %b")
                df_t = df_t.dropna(subset=["_day"])
                days = df_t["_day"].unique().tolist()
                SCLR = {"Open":"#EF4444","Investigated":"#F59E0B","Resolved":"#22C55E"}
                series_st = []
                for status, clr in SCLR.items():
                    vals = [len(df_t[(df_t["_day"]==d)&(df_t["status"]==status)]) for d in days]
                    series_st.append({"name":status,"type":"line","data":vals,"smooth":True,
                                      "symbol":"circle","symbolSize":6,
                                      "lineStyle":{"color":clr,"width":2},
                                      "itemStyle":{"color":clr},"areaStyle":{"opacity":0.08}})
                st_echarts({
                    "title":{"text":"Tren Status Root Cause per Hari","textStyle":{"fontSize":13,"fontWeight":700}},
                    "tooltip":{"trigger":"axis"},
                    "legend":{"data":list(SCLR.keys()),"top":8,"right":8,"icon":"circle","itemWidth":8,"textStyle":{"fontSize":10}},
                    "grid":{"top":36,"bottom":32,"left":40,"right":20},
                    "xAxis":{"type":"category","data":days,"axisLabel":{"fontSize":9,"rotate":20}},
                    "yAxis":{"type":"value","axisLabel":{"fontSize":10}},
                    "dataZoom":[{"type":"inside"}],
                    "series":series_st,
                }, height="320px", key="presc_tren_status")

        st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)

        # ── Row 2: Heatmap Part+Model × Kategori ─────────────────
        st.markdown('<div style="font-size:13px;font-weight:600;color:#0F172A;margin-bottom:8px;">Part+Model × Kategori Root Cause</div>', unsafe_allow_html=True)
        pm_cat = df_f.groupby(["part","model","category"]).size().reset_index(name="n")
        pm_keys = sorted((df_f["part"] + "|||" + df_f["model"]).unique().tolist())
        hm_data = []
        max_val = 0
        for xi, cat in enumerate(RC_CATEGORIES):
            for yi, pm in enumerate(pm_keys):
                parts2 = pm.split("|||", 1)
                p2, m2 = (parts2[0], parts2[1]) if len(parts2)==2 else (pm, "")
                sub = pm_cat[(pm_cat["part"]==p2)&(pm_cat["model"]==m2)&(pm_cat["category"]==cat)]
                val = int(sub["n"].sum()) if not sub.empty else 0
                if val > max_val: max_val = val
                hm_data.append([xi, yi, val])

        h_hm = max(180, len(pm_keys)*36 + 100)
        st_echarts({
            "tooltip":{"formatter":"function(p){return p.data[2]>0?'<b>'+p.marker+p.name+'</b><br/>'+p.data[2]:'';}"},
            "grid":{"top":24,"bottom":80,"left":120,"right":20},
            "xAxis":{"type":"category","data":RC_CATEGORIES,
                     "axisLabel":{"rotate":30,"fontSize":10},"splitArea":{"show":True}},
            "yAxis":{"type":"category","data":[p.replace("|||"," ") for p in pm_keys],
                     "axisLabel":{"fontSize":10},"splitArea":{"show":True}},
            "visualMap":{"min":0,"max":max(max_val,1),"calculable":True,
                         "orient":"horizontal","left":"center","bottom":10,
                         "inRange":{"color":["#FFF5F5","#EF4444"]},"textStyle":{"fontSize":9}},
            "series":[{"type":"heatmap","data":hm_data,
                       "label":{"show":True,"fontSize":9},
                       "emphasis":{"itemStyle":{"shadowBlur":10}}}],
        }, height=f"{h_hm}px", key="presc_hm_pm_cat")

        st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)

        # ── Row 3: Top Backlog Open ───────────────────────────────
        df_open = df_f[df_f["status"]=="Open"].copy()
        if not df_open.empty:
            st.markdown('<div style="font-size:13px;font-weight:600;color:#DC2626;margin-bottom:8px;">Backlog Open — Belum Ditindaklanjuti</div>', unsafe_allow_html=True)
            top_open = (df_open.groupby(["part","model","ref","parameter","category"])
                        .size().reset_index(name="n")
                        .sort_values("n", ascending=False).head(15))
            labels_o = [f"{r['ref']} · {r['parameter']} ({r['part']} {r['model']})"
                        for _, r in top_open.iterrows()]
            values_o = top_open["n"].tolist()
            cats_o   = top_open["category"].tolist()
            CAT_CLR  = {"Mesin / Machine":"#EF4444","Setup / Fixture":"#F59E0B",
                        "Material":"#8B5CF6","Operator":"#06B6D4",
                        "Program CMM":"#10B981","Tooling":"#6366F1","Lainnya":"#94A3B8"}
            h_open = max(260, len(labels_o)*28+60)
            st_echarts({
                "tooltip":{"trigger":"axis","axisPointer":{"type":"shadow"}},
                "grid":{"top":12,"right":80,"bottom":8,"left":8,"containLabel":True},
                "xAxis":{"type":"value"},
                "yAxis":{"type":"category","data":list(reversed(labels_o)),"axisLabel":{"fontSize":9}},
                "dataZoom":[{"type":"slider","yAxisIndex":0,
                             "start":max(0,100-round(10/max(len(labels_o),1)*100)),"end":100,
                             "width":15,"right":5,"borderColor":"transparent",
                             "fillerColor":"rgba(220,38,38,0.15)",
                             "handleStyle":{"color":"#DC2626"}}],
                "series":[{"type":"bar",
                           "data":[{"value":v,"itemStyle":{"color":CAT_CLR.get(c,"#94A3B8"),
                                                           "borderRadius":[0,4,4,0]}}
                                   for v,c in zip(reversed(values_o),reversed(cats_o))],
                           "label":{"show":True,"position":"right","fontSize":10}}],
            }, height=f"{h_open}px", key="presc_backlog_open")
        else:
            st.success("Tidak ada backlog Open saat ini.")
