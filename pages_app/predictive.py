"""
pages_app/predictive.py — Halaman Predictive (prediksi kualitas).
═══════════════════════════════════════════════════════════════════════
Dua mode utama:
  • AI Predictive — model XGBoost menaksir probabilitas NG shift berikutnya
    (tab Klasifikasi) dan proyeksi nilai aktual dengan ARIMA (tab Forecasting).
  • Deteksi SPC — deteksi 7 Nelson rules pada deret pengukuran, lalu
    proyeksikan tren linier ke depan untuk antisipasi pelanggaran.
Konstanta RULES di bawah mendefinisikan label, warna, dan deskripsi tiap rule.
"""
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from streamlit_echarts import st_echarts, JsCode
from utils.xgb_inference import run_xgb_inference, get_xgb_cache_key, _detect_kendali_shared as _detect_kendali

# ─────────────────────────────────────────────────────────────────
#  Definisi Aturan Deteksi Proses di Luar Kendali
# ─────────────────────────────────────────────────────────────────
RULES = {
    1: {"label": "Rule 1", "color": "#EF4444", "severity": "Critical",
        "desc": "1 titik di luar ±3σ"},
    2: {"label": "Rule 2", "color": "#F59E0B", "severity": "Warning",
        "desc": "Delapan titik data berurutan berada di satu sisi nilai rata-rata."},
    3: {"label": "Rule 3", "color": "#8B5CF6", "severity": "Warning",
        "desc": "Tujuh titik data berturut-turut yang meningkat atau menurun."},
    4: {"label": "Rule 4", "color": "#06B6D4", "severity": "Warning",
        "desc": "Empat belas titik data berurutan yang bergantian naik dan turun."},
    5: {"label": "Rule 5", "color": "#10B981", "severity": "Warning",
        "desc": "Dua titik data, dari tiga titik data berurutan, berada di sisi yang sama dari rata-rata di zona A atau di luarnya."},
    6: {"label": "Rule 6", "color": "#F97316", "severity": "Warning",
        "desc": "Empat titik data, dari lima titik data berurutan, berada di sisi yang sama dari rata-rata di zona B atau lebih jauh."},
    7: {"label": "Rule 7", "color": "#3B82F6", "severity": "Warning",
        "desc": "Lima belas titik data berurutan berada dalam zona C (di atas dan di bawah rata-rata)."},
}


@st.cache_data(ttl=1800, show_spinner=False)
def _build_kendali_history(df_all: pd.DataFrame) -> pd.DataFrame:
    """
    Scan seluruh data CMM, deteksi kondisi proses di luar kendali per titik ukur.
    Return DataFrame: Part, Model, Ref, Parameter, Rule, n_violations,
                      last_date, severity, Category
    """
    param_col = "point" if "point" in df_all.columns else "Parameter"
    records   = []

    has_sno    = "SampleNo" in df_all.columns
    group_keys = ["PartName", "ModelName", "ref", param_col]
    if has_sno:
        group_keys.append("SampleNo")

    for keys, grp in df_all.groupby(group_keys, sort=False):
        if has_sno:
            part, model, ref, param, sno = keys
        else:
            part, model, ref, param = keys
            sno = None

        ref_str = str(ref).strip()
        if ref_str in ("-", "nan", ""):
            ref_str = str(grp["ID"].iloc[0]).strip() if "ID" in grp.columns else "—"

        df_g = grp.sort_values(["Date","Shift","Cycle"]).dropna(subset=["Actual"])
        if len(df_g) < 2:
            continue

        values    = df_g["Actual"].tolist()
        vbr       = _detect_kendali(values)
        last_date = df_g["Date"].max().strftime("%d %b %Y")
        category  = grp["Category"].iloc[0] if "Category" in grp.columns else ""

        for rule_num, idxs in vbr.items():
            if not idxs:
                continue
            rec = {
                "Part":        part,
                "Model":       model,
                "Ref":         ref_str,
                "Parameter":   str(param),
                "Category":    category,
                "Rule":        rule_num,
                "Rule Label":  RULES[rule_num]["label"],
                "Deskripsi":   RULES[rule_num]["desc"],
                "Severity":    RULES[rule_num]["severity"],
                "n Titik":     len(idxs),
                "Terakhir":    last_date,
            }
            if sno is not None:
                rec["SampleNo"] = sno
            records.append(rec)

    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records).sort_values(
        ["Severity", "Rule", "n Titik"], ascending=[True, True, False]
    ).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────
#  Helper: load ilustrasi rule SPC sebagai base64
# ─────────────────────────────────────────────────────────────────
import base64 as _b64_spc
from pathlib import Path as _SpcPath

_SPC_RULE_IMG_DIR = _SpcPath("assets/ilustrasi/rule")

# Daftar nama file ilustrasi per rule — isi sesuai file yang tersedia
_RULE_IMG_FILES = {
    1: "spc_rule_1.png",
    2: "spc_rule_2.png",
    3: "spc_rule_3.png",
    4: "spc_rule_4.png",
    5: "spc_rule_5.png",
    6: "spc_rule_6.png",
    7: "spc_rule_7.png",
}
_RULE_IMG_CACHE: dict = {}

def _get_rule_img_html(r_num: int, border_clr: str) -> str:
    """Return <img> tag base64 atau placeholder teks kalau file tidak ada."""
    if r_num in _RULE_IMG_CACHE:
        return _RULE_IMG_CACHE[r_num]
    fname = _RULE_IMG_FILES.get(r_num, "")
    path  = _SPC_RULE_IMG_DIR / fname if fname else None
    if path and path.exists():
        ext  = path.suffix.lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        b64  = _b64_spc.b64encode(path.read_bytes()).decode()
        html = (f'<img src="data:{mime};base64,{b64}" '
                f'style="max-width:100%;max-height:78px;object-fit:contain;" '
                f'alt="Rule {r_num}"/>')
    else:
        html = (f'<span style="font-size:10px;color:#CBD5E1;">'
                f'📷 Rule {r_num} — tempatkan file <b>{fname or "spc_rule_"+str(r_num)+".jpg"}</b>'
                f' di folder assets/ilustrasi/</span>')
    _RULE_IMG_CACHE[r_num] = html
    return html


# ─────────────────────────────────────────────────────────────────
#  Page Class
# ─────────────────────────────────────────────────────────────────
class PredictivePage:
    def __init__(self, df_all: pd.DataFrame):
        self.df_all = df_all

    def render(self):
        st.markdown(
            '<div class="page-hdr">'
            '<span class="page-title">Predictive</span>'
            '<span class="page-sub">Prediksi kualitas berbasis AI & SPC</span>'
            '</div>',
            unsafe_allow_html=True
        )

        mode = st.segmented_control(
            "Mode", ["AI Predictive", "Deteksi SPC"],
            default="AI Predictive",
            key="pred_mode",
            label_visibility="collapsed",
        ) or "AI Predictive"

        _mode_desc = {
            "AI Predictive": "Model XGBoost memprediksi probabilitas NG pada shift berikutnya berdasarkan data historis.",
            "Deteksi SPC":   "Deteksi berbasis aturan statistik SPC — scan tren linier dan proyeksikan ke depan.",
        }
        st.markdown(f'<div class="section-desc">{_mode_desc[mode]}</div>', unsafe_allow_html=True)

        if mode == "AI Predictive":
            self._render_ai()
        else:
            self._render_spc()

    def _render_ai(self):
        tab_cls, tab_fc = st.tabs(["Klasifikasi", "Forecasting"])

        with tab_cls:
            st.markdown(
                '<div class="section-desc">Probabilitas NG per titik ukur pada shift berikutnya · diurutkan berdasarkan risiko tertinggi.</div>',
                unsafe_allow_html=True
            )
            self._render_klasifikasi()

        with tab_fc:
            st.markdown(
                '<div class="section-desc">Proyeksi nilai aktual ke depan menggunakan model ARIMA · estimasi kapan titik mendekati batas toleransi.</div>',
                unsafe_allow_html=True
            )
            self._render_forecasting()

    def _run_arima(self, y: list, forecast_n: int = 30):
        """Fit auto_arima dan return forecast. Return None kalau gagal."""
        try:
            from pmdarima import auto_arima as _auto_arima
            import warnings
            warnings.filterwarnings("ignore")
            model = _auto_arima(
                y, seasonal=False, stepwise=True,
                suppress_warnings=True, error_action="ignore",
                max_p=5, max_q=5, max_d=2,
                information_criterion="aic",
            )
            fc, ci = model.predict(n_periods=forecast_n, return_conf_int=True)
            return {"model": model, "order": model.order,
                    "aic": round(model.aic(), 2),
                    "fc": fc, "ci": ci}
        except Exception as e:
            return {"error": str(e)}

    def _render_forecasting(self):
        CACHE_CSV = Path("data/batch_arima_summary.csv")

        fc_mode = st.segmented_control(
            "Forecast mode",
            ["Satu Titik", "Batch Overview"],
            default="Satu Titik",
            key="pred_fc_mode",
            label_visibility="collapsed",
        ) or "Satu Titik"

        if fc_mode == "Satu Titik":
            self._render_forecast_single()
        else:
            self._render_forecast_batch(CACHE_CSV)

    def _render_forecast_single(self):
        df = self.df_all

        # ── Baris 1: Part·Model | SampleNo | Category ────────────
        # Cascade: combo → sampleno → ref → param
        combos_df_fc = (
            df[["PartName","ModelName"]].dropna().drop_duplicates()
            .sort_values(["PartName","ModelName"])
        )
        combo_opts_fc = ["Pilih Part & Model"] + [
            f"{r.PartName} · {r.ModelName}" for _, r in combos_df_fc.iterrows()
        ]
        if st.session_state.get("fc_combo") not in combo_opts_fc:
            st.session_state["fc_combo"] = "Pilih Part & Model"

        cur_combo_fc = st.session_state.get("fc_combo", "Pilih Part & Model")
        df_after_combo_fc = df.copy()
        f_part, f_model = "", ""
        if cur_combo_fc != "Pilih Part & Model":
            _sp = cur_combo_fc.split(" · ", 1)
            if len(_sp) == 2:
                f_part, f_model = _sp[0], _sp[1]
                df_after_combo_fc = df[(df["PartName"]==f_part)&(df["ModelName"]==f_model)]

        sno_vals_fc = sorted(
            df_after_combo_fc["SampleNo"].dropna().astype(str).unique().tolist(),
            key=lambda s: (0, int(s)) if s.isdigit() else (1, s)
        )
        sno_opts_fc = ["Semua Sample"] + sno_vals_fc
        if st.session_state.get("fc_sno") not in sno_opts_fc:
            st.session_state["fc_sno"] = "Semua Sample"

        c1, c2 = st.columns([2.5, 1.2], gap="small")
        with c1:
            f_combo_fc = st.selectbox("Part · Model", combo_opts_fc, key="fc_combo")
            if f_combo_fc != "Pilih Part & Model":
                _sp = f_combo_fc.split(" · ", 1)
                if len(_sp) == 2:
                    f_part, f_model = _sp[0], _sp[1]
                    df_after_combo_fc = df[(df["PartName"]==f_part)&(df["ModelName"]==f_model)]
        with c2:
            f_sno = st.selectbox("No. Sample", sno_opts_fc, key="fc_sno")

        # ── Baris 2: Ref | Parameter (cascade dari combo+sno) ────
        param_col = "point" if "point" in df.columns else "Parameter"
        df_pm = df_after_combo_fc.copy()
        if f_sno != "Semua Sample":
            df_pm = df_pm[df_pm["SampleNo"].astype(str) == f_sno]

        refs_fc = sorted([r for r in df_pm["ref"].dropna().astype(str).unique()
                          if r not in ("-","nan","")])
        ref_opts_fc = ["Pilih Ref / Point"] + refs_fc
        if st.session_state.get("fc_ref") not in ref_opts_fc:
            st.session_state["fc_ref"] = "Pilih Ref / Point"

        cur_ref_fc = st.session_state.get("fc_ref", "Pilih Ref / Point")
        df_pm_ref  = df_pm[df_pm["ref"].astype(str)==cur_ref_fc] if cur_ref_fc != "Pilih Ref / Point" else df_pm
        params_fc  = sorted([p for p in df_pm_ref[param_col].dropna().astype(str).unique()
                              if p not in ("","nan","-")])
        param_opts_fc = ["Pilih Parameter"] + params_fc
        if st.session_state.get("fc_param") not in param_opts_fc:
            st.session_state["fc_param"] = "Pilih Parameter"

        c4, c5 = st.columns([1.5, 2.5], gap="small")
        with c4:
            f_ref   = st.selectbox("Ref / Point", ref_opts_fc, key="fc_ref")
        with c5:
            f_param = st.selectbox("Parameter",   param_opts_fc, key="fc_param")

        c_hor1, c_hor2 = st.columns([1, 4], gap="small")
        with c_hor1:
            fc_n = st.number_input("Prediksi berapa shift kedepan", min_value=5, max_value=90, value=30, step=5, key="fc_n")

        if f_combo_fc == "Pilih Part & Model" or f_ref == "Pilih Ref / Point" or f_param == "Pilih Parameter":
            st.info("Pilih Part · Model, Ref, dan Parameter untuk melanjutkan.")
            return

        if not f_ref or not f_param:
            st.info("Pilih Ref dan Parameter untuk melanjutkan.")
            return

        df_sel = df_pm[df_pm["ref"].astype(str)==f_ref]
        df_sel = df_sel[df_sel[param_col].astype(str)==f_param]
        df_sel = df_sel.sort_values(["Date","Shift","Cycle"]).dropna(subset=["Deviation"])

        if len(df_sel) < 10:
            st.warning(f"Data terlalu sedikit ({len(df_sel)} observasi). Minimal 10 diperlukan.")
            return

        nominal  = float(df_sel["Nominal"].iloc[0])
        utol     = float(df_sel["Uppertol"].iloc[0])
        ltol     = float(df_sel["Lowertol"].iloc[0])
        usl      = round(nominal + utol, 5)
        lsl      = round(nominal + ltol, 5)
        y_dev    = df_sel["Deviation"].tolist()

        # KPI historis
        n_ok  = int((df_sel["Judgement"]=="OK").sum())
        n_ng  = int((df_sel["Judgement"]=="NG").sum())
        n_tot = len(df_sel)
        pct_ok= round(n_ok/n_tot*100,1)

        st.markdown(
            f'<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:12px 0 16px;">'
            + "".join([
                f'<div style="background:{bg};border-radius:8px;padding:10px;text-align:center;">'
                f'<div style="font-size:16px;font-weight:700;color:{fc};">{val}</div>'
                f'<div style="font-size:10px;color:#64748B;">{lbl}</div></div>'
                for bg, fc, val, lbl in [
                    ("#F8FAFC","#0F172A",n_tot,"Total data"),
                    ("#F0FDF4","#16A34A",f"{pct_ok}%","% OK"),
                    ("#FEF2F2","#DC2626",n_ng,"NG"),
                    ("#F8FAFC","#3B82F6",nominal,"Nominal"),
                    ("#F8FAFC","#334155",f"+{utol} / {ltol}","Toleransi"),
                ]
            ])
            + '</div>', unsafe_allow_html=True
        )

        if st.button("Jalankan", type="primary", key="fc_run"):
            with st.spinner(f"Fitting ARIMA untuk {f_ref} · {f_param}..."):
                result = self._run_arima(y_dev, int(fc_n))
            # Simpan result bersama meta-key agar tidak ambigu saat filter berubah
            _fc_meta_key = f"{f_combo_fc}|{f_sno}|{f_ref}|{f_param}|{fc_n}"
            st.session_state["fc_result"]     = result
            st.session_state["fc_result_key"] = _fc_meta_key
            st.session_state["fc_meta"]       = {
                "y_dev": y_dev, "nominal": nominal, "usl": usl, "lsl": lsl,
                "utol": utol, "ltol": ltol, "ref": f_ref, "param": f_param
            }

        # Ambil result — hanya tampilkan kalau masih relevan dengan pilihan saat ini
        _fc_meta_key_now = f"{f_combo_fc}|{f_sno}|{f_ref}|{f_param}|{fc_n}"
        result = st.session_state.get("fc_result") if st.session_state.get("fc_result_key") == _fc_meta_key_now else None
        meta   = st.session_state.get("fc_meta", {})
        if not result:
            return

        if "error" in result:
            st.error(f"ARIMA gagal: {result['error']}")
            return

        fc    = result["fc"]
        ci    = result["ci"]
        order = result["order"]
        y_dev_m = meta.get("y_dev", y_dev)
        nom_m   = meta.get("nominal", nominal)
        usl_m   = meta.get("usl", usl)
        lsl_m   = meta.get("lsl", lsl)
        utol_m  = meta.get("utol", utol)
        ltol_m  = meta.get("ltol", ltol)

        # Prediksi NG
        fc_ng  = [i+1 for i,v in enumerate(fc) if v > utol_m or v < ltol_m]
        fc_act = [round(v + nom_m, 5) for v in fc]
        fc_lo  = [round(v + nom_m, 5) for v in ci[:,0]]
        fc_hi  = [round(v + nom_m, 5) for v in ci[:,1]]

        # Status badge
        if fc_ng:
            risk_html = (f'<span style="background:#FEE2E2;color:#DC2626;font-size:11px;'
                         f'font-weight:700;padding:3px 10px;border-radius:99px;">'
                         f'⚠ Diprediksi NG pada shift ke-{fc_ng[0]}</span>')
        else:
            risk_html = (f'<span style="background:#DCFCE7;color:#16A34A;font-size:11px;'
                         f'font-weight:700;padding:3px 10px;border-radius:99px;">'
                         f'✓ Tidak ada prediksi NG dalam {int(fc_n)} shift berikutnya</span>')

        st.markdown(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'margin-bottom:8px;">'
            f'<span style="font-size:13px;font-weight:700;color:#0F172A;">'
            f'ARIMA{order} — {meta.get("ref","?")} · {meta.get("param","?")}</span>'
            f'{risk_html}</div>',
            unsafe_allow_html=True
        )

        # Chart ECharts — x-axis: Tanggal + Shift (history) dan F+N Shift (forecast)
        hist_n   = len(y_dev_m)
        act_hist = [round(v + nom_m, 5) for v in y_dev_m]

        # Build x-axis labels history dari df_sel (date + shift)
        x_hist_labels = df_sel.apply(
            lambda r: f"{r['Date'].strftime('%d %b')} S{r['Shift']}",
            axis=1
        ).tolist()

        # Build x-axis labels forecast: lanjutkan shift dari titik terakhir
        from datetime import timedelta as _td
        _last_date  = df_sel["Date"].iloc[-1].date()
        _last_shift = int(df_sel["Shift"].iloc[-1])
        _cur_date, _cur_shift = _last_date, _last_shift
        x_fc_labels = []
        for _i in range(int(fc_n)):
            _cur_shift += 1
            if _cur_shift > 3:
                _cur_shift = 1
                _cur_date += _td(days=1)
            x_fc_labels.append(f"{_cur_date.strftime('%d %b')} S{_cur_shift}")

        x_all_labels = x_hist_labels + x_fc_labels

        # Hitung Y range
        all_vals = act_hist + fc_act + fc_lo + fc_hi + [usl_m, lsl_m]
        all_vals = [v for v in all_vals if v is not None]
        y_min = round(min(all_vals) - abs(utol_m) * 0.5, 4)
        y_max = round(max(all_vals) + abs(utol_m) * 0.5, 4)

        # Tooltip: history tampilkan Aktual+Deviasi+Status, forecast tampilkan Pred+CI+Status
        _fc_status = ["NG" if (v > utol_m or v < ltol_m) else "OK" for v in fc]
        _fc_dev    = [round(v, 5) for v in fc]
        _hist_dev  = [round(v, 5) for v in y_dev_m]
        _hist_judg = df_sel["Judgement"].tolist()

        import json as _json_fc
        _tt_fc = JsCode(
            "function(params){"
            "var idx=params[0].dataIndex;"
            "var histN=" + str(hist_n) + ";"
            "var actHist=" + _json_fc.dumps(act_hist) + ";"
            "var histDev=" + _json_fc.dumps(_hist_dev) + ";"
            "var histJudg=" + _json_fc.dumps(_hist_judg) + ";"
            "var fcAct=" + _json_fc.dumps(fc_act) + ";"
            "var fcDev=" + _json_fc.dumps(_fc_dev) + ";"
            "var fcLo=" + _json_fc.dumps(fc_lo) + ";"
            "var fcHi=" + _json_fc.dumps(fc_hi) + ";"
            "var fcSt=" + _json_fc.dumps(_fc_status) + ";"
            "var lbl=params[0].axisValue;"
            "var html='<b>'+lbl+'</b><br/>';"
            "if(idx<histN){"
            "  var j=histJudg[idx]||'—';"
            "  var jc=j==='NG'?'#EF4444':'#22C55E';"
            "  html+='Aktual: <b>'+actHist[idx]+'</b><br/>';"
            "  html+='Deviasi: <b>'+histDev[idx]+'</b><br/>';"
            "  html+='Status: <b style=color:'+jc+';'+'>'+j+'</b>';"
            "} else {"
            "  var fi=idx-histN;"
            "  var st=fcSt[fi]||'—';"
            "  var sc=st==='NG'?'#EF4444':'#22C55E';"
            "  html+='Pred. Aktual: <b>'+fcAct[fi]+'</b><br/>';"
            "  html+='Pred. Deviasi: <b>'+fcDev[fi]+'</b><br/>';"
            "  html+='CI 95%: ['+fcLo[fi]+' — '+fcHi[fi]+']<br/>';"
            "  html+='Status: <b style=color:'+sc+';'+'>'+st+'</b>';"
            "}"
            "return html;}"
        )

        from streamlit_echarts import st_echarts as _ech
        _ech({
            "tooltip": {"trigger": "axis", "formatter": _tt_fc},
            "legend": {"data": ["Aktual","Forecast","USL/LSL"],
                       "bottom": 0, "icon": "circle", "itemWidth": 8},
            "grid": {"top": 16, "bottom": 54, "left": 60, "right": 80},
            "xAxis": {"type": "category",
                      "data": x_all_labels,
                      "axisLabel": {"rotate": 20, "fontSize": 9, "interval": "auto"}},
            "yAxis": {"type": "value", "min": y_min, "max": y_max,
                      "axisLabel": {"fontSize": 9}},
            "dataZoom": [{"type": "inside"}, {"type": "slider", "bottom": 8, "height": 20}],
            "series": [
                {"name": "Aktual", "type": "line",
                 "data": act_hist + [None]*int(fc_n),
                 "itemStyle": {"color": "#6366F1"}, "lineStyle": {"width": 1.5},
                 "symbol": "circle", "symbolSize": 5},
                {"name": "Forecast", "type": "line",
                 "data": [None]*hist_n + fc_act,
                 "itemStyle": {"color": "#F59E0B"},
                 "lineStyle": {"width": 2, "type": "dashed"},
                 "symbol": "circle", "symbolSize": 5},
                {"name": "USL/LSL", "type": "line",
                 "data": [usl_m] * (hist_n + int(fc_n)),
                 "lineStyle": {"color": "#EF4444", "width": 1, "type": "dashed"},
                 "itemStyle": {"color": "#EF4444"}, "symbol": "none"},
                {"name": "LSL_hidden", "type": "line",
                 "data": [lsl_m] * (hist_n + int(fc_n)),
                 "lineStyle": {"color": "#EF4444", "width": 1, "type": "dashed"},
                 "itemStyle": {"color": "#EF4444"}, "symbol": "none",
                 "legendHoverLink": False, "showSymbol": False},
            ],
        }, height="380px", key="fc_chart")

        # Tabel forecast — pakai label tanggal+shift
        df_fc = pd.DataFrame({
            "Tanggal · Shift": x_fc_labels,
            "Pred. Actual":    fc_act,
            "Lower 95%":       fc_lo,
            "Upper 95%":       fc_hi,
            "Pred. Deviation": [round(v, 5) for v in fc],
            "Status":          _fc_status,
        })
        st.dataframe(df_fc, use_container_width=True, hide_index=True,
                     height=min(400, 42 + len(df_fc)*36))


    @st.fragment
    def _render_klasifikasi(self):
        from datetime import date as _date, datetime as _dt

        # ── Deteksi shift berikutnya ──────────────────────────────
        cache_key, cur_shift, next_shift, next_date = get_xgb_cache_key()

        st.markdown(
            f'<div style="background:#EFF6FF;border-radius:8px;padding:12px 16px;'
            f'margin-bottom:16px;display:flex;justify-content:space-between;align-items:center;">'
            f'<div><div style="font-size:13px;font-weight:700;color:#1D4ED8;">Prediksi Shift Berikutnya</div>'
            f'<div style="font-size:11px;color:#3B82F6;margin-top:2px;">'
            f'Shift {cur_shift} sedang berjalan → memprediksi <b>Shift {next_shift} · '
            f'{next_date.strftime("%d %b %Y")}</b></div></div>'
            f'</div>',
            unsafe_allow_html=True
        )

        # ── Jalankan inference (shared cache dengan Dashboard) ────
        import time as _time
        ts_key = f"{cache_key}_ts"
        is_cached = (cache_key in st.session_state and
                     _time.time() - st.session_state.get(ts_key, 0) < 1800)

        if not is_cached:
            with st.spinner("Memuat prediksi model..."):
                result_df = run_xgb_inference(self.df_all)
        else:
            result_df = st.session_state.get(cache_key)

        if result_df is None or result_df.empty:
            st.info("Tidak ada hasil prediksi.")
            return

        result = result_df

        # ── Filter Baris 1: Risiko (pills) tetap di atas ──
        st.markdown('<div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:4px;">Tingkat Risiko</div>', unsafe_allow_html=True)
        f_risk = st.pills(
            "Tingkat Risiko",
            ["Semua Risiko", "🔴 Tinggi", "🟡 Sedang", "🟢 Rendah"],
            default="🔴 Tinggi", key="cls_filter",
            selection_mode="single", label_visibility="collapsed",
        ) or "Semua Risiko"

        # ── Filter Baris 2: Part·Model | Kategori | Sample No (selectbox cascade) ──
        combos_cls = (
            result[["PartName","ModelName"]].drop_duplicates()
            .sort_values(["PartName","ModelName"])
        )
        combo_cls_opts = ["Semua Part & Model"] + [
            f"{r.PartName} · {r.ModelName}" for _, r in combos_cls.iterrows()
        ]
        if st.session_state.get("cls_combo") not in combo_cls_opts:
            st.session_state["cls_combo"] = "Semua Part & Model"

        cur_cls_combo = st.session_state.get("cls_combo", "Semua Part & Model")
        df_cls_combo  = result.copy()
        if cur_cls_combo != "Semua Part & Model":
            _sp = cur_cls_combo.split(" · ", 1)
            if len(_sp) == 2:
                df_cls_combo = result[(result["PartName"]==_sp[0])&(result["ModelName"]==_sp[1])]

        cat_cls_vals = sorted(df_cls_combo["Category"].dropna().unique().tolist()) if "Category" in df_cls_combo.columns else []
        cat_cls_opts = ["Semua Kategori"] + cat_cls_vals
        if st.session_state.get("cls_cat") not in cat_cls_opts:
            st.session_state["cls_cat"] = "Produksi" if "Produksi" in cat_cls_opts else "Semua Kategori"

        cur_cls_cat = st.session_state.get("cls_cat", "Semua Kategori")
        df_cls_cat  = df_cls_combo[df_cls_combo["Category"]==cur_cls_cat] if cur_cls_cat != "Semua Kategori" and "Category" in df_cls_combo.columns else df_cls_combo

        sno_cls_vals = sorted(
            df_cls_cat["SampleNo"].dropna().astype(str).unique().tolist(),
            key=lambda s: (0, int(s)) if s.isdigit() else (1, s)
        )
        sno_cls_opts = ["Semua Sample"] + sno_cls_vals
        if st.session_state.get("cls_sno") not in sno_cls_opts:
            st.session_state["cls_sno"] = "Semua Sample"

        # ── KP → ref → param (cascade dari sno) ──────────────
        cur_cls_sno = st.session_state.get("cls_sno", "Semua Sample")
        df_cls_sno  = df_cls_cat[df_cls_cat["SampleNo"].astype(str)==cur_cls_sno] if cur_cls_sno != "Semua Sample" else df_cls_cat

        _ref_col_cls   = "ref"   if "ref"   in df_cls_sno.columns else "PartName"
        _param_col_cls = "point" if "point" in df_cls_sno.columns else "Parameter"

        ref_cls_vals = sorted([r for r in df_cls_sno[_ref_col_cls].dropna().astype(str).unique() if r not in ("","-","nan")])
        ref_cls_opts = ["Semua Ref / Point"] + ref_cls_vals
        if st.session_state.get("cls_ref") not in ref_cls_opts:
            st.session_state["cls_ref"] = "Semua Ref / Point"

        cur_cls_ref  = st.session_state.get("cls_ref", "Semua Ref / Point")
        df_cls_ref   = df_cls_sno[df_cls_sno[_ref_col_cls].astype(str)==cur_cls_ref] if cur_cls_ref != "Semua Ref / Point" else df_cls_sno

        param_cls_vals = sorted([p for p in df_cls_ref[_param_col_cls].dropna().astype(str).unique() if p not in ("","-","nan")])
        param_cls_opts = ["Semua Parameter"] + param_cls_vals
        if st.session_state.get("cls_param") not in param_cls_opts:
            st.session_state["cls_param"] = "Semua Parameter"

        kp_cls_opts = ["Semua Titik", "KP saja"]
        if st.session_state.get("cls_kp") not in kp_cls_opts:
            st.session_state["cls_kp"] = "Semua Titik"

        cls_r2c1, cls_r2c2, cls_r2c3 = st.columns([2.5, 1.4, 1.2], gap="small")
        with cls_r2c1:
            f_combo_cls = st.selectbox("Part · Model", combo_cls_opts, key="cls_combo")
        with cls_r2c2:
            f_cat = st.selectbox("Kategori", cat_cls_opts, key="cls_cat")
        with cls_r2c3:
            f_sno_cls = st.selectbox("No. Sample", sno_cls_opts, key="cls_sno")

        cls_r3c1, cls_r3c2, cls_r3c3 = st.columns([1.2, 1.5, 2.5], gap="small")
        with cls_r3c1:
            f_kp_cls = st.selectbox("Kritikal Point", kp_cls_opts, key="cls_kp")
        with cls_r3c2:
            f_ref_cls = st.selectbox("Ref / Point", ref_cls_opts, key="cls_ref")
        with cls_r3c3:
            f_param_cls = st.selectbox("Parameter", param_cls_opts, key="cls_param")

        # Terapkan semua filter
        df_filtered = result.copy()
        if f_risk != "Semua Risiko":
            df_filtered = df_filtered[df_filtered["Risiko"]==f_risk]
        if f_combo_cls != "Semua Part & Model":
            _sp = f_combo_cls.split(" · ", 1)
            if len(_sp) == 2:
                df_filtered = df_filtered[(df_filtered["PartName"]==_sp[0])&(df_filtered["ModelName"]==_sp[1])]
        if f_cat != "Semua Kategori" and "Category" in df_filtered.columns:
            df_filtered = df_filtered[df_filtered["Category"]==f_cat]
        if f_sno_cls != "Semua Sample":
            df_filtered = df_filtered[df_filtered["SampleNo"].astype(str)==f_sno_cls]
        if f_kp_cls == "KP saja" and "KP" in df_filtered.columns:
            df_filtered = df_filtered[df_filtered["KP"].astype(str).isin(["1","1.0","True"])]
        if f_ref_cls != "Semua Ref / Point" and _ref_col_cls in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[_ref_col_cls].astype(str)==f_ref_cls]
        if f_param_cls != "Semua Parameter" and _param_col_cls in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[_param_col_cls].astype(str)==f_param_cls]

        df_show = df_filtered.copy()

        # ── KPI responsif filter ──────────────────────────────────
        n_ng   = int((df_show["Pred"]=="NG").sum())
        n_ok   = int((df_show["Pred"]=="OK").sum())
        n_tot  = len(df_show)
        n_high = int(df_show["Risiko"].str.startswith("🔴").sum())

        st.markdown(
            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px;">'
            + "".join([
                f'<div style="background:{bg};border-radius:8px;padding:12px;text-align:center;">'
                f'<div style="font-size:22px;font-weight:700;color:{fc};">{val}</div>'
                f'<div style="font-size:10px;color:#64748B;">{lbl}</div></div>'
                for bg, fc, val, lbl in [
                    ("#F8FAFC","#0F172A",n_tot,"Total Titik"),
                    ("#FEF2F2","#DC2626",n_ng,"Prediksi NG"),
                    ("#F0FDF4","#16A34A",n_ok,"Prediksi OK"),
                    ("#FFFBEB","#D97706",n_high,"Risiko Tinggi"),
                ]
            ])
            + '</div>', unsafe_allow_html=True
        )

        if n_ng > 0:
            st.error(f"⚠️ **{n_ng} titik** diprediksi NG pada "
                     f"Shift {next_shift} · {next_date.strftime('%d %b %Y')}")

        sc = ["PartName","ModelName","ref","point","SampleNo","KP","Prob_NG","Pred","Risiko"]
        sc = [c for c in sc if c in df_show.columns]
        df_tbl = df_show[sc].sort_values("Prob_NG", ascending=False).reset_index(drop=True)
        _col_rename = {"PartName":"Part","ModelName":"Model","ref":"Ref","point":"Parameter",
                       "SampleNo":"Sample No","KP":"KP","Prob_NG":"Prob NG (%)","Pred":"Prediksi","Risiko":"Risiko"}
        df_tbl.columns = [_col_rename.get(c,c) for c in sc]
        st.dataframe(df_tbl, use_container_width=True, hide_index=True,
                     height=min(520, 42 + len(df_tbl)*36))

    def _render_forecast_batch(self, cache_path):

        st.markdown(
            '<div style="font-size:13px;font-weight:600;color:#0F172A;margin-bottom:12px;">'
            'Batch Forecast — Semua Kombinasi</div>',
            unsafe_allow_html=True
        )

        has_cache = Path(cache_path).exists()
        cc1, cc2 = st.columns([3,1], gap="small")
        with cc2:
            if st.button("Jalankan Forecast", use_container_width=True,
                         type="primary" if not has_cache else "secondary",
                         key="fc_batch_run"):
                self._run_batch_arima(cache_path)
                st.rerun()

        if not has_cache:
            st.info("Belum ada hasil batch. Klik 'Generate Forecast' untuk memulai (bisa memakan beberapa menit).")
            return

        df_batch = pd.read_csv(cache_path)
        n_total  = len(df_batch)
        n_risk   = int((df_batch["Prediksi_NG_Shift"]>0).sum())
        n_stable = n_total - n_risk

        st.markdown(
            f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px;">'
            + "".join([
                f'<div style="background:{bg};border-radius:8px;padding:12px;text-align:center;">'
                f'<div style="font-size:22px;font-weight:700;color:{fc};">{val}</div>'
                f'<div style="font-size:10px;color:#64748B;">{lbl}</div></div>'
                for bg, fc, val, lbl in [
                    ("#F8FAFC","#0F172A",n_total,"Total Kombinasi"),
                    ("#FEF2F2","#DC2626",n_risk,"Berisiko NG"),
                    ("#F0FDF4","#16A34A",n_stable,"Stabil"),
                ]
            ])
            + '</div>', unsafe_allow_html=True
        )

        # Filter
        f_risk = st.pills("Filter", ["Semua","Berisiko NG","Stabil"],
                           default="Berisiko NG", key="batch_filter",
                           selection_mode="single", label_visibility="collapsed") or "Berisiko NG"
        if f_risk == "Berisiko NG":
            df_show = df_batch[df_batch["Prediksi_NG_Shift"]>0].sort_values("Prediksi_NG_Shift")
        elif f_risk == "Stabil":
            df_show = df_batch[df_batch["Prediksi_NG_Shift"]==0]
        else:
            df_show = df_batch

        cols_show = ["Part","Model","SampleNo","Ref","Point",
                     "ARIMA_Order","Tren","Prediksi_NG_Shift","Status"]
        cols_show = [c for c in cols_show if c in df_show.columns]
        st.dataframe(df_show[cols_show].reset_index(drop=True),
                     use_container_width=True, hide_index=True,
                     height=min(500, 42 + len(df_show)*36))

    # ═════════════════════════════════════════════════════════════════
    #  📐 PREDIKSI RULE — Scan otomatis semua titik (pola Klasifikasi)
    # ═════════════════════════════════════════════════════════════════
    @st.fragment
    def _render_prediksi_rule(self):
        import numpy as np
        import time as _time

        df        = self.df_all
        param_col = "point" if "point" in df.columns else "Parameter"
        ref_col   = "ref"   if "ref"   in df.columns else "ID"

        # ── Banner info ───────────────────────────────────────────
        st.markdown(
            '<div style="background:#F0FDF4;border-radius:8px;padding:12px 16px;'
            'margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;">'
            '<div>'
            '<div style="font-size:13px;font-weight:700;color:#166534;">Prediksi Rule SPC — Linear Trend</div>'
            '<div style="font-size:11px;color:#16A34A;margin-top:2px;">'
            'Scan otomatis semua titik ukur · proyeksikan tren ke depan · deteksi rule sebelum terjadi</div>'
            '</div></div>',
            unsafe_allow_html=True
        )

        # ── Filter Baris 1: Part·Model | Kategori | KP ───────────
        combos_pr = (
            df[["PartName","ModelName"]].dropna().drop_duplicates()
            .sort_values(["PartName","ModelName"])
        )
        combo_pr_opts = ["Semua Part & Model"] + [
            f"{r.PartName} · {r.ModelName}" for _, r in combos_pr.iterrows()
        ]
        if st.session_state.get("pr_combo") not in combo_pr_opts:
            st.session_state["pr_combo"] = "Semua Part & Model"

        cur_pr_combo = st.session_state.get("pr_combo", "Semua Part & Model")
        df_pr_base   = df.copy()
        if cur_pr_combo != "Semua Part & Model":
            _sp = cur_pr_combo.split(" · ", 1)
            if len(_sp) == 2:
                df_pr_base = df[(df["PartName"]==_sp[0])&(df["ModelName"]==_sp[1])]

        cat_pr_vals = sorted(df_pr_base["Category"].dropna().unique().tolist()) if "Category" in df_pr_base.columns else []
        cat_pr_opts = ["Semua Kategori"] + cat_pr_vals
        if st.session_state.get("pr_cat") not in cat_pr_opts:
            st.session_state["pr_cat"] = "Produksi" if "Produksi" in cat_pr_opts else "Semua Kategori"

        kp_pr_opts = ["Semua Titik", "KP saja"]
        if st.session_state.get("pr_kp") not in kp_pr_opts:
            st.session_state["pr_kp"] = "Semua Titik"

        pr_r1c1, pr_r1c2, pr_r1c3 = st.columns([2.5, 1.4, 1.1], gap="small")
        with pr_r1c1:
            f_pr_combo = st.selectbox("Part · Model", combo_pr_opts, key="pr_combo")
        with pr_r1c2:
            f_pr_cat = st.selectbox("Kategori", cat_pr_opts, key="pr_cat")
        with pr_r1c3:
            f_pr_kp = st.selectbox("KP", kp_pr_opts, key="pr_kp")

        # ── Filter Baris 2: SampleNo ──────────────────────────────
        df_pr_filt = df_pr_base.copy()
        if f_pr_combo != "Semua Part & Model":
            _sp = f_pr_combo.split(" · ", 1)
            if len(_sp) == 2:
                df_pr_filt = df_pr_base[(df_pr_base["PartName"]==_sp[0])&(df_pr_base["ModelName"]==_sp[1])]
        if f_pr_cat != "Semua Kategori" and "Category" in df_pr_filt.columns:
            df_pr_filt = df_pr_filt[df_pr_filt["Category"]==f_pr_cat]
        if f_pr_kp == "KP saja" and "KP" in df_pr_filt.columns:
            df_pr_filt = df_pr_filt[df_pr_filt["KP"].astype(str).isin(["1","1.0","True"])]

        sno_pr_vals = sorted(
            df_pr_filt["SampleNo"].dropna().astype(str).unique().tolist(),
            key=lambda s: (0, int(s)) if s.isdigit() else (1, s)
        )
        sno_pr_opts = ["Semua Sample"] + sno_pr_vals
        if st.session_state.get("pr_sno") not in sno_pr_opts:
            st.session_state["pr_sno"] = "Semua Sample"

        pr_r2c1, pr_r2c2, pr_r2c3 = st.columns([1.2, 1.5, 2.5], gap="small")
        with pr_r2c1:
            f_pr_sno = st.selectbox("No. Sample", sno_pr_opts, key="pr_sno")

        if f_pr_sno != "Semua Sample":
            df_pr_filt = df_pr_filt[df_pr_filt["SampleNo"].astype(str)==f_pr_sno]

        # Ref / Point & Parameter cascade dari sno
        ref_pr_vals = sorted([r for r in df_pr_filt[ref_col].dropna().astype(str).unique()
                              if r not in ("","-","nan")])
        ref_pr_opts = ["Semua Ref / Point"] + ref_pr_vals
        if st.session_state.get("pr_ref") not in ref_pr_opts:
            st.session_state["pr_ref"] = "Semua Ref / Point"

        cur_pr_ref    = st.session_state.get("pr_ref", "Semua Ref / Point")
        df_pr_ref_tmp = df_pr_filt[df_pr_filt[ref_col].astype(str)==cur_pr_ref] if cur_pr_ref != "Semua Ref / Point" else df_pr_filt
        param_pr_vals = sorted([p for p in df_pr_ref_tmp[param_col].dropna().astype(str).unique()
                                if p not in ("","-","nan")])
        param_pr_opts = ["Semua Parameter"] + param_pr_vals
        if st.session_state.get("pr_param") not in param_pr_opts:
            st.session_state["pr_param"] = "Semua Parameter"

        with pr_r2c2:
            f_pr_ref   = st.selectbox("Ref / Point", ref_pr_opts, key="pr_ref")
        with pr_r2c3:
            f_pr_param = st.selectbox("Parameter",   param_pr_opts, key="pr_param")

        # ── Baris 3: n_hist + n_fc di bawah semua filter ─────────
        pr_r3c1, pr_r3c2, _ = st.columns([1.5, 1.5, 2.0], gap="small")
        with pr_r3c1:
            n_hist = st.number_input("Data historis (shift)", min_value=10, max_value=100,
                                     value=20, step=5, key="pr_n_hist",
                                     help="Jumlah shift terakhir yang dipakai untuk hitung tren")
        with pr_r3c2:
            n_fc = st.number_input("Prediksi ke depan (shift)", min_value=1,
                                   max_value=50, value=10, step=1, key="pr_n_fc")

        if f_pr_ref != "Semua Ref / Point":
            df_pr_filt = df_pr_filt[df_pr_filt[ref_col].astype(str)==f_pr_ref]
        if f_pr_param != "Semua Parameter":
            df_pr_filt = df_pr_filt[df_pr_filt[param_col].astype(str)==f_pr_param]

        # ── Cache key — scan ulang kalau filter berubah ───────────
        f_pr_ref_k   = st.session_state.get("pr_ref",   "Semua Ref / Point")
        f_pr_param_k = st.session_state.get("pr_param", "Semua Parameter")
        cache_key = f"pr_result_{f_pr_combo}_{f_pr_cat}_{f_pr_kp}_{f_pr_sno}_{f_pr_ref_k}_{f_pr_param_k}_{int(n_hist)}_{int(n_fc)}"
        ts_key    = f"{cache_key}_ts"
        TTL       = 1800  # 30 menit

        # ── Coba pakai shared cache kalau filter = default ────────
        from utils.xgb_inference import RULE_CACHE_KEY, run_rule_prediction
        _is_default = (
            f_pr_combo  == "Semua Part & Model" and
            f_pr_cat    in ("Produksi", "Semua Kategori") and
            f_pr_kp     == "Semua Titik" and
            f_pr_sno    == "Semua Sample" and
            f_pr_ref_k  == "Semua Ref / Point" and
            f_pr_param_k == "Semua Parameter" and
            int(n_hist) == 20 and int(n_fc) == 10
        )

        if _is_default:
            # Pakai shared cache — warmup sudah jalan saat login
            _rts_k = f"{RULE_CACHE_KEY}_ts"
            if RULE_CACHE_KEY not in st.session_state or \
               _time.time() - st.session_state.get(_rts_k, 0) > TTL:
                with st.spinner("🔍 Menghitung tren & prediksi rule..."):
                    run_rule_prediction(df_pr_filt)
            all_rows = st.session_state.get(RULE_CACHE_KEY) or []
        else:
            # Filter spesifik — scan subset data
            if cache_key not in st.session_state or \
               _time.time() - st.session_state.get(ts_key, 0) > TTL:

                all_rows = []
                group_keys = [col for col in ["PartName","ModelName","SampleNo", ref_col, param_col]
                              if col in df_pr_filt.columns]

                with st.spinner("🔍 Menghitung tren & prediksi rule semua titik..."):
                    for keys, grp in df_pr_filt.groupby(group_keys, sort=False):
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

                        y_all  = grp_s["Actual"].tolist()
                        y_use  = y_all[-int(n_hist):]
                        n_use  = len(y_use)
                        if n_use < 5:
                            continue

                        nom   = float(grp_s["Nominal"].dropna().iloc[0])  if grp_s["Nominal"].notna().any()  else 0.0
                        utol  = float(grp_s["Uppertol"].dropna().iloc[0]) if grp_s["Uppertol"].notna().any() else 0.0
                        ltol  = float(grp_s["Lowertol"].dropna().iloc[0]) if grp_s["Lowertol"].notna().any() else 0.0
                        usl   = round(nom + utol, 5)
                        lsl   = round(nom + ltol, 5)

                        x_arr   = np.arange(n_use)
                        slope, intercept = np.polyfit(x_arr, y_use, 1)

                        x_fc_arr = np.arange(n_use, n_use + int(n_fc))
                        y_fc     = (slope * x_fc_arr + intercept).tolist()

                        y_combined   = y_use + y_fc
                        vbr_combined = _detect_kendali(y_combined)

                        has_hist_violation = any(
                            any(i < n_use for i in idxs)
                            for idxs in vbr_combined.values() if idxs
                        )
                        fc_rules_violated = [
                            r for r, idxs in vbr_combined.items()
                            if any(i >= n_use for i in idxs)
                        ]
                        n_fc_ng   = sum(1 for v in y_fc if v > usl or v < lsl)
                        trend_lbl = "📈 Naik" if slope > 1e-6 else ("📉 Turun" if slope < -1e-6 else "➡ Stabil")

                        shifts_to_batas = None
                        if slope > 1e-9:
                            s = (usl - y_use[-1]) / slope
                            if 0 < s <= 50: shifts_to_batas = int(s)
                        elif slope < -1e-9:
                            s = (lsl - y_use[-1]) / slope
                            if 0 < s <= 50: shifts_to_batas = int(s)

                        status = "🔴 Rule Terpicu" if fc_rules_violated else \
                                 ("🟡 NG Prediksi" if n_fc_ng > 0 else \
                                 ("⚠ Tren Menuju Batas" if shifts_to_batas else "🟢 Aman"))

                        all_rows.append({
                            "Part":        part,
                            "Model":       model,
                            "Sample":      sno,
                            "Ref":         ref,
                            "Parameter":   param,
                            "KP":          kp,
                            "n Data":      n_use,
                            "Slope (mm/sh)": round(slope, 6),
                            "Tren":        trend_lbl,
                            "NG Prediksi": n_fc_ng,
                            "Rule Terpicu":len(fc_rules_violated),
                            "Rule List":   ", ".join([f"R{r}" for r in sorted(fc_rules_violated)]) or "-",
                            "Est. Shift ke Batas": shifts_to_batas if shifts_to_batas else "-",
                            "Status":      status,
                            "_y_use":      y_use,
                            "_y_fc":       y_fc,
                            "_usl":        usl,
                            "_lsl":        lsl,
                            "_nom":        nom,
                            "_vbr":        vbr_combined,
                            "_n_use":      n_use,
                        })

                st.session_state[cache_key] = all_rows
                st.session_state[ts_key]    = _time.time()

            all_rows = st.session_state[cache_key]

        if not all_rows:
            st.info("Tidak ada data cukup untuk prediksi. Pastikan filter sesuai dan data minimal 10 poin per titik.")
            return

        # ── KPI Summary ───────────────────────────────────────────
        n_total    = len(all_rows)
        n_rule     = sum(1 for r in all_rows if r["Rule Terpicu"] > 0)
        n_ng_pred  = sum(1 for r in all_rows if r["NG Prediksi"] > 0)
        n_batas    = sum(1 for r in all_rows if r["Est. Shift ke Batas"] != "-")
        n_aman     = sum(1 for r in all_rows if r["Status"] == "🟢 Aman")

        st.markdown(
            f'<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:12px 0 16px;">'            + "".join([
                f'<div style="background:{bg};border-radius:8px;padding:12px;text-align:center;">'                f'<div style="font-size:22px;font-weight:700;color:{fc};">{val}</div>'                f'<div style="font-size:10px;color:#64748B;margin-top:2px;">{lbl}</div></div>'
                for bg, fc, val, lbl in [
                    ("#F8FAFC","#0F172A",   n_total,  "Total Titik"),
                    ("#FEF2F2","#DC2626",   n_rule,   "Rule Terpicu (forecast)"),
                    ("#FEF2F2","#DC2626",   n_ng_pred,"Prediksi NG"),
                    ("#FFFBEB","#D97706",   n_batas,  "Menuju Batas Toleransi"),
                    ("#F0FDF4","#16A34A",   n_aman,   "Aman"),
                ]
            ])
            + '</div>',
            unsafe_allow_html=True
        )

        # ── Filter hasil ──────────────────────────────────────────
        STATUS_OPTS = ["Semua Status", "🔴 Rule Terpicu", "🟡 NG Prediksi",
                       "⚠ Tren Menuju Batas", "🟢 Aman"]
        if st.session_state.get("pr_status_filter") not in STATUS_OPTS:
            st.session_state["pr_status_filter"] = "🔴 Rule Terpicu"

        st.markdown('<div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:4px;">🔎 Filter Hasil</div>',
                    unsafe_allow_html=True)
        f_pr_status = st.pills(
            "Status hasil", STATUS_OPTS,
            default="🔴 Rule Terpicu", key="pr_status_filter",
            selection_mode="single", label_visibility="collapsed",
        ) or "🔴 Rule Terpicu"

        rows_show = [r for r in all_rows
                     if f_pr_status == "Semua Status" or r["Status"] == f_pr_status]

        if not rows_show:
            st.info(f"Tidak ada titik dengan status '{f_pr_status}'.")
            return

        # ── Tabel hasil ───────────────────────────────────────────
        DISPLAY_COLS = ["Part","Model","Sample","Ref","Parameter","KP",
                        "Tren","Slope (mm/sh)","NG Prediksi","Rule Terpicu",
                        "Rule List","Est. Shift ke Batas","Status"]
        df_res = pd.DataFrame([{c: r[c] for c in DISPLAY_COLS} for r in rows_show])
        df_res = df_res.sort_values(["Rule Terpicu","NG Prediksi"], ascending=False).reset_index(drop=True)

        STATUS_CLR_MAP = {
            "🔴 Rule Terpicu":      "background:#FEE2E2;color:#991B1B;font-weight:700;",
            "🟡 NG Prediksi":       "background:#FEF3C7;color:#92400E;font-weight:700;",
            "⚠ Tren Menuju Batas":  "background:#FFF7ED;color:#C2410C;font-weight:700;",
            "🟢 Aman":              "background:#DCFCE7;color:#166534;font-weight:700;",
        }

        def _style_row(row):
            styles = [""] * len(row)
            idx = list(row.index)
            if "Status" in idx:
                styles[idx.index("Status")] = STATUS_CLR_MAP.get(row["Status"],"")
            if "KP" in idx and row["KP"]:
                styles[idx.index("KP")] = "background:#FEF9C3;color:#713F12;font-weight:700;"
            if "NG Prediksi" in idx and row["NG Prediksi"] > 0:
                styles[idx.index("NG Prediksi")] = "color:#DC2626;font-weight:700;"
            if "Rule Terpicu" in idx and row["Rule Terpicu"] > 0:
                styles[idx.index("Rule Terpicu")] = "color:#DC2626;font-weight:700;"
            return styles

        st.markdown(
            f'<div style="font-size:12px;color:#64748B;margin-bottom:6px;">'            f'Klik baris untuk lihat grafik tren + prediksi · {len(rows_show)} titik ditampilkan</div>',
            unsafe_allow_html=True
        )

        if st.session_state.pop("pr_clear_sel", False):
            st.session_state.pop("pr_result_tbl", None)

        sel = st.dataframe(
            df_res.style.apply(_style_row, axis=1),
            use_container_width=True,
            hide_index=True,
            height=min(520, 42 + len(df_res)*36),
            on_select="rerun",
            selection_mode="single-row",
            key="pr_result_tbl",
            column_config={
                "KP": st.column_config.CheckboxColumn("KP", width="small"),
                "Slope (mm/sh)": st.column_config.NumberColumn("Slope", format="%.6f"),
            }
        )

        # ── Chart detail untuk baris yang diklik ─────────────────
        sel_rows = sel.selection.rows if sel and hasattr(sel, "selection") else []
        if not sel_rows:
            return
        row_idx = sel_rows[0]
        if row_idx >= len(rows_show):
            return
        row    = rows_show[row_idx]
        y_use  = row["_y_use"]
        y_fc   = row["_y_fc"]
        usl_d  = row["_usl"]
        lsl_d  = row["_lsl"]
        nom_d  = row["_nom"]
        vbr_c  = row["_vbr"]
        n_use  = row["_n_use"]
        n_fc_i = len(y_fc)

        RC = {1:"#EF4444",2:"#F59E0B",3:"#8B5CF6",
              4:"#06B6D4",5:"#10B981",6:"#F97316",7:"#3B82F6"}

        mean_v  = float(np.mean(y_use))
        sigma_v = float(np.std(y_use, ddof=1)) if n_use > 1 else 0.0
        ucl_v   = round(mean_v + 3*sigma_v, 5)
        lcl_v   = round(mean_v - 3*sigma_v, 5)

        # X labels: dd %b S{shift} persis SPC
        df_chart = df_pr_filt[
            (df_pr_filt["PartName"].astype(str)==str(row["Part"])) &
            (df_pr_filt["ModelName"].astype(str)==str(row["Model"])) &
            (df_pr_filt["SampleNo"].astype(str)==str(row["Sample"])) &
            (df_pr_filt[ref_col].astype(str)==str(row["Ref"])) &
            (df_pr_filt[param_col].astype(str)==str(row["Parameter"]))
        ].sort_values(["Date","Shift","Cycle"]).dropna(subset=["Actual"]).tail(n_use).reset_index(drop=True)

        if len(df_chart) == n_use:
            x_hist_lbl = df_chart.apply(
                lambda r: f"{r['Date'].strftime('%d %b')} S{r['Shift']}", axis=1
            ).tolist()
            last_date  = df_chart["Date"].iloc[-1]
            last_shift = int(df_chart["Shift"].iloc[-1])
            fc_labels  = []
            cd, cs = last_date, last_shift
            for _ in range(n_fc_i):
                cs += 1
                if cs > 3:
                    cs = 1
                    cd = cd + pd.Timedelta(days=1)
                fc_labels.append(f"{cd.strftime('%d %b')} S{cs}")
        else:
            x_hist_lbl = [f"H{i+1}" for i in range(n_use)]
            fc_labels  = [f"F+{i+1}" for i in range(n_fc_i)]

        x_all = x_hist_lbl + fc_labels
        n_all = len(x_all)

        # Build peta: index → list rule yang terpicu di titik itu
        def _rules_at(idx: int) -> list:
            return [r for r in range(1,8) if idx in vbr_c[r]]

        # Style titik — border tebal + tooltip rule
        def _pt_h(i, v):
            rules_here = _rules_at(i)
            val_str    = round(v, 5)
            if rules_here:
                # Warna border = rule dengan prioritas tertinggi (rule terkecil = paling kritis)
                border_clr = RC[rules_here[0]]
                rule_txt   = ", ".join(f"Rule {r}" for r in rules_here)
                item = {
                    "color":       "#6366F1",
                    "borderColor": border_clr,
                    "borderWidth": 3,
                }
                return {
                    "value":     val_str,
                    "itemStyle": item,
                    "tooltip":   {"formatter": f"{x_all[i]}<br/>Aktual: <b>{val_str}</b><br/>⚠ {rule_txt}"},
                    "name":      rule_txt,
                }
            return {"value": val_str, "itemStyle": {"color": "#6366F1"}}

        def _pt_f(i, v):
            abs_idx    = i + n_use
            rules_here = _rules_at(abs_idx)
            val_str    = round(float(v), 5)
            base_clr   = "#EF4444" if (v > usl_d or v < lsl_d) else "#F59E0B"
            if rules_here:
                border_clr = RC[rules_here[0]]
                rule_txt   = ", ".join(f"Rule {r}" for r in rules_here)
                item = {
                    "color":       base_clr,
                    "borderColor": border_clr,
                    "borderWidth": 3,
                }
                return {
                    "value":     val_str,
                    "itemStyle": item,
                    "tooltip":   {"formatter": f"{x_all[abs_idx]}<br/>Forecast: <b>{val_str}</b><br/>⚠ {rule_txt}"},
                    "name":      rule_txt,
                }
            return {"value": val_str, "itemStyle": {"color": base_clr}}

        pts_hist = [_pt_h(i, v) for i, v in enumerate(y_use)]
        pts_fc   = [_pt_f(i, v) for i, v in enumerate(y_fc)]

        # Tren sepanjang n_all
        x_arr  = np.arange(n_use)
        sv, iv = np.polyfit(x_arr, y_use, 1)
        trend_all = [round(float(sv*i+iv),5) for i in range(n_all)]

        all_v = y_use + y_fc + [ucl_v,lcl_v,usl_d,lsl_d,nom_d]
        y_pad = (max(all_v)-min(all_v))*0.1 or sigma_v*0.5 or 0.01
        y_min = round(min(all_v)-y_pad,5)
        y_max = round(max(all_v)+y_pad,5)

        mark_lines = [
            {"yAxis":ucl_v,"lineStyle":{"color":"#EF4444","width":1,"type":"dashed"},
             "label":{"formatter":f"UCL {ucl_v}","fontSize":9,"color":"#EF4444","position":"end"}},
            {"yAxis":lcl_v,"lineStyle":{"color":"#EF4444","width":1,"type":"dashed"},
             "label":{"formatter":f"LCL {lcl_v}","fontSize":9,"color":"#EF4444","position":"end"}},
            {"yAxis":usl_d,"lineStyle":{"color":"#EF4444","width":2,"type":"solid"},
             "label":{"formatter":f"USL {usl_d}","fontSize":10,"color":"#EF4444","position":"end"}},
            {"yAxis":lsl_d,"lineStyle":{"color":"#EF4444","width":2,"type":"solid"},
             "label":{"formatter":f"LSL {lsl_d}","fontSize":10,"color":"#EF4444","position":"end"}},
            {"yAxis":nom_d,"lineStyle":{"color":"#22C55E","width":1.5,"type":"dashed"},
             "label":{"formatter":f"Nom {nom_d}","fontSize":10,"color":"#22C55E","position":"end"}},
        ]

        st.markdown(
            f'<div style="font-size:13px;font-weight:700;color:#0F172A;margin:16px 0 4px;">'
            f'Tren Kendali + Prediksi — {row["Ref"]} · {row["Parameter"]} · No.{row["Sample"]}</div>',
            unsafe_allow_html=True
        )
        st.markdown("""
        <div style="display:flex;flex-wrap:wrap;gap:14px;font-size:11px;color:#64748B;margin-bottom:6px;">
          <span>&#8943; <span style="color:#EF4444;">dashed</span> UCL/LCL (3&sigma;)</span>
          <span>&#9632; <span style="color:#EF4444;">solid</span> USL/LSL</span>
          <span style="color:#6366F1;">&#9711;</span> Historis &nbsp;
          <span style="color:#F59E0B;">&#9711;</span> Forecast OK &nbsp;
          <span style="color:#EF4444;">&#9711;</span> Forecast NG &nbsp;|&nbsp;
          <span style="color:#EF4444;">&#9711;</span> R1 &nbsp;
          <span style="color:#F59E0B;">&#9711;</span> R2 &nbsp;
          <span style="color:#8B5CF6;">&#9711;</span> R3 &nbsp;
          <span style="color:#06B6D4;">&#9711;</span> R4 &nbsp;
          <span style="color:#10B981;">&#9711;</span> R5 &nbsp;
          <span style="color:#F97316;">&#9711;</span> R6 &nbsp;
          <span style="color:#3B82F6;">&#9711;</span> R7
        </div>
        """, unsafe_allow_html=True)

        # Bangun lookup rule per index untuk tooltip JS
        # Format: { index: "Rule 1, Rule 3" }
        rule_map_hist = {}
        rule_map_fc   = {}
        for r in range(1, 8):
            for idx in vbr_c[r]:
                if idx < n_use:
                    rule_map_hist.setdefault(idx, []).append(f"Rule {r}")
                else:
                    rule_map_fc.setdefault(idx - n_use, []).append(f"Rule {r}")

        # Inject rule label ke field "name" setiap titik agar bisa dibaca JS
        for i, pt in enumerate(pts_hist):
            if i in rule_map_hist:
                pt["name"] = " · ".join(rule_map_hist[i])
            else:
                pt["name"] = ""
        for i, pt in enumerate(pts_fc):
            if i in rule_map_fc:
                pt["name"] = " · ".join(rule_map_fc[i])
            else:
                pt["name"] = ""

        tooltip_js = JsCode("""
        function(params) {
            var lines = [];
            params.forEach(function(p) {
                if (p.value === null || p.value === undefined) return;
                var label = p.seriesName + ': <b>' + p.value + '</b>';
                if (p.name && p.name !== '' && (p.seriesName === 'Aktual' || p.seriesName === 'Forecast')) {
                    label += '<br/><span style="color:#EF4444;font-weight:700;">⚠ ' + p.name + '</span>';
                }
                lines.push(p.marker + ' ' + label);
            });
            return params[0].axisValueLabel + '<br/>' + lines.join('<br/>');
        }
        """)

        _chart_key = f"pr_chart_{abs(hash(str(row['Ref'])+str(row['Parameter'])+str(row['Sample'])))}"
        st_echarts({
            "title": {"text":f'Tren — {row["Ref"]} · {row["Parameter"]} · No.{row["Sample"]}',
                      "left":12,"top":8,
                      "textStyle":{"fontSize":13,"fontWeight":700,"color":"#0F172A"}},
            "grid":  {"top":50,"right":90,"bottom":58,"left":60},
            "tooltip":{"trigger":"axis","formatter": tooltip_js},
            "legend":{"data":["Aktual","Forecast","Tren"],"top":10,"right":16,
                      "icon":"circle","itemWidth":8,"textStyle":{"fontSize":10}},
            "xAxis": {
                "type":"category","data":x_all,
                "axisLabel":{"rotate":20,"fontSize":9,"interval":"auto"},
                "axisLine":{"lineStyle":{"color":"#E2E8F0"}},
                "axisTick":{"show":False},
            },
            "yAxis": {
                "type":"value","min":y_min,"max":y_max,"name":"Aktual",
                "axisLabel":{"fontSize":10},
                "splitLine":{"lineStyle":{"color":"#F1F5F9","type":"dashed"}},
            },
            "dataZoom": [
                {"type":"inside","start":0,"end":100},
                {"type":"slider","bottom":5,"height":18,
                 "borderColor":"transparent",
                 "fillerColor":"rgba(99,102,241,0.15)",
                 "handleStyle":{"color":"#6366F1"},
                 "textStyle":{"fontSize":9}},
            ],
            "series": [
                {"name":"Aktual","type":"line",
                 "data": pts_hist + [None]*n_fc_i,
                 "symbol":"circle","symbolSize":10,
                 "lineStyle":{"color":"#6366F1","width":1.5},
                 "markLine":{"symbol":["none","none"],"silent":True,"data":mark_lines},
                 "markArea":{
                     "silent":True,
                     "itemStyle":{"color":"rgba(249,115,22,0.04)"},
                     "data":[[{"xAxis":x_hist_lbl[-1] if x_hist_lbl else ""},{"xAxis":x_all[-1]}]],
                 }},
                {"name":"Forecast","type":"line",
                 "data": [None]*n_use + pts_fc,
                 "symbol":"circle","symbolSize":10,
                 "lineStyle":{"color":"#F59E0B","width":2,"type":"dashed"}},
                {"name":"Tren","type":"line",
                 "data": trend_all,
                 "symbol":"none",
                 "lineStyle":{"color":"#94A3B8","width":1.5,"type":"dotted"}},
            ],
        }, height="360px", key=_chart_key)

        # ── Kondisi Terdeteksi ────────────────────────────────────
        KONTEKS_PR = {
            1:"Titik berada di luar batas kendali — indikasi penyebab khusus yang perlu segera diinvestigasi.",
            2:"Proses mengalami pergeseran dari nilai rata-rata — kemungkinan ada perubahan material, mesin, atau operator.",
            3:"Tren naik atau turun secara konsisten — indikasi drift pada proses, misalnya keausan alat.",
            4:"Pola osilasi berlebihan — kemungkinan over-adjustment atau gangguan sistematis.",
            5:"Peringatan dini pergeseran proses — dua dari tiga titik mendekati batas kendali.",
            6:"Proses bergeser secara halus dari rata-rata — empat dari lima titik jauh dari pusat.",
            7:"Proses terlalu konsisten di dekat rata-rata — kemungkinan stratifikasi data.",
        }
        triggered_hist = [r for r in range(1,8) if any(i <  n_use for i in vbr_c[r])]
        triggered_fc   = [r for r in range(1,8) if any(i >= n_use for i in vbr_c[r])]
        triggered_all  = sorted(set(triggered_hist)|set(triggered_fc))

        if triggered_all:
            st.markdown('<div style="font-size:12px;font-weight:700;color:#0F172A;margin:12px 0 6px;">Kondisi Terdeteksi</div>',
                        unsafe_allow_html=True)
            for r_num in triggered_all:
                clr     = RC[r_num]
                sev     = RULES[r_num]["severity"]
                desc    = RULES[r_num]["desc"]
                konteks = KONTEKS_PR[r_num]
                is_crit = sev == "Critical"
                sev_bg  = "#FEE2E2" if is_crit else "#FEF3C7"
                sev_clr = "#991B1B" if is_crit else "#92400E"
                card_bg = "#FFF0F0" if is_crit else "#F5F7FF"
                n_hv = len([i for i in vbr_c[r_num] if i <  n_use])
                n_fv = len([i for i in vbr_c[r_num] if i >= n_use])
                zone = (
                    '<span style="background:#FEE2E2;color:#991B1B;font-size:9px;font-weight:700;padding:1px 6px;border-radius:4px;margin-left:6px;">Historis + Prediksi</span>'
                    if (n_hv and n_fv) else
                    '<span style="background:#FEF3C7;color:#92400E;font-size:9px;font-weight:700;padding:1px 6px;border-radius:4px;margin-left:6px;">Prediksi</span>'
                    if n_fv else
                    '<span style="background:#EFF6FF;color:#1D4ED8;font-size:9px;font-weight:700;padding:1px 6px;border-radius:4px;margin-left:6px;">Historis</span>'
                )
                st.markdown(
                    f'<div style="display:flex;align-items:flex-start;gap:12px;background:{card_bg};'
                    f'border:1.5px solid {clr}66;border-left:5px solid {clr};'
                    f'border-radius:10px;padding:12px 16px;margin-bottom:8px;'
                    f'box-shadow:0 2px 8px rgba(0,0,0,0.07);">'
                    f'<div style="min-width:64px;padding-top:1px;">'
                    f'<span style="background:{clr};color:#fff;border-radius:6px;'
                    f'padding:3px 10px;font-size:11px;font-weight:700;white-space:nowrap;">Rule {r_num}</span>'
                    f'</div><div style="flex:1;">'
                    f'<div style="font-size:12px;color:#0F172A;font-weight:600;margin-bottom:3px;">{desc}{zone}</div>'
                    f'<div style="font-size:11px;color:#475569;margin-bottom:6px;line-height:1.5;">{konteks}</div>'
                    f'<div style="display:flex;gap:8px;font-size:11px;color:#64748B;">'
                    f'<span>📍 {n_hv} historis · {n_fv} forecast</span>'
                    f'<span style="color:#CBD5E1;">|</span>'
                    f'<span style="background:{sev_bg};color:{sev_clr};'
                    f'border-radius:4px;padding:1px 8px;font-weight:700;font-size:10px;">{sev}</span>'
                    f'</div></div></div>',
                    unsafe_allow_html=True
                )

        # ── Keterangan — expander key statis (tidak bertambah) ────
        with st.expander("📋 Keterangan Kondisi Proses di Luar Kendali", expanded=False):
            RULE_META_PR = [
                (1,"#EF4444","Critical","Satu atau lebih titik data berada di luar batas kendali."),
                (2,"#F59E0B","Warning", "Delapan titik data berurutan berada di satu sisi nilai rata-rata."),
                (3,"#8B5CF6","Warning", "Tujuh titik data berturut-turut yang meningkat atau menurun."),
                (4,"#06B6D4","Warning", "Empat belas titik data berurutan yang bergantian naik dan turun."),
                (5,"#10B981","Warning", "Dua dari tiga titik berurutan berada di zona A atau di luarnya."),
                (6,"#F97316","Warning", "Empat dari lima titik berurutan berada di zona B atau lebih jauh."),
                (7,"#3B82F6","Warning", "Lima belas titik berurutan berada dalam zona C."),
            ]
            cols_pr = st.columns(2)
            for idx_pr,(r_num,clr,sev,desc) in enumerate(RULE_META_PR):
                is_crit = sev == "Critical"
                sev_bg  = "#FEE2E2" if is_crit else "#EFF6FF"
                sev_clr = "#991B1B" if is_crit else "#1D4ED8"
                card_bg = "#FFF0F0" if is_crit else "#F0F4FF"
                with cols_pr[idx_pr % 2]:
                    st.markdown(
                        f'<div style="background:{card_bg};border:1.5px solid {clr}88;'
                        f'border-left:5px solid {clr};border-radius:10px;'
                        f'padding:12px 14px;margin-bottom:4px;'
                        f'box-shadow:0 2px 8px rgba(0,0,0,0.08);">'
                        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">'
                        f'<span style="background:{clr};color:#fff;border-radius:6px;'
                        f'padding:2px 10px;font-size:11px;font-weight:700;">Rule {r_num}</span>'
                        f'<span style="background:{sev_bg};color:{sev_clr};border-radius:4px;'
                        f'padding:1px 8px;font-size:10px;font-weight:700;">{sev}</span>'
                        f'</div>'
                        f'<div style="font-size:12px;color:#1E293B;line-height:1.5;font-weight:500;">{desc}</div>'
                        f'</div>'
                        f'<div style="margin-bottom:10px;border-radius:6px;overflow:hidden;'
                        f'border:1px dashed {clr}66;background:#F8FAFC;'
                        f'height:80px;display:flex;align-items:center;justify-content:center;">' +
                        _get_rule_img_html(r_num, clr) +
                        '</div>',
                        unsafe_allow_html=True
                    )


    def _run_batch_arima(self, cache_path):
        import warnings
        warnings.filterwarnings("ignore")

        df = self.df_all
        param_col = "point" if "point" in df.columns else "Parameter"

        combos = (df[df["ref"]!="-"]
                  .groupby(["PartName","ModelName","SampleNo","ref",param_col])
                  .size().reset_index(name="n"))

        results = []
        progress = st.progress(0, text="Memproses batch forecast...")
        total = len(combos)

        for i, row in combos.iterrows():
            part, model, sno, ref, param = (
                row["PartName"], row["ModelName"],
                str(row["SampleNo"]), row["ref"], row[param_col]
            )
            df_sub = df[
                (df["PartName"]==part) & (df["ModelName"]==model) &
                (df["SampleNo"].astype(str)==sno) &
                (df["ref"].astype(str)==ref) &
                (df[param_col].astype(str)==param)
            ].sort_values(["Date","Shift","Cycle"]).dropna(subset=["Deviation"])

            progress.progress(min((i+1)/total, 1.0), text=f"{ref} · {param} ({i+1}/{total})")

            if len(df_sub) < 10:
                continue

            y    = df_sub["Deviation"].tolist()
            utol = float(df_sub["Uppertol"].iloc[0])
            ltol = float(df_sub["Lowertol"].iloc[0])
            res  = self._run_arima(y, 30)
            if "error" in res:
                continue

            fc = res["fc"]
            ng_shifts = [i+1 for i,v in enumerate(fc) if v > utol or v < ltol]
            trend_slope = round(float(np.polyfit(range(len(y)), y, 1)[0]), 6)
            trend_str = "naik" if trend_slope > 0 else "turun" if trend_slope < 0 else "stabil"

            results.append({
                "Part": part, "Model": model, "SampleNo": sno,
                "Ref": ref, "Point": param,
                "ARIMA_Order": str(res["order"]),
                "AIC": res["aic"],
                "Tren": trend_str,
                "Slope": trend_slope,
                "Prediksi_NG_Shift": ng_shifts[0] if ng_shifts else 0,
                "Status": "Berisiko" if ng_shifts else "Stabil",
            })

        progress.empty()
        if results:
            Path(cache_path).parent.mkdir(exist_ok=True)
            pd.DataFrame(results).to_csv(cache_path, index=False)
            st.success(f"✓ Batch selesai — {len(results)} kombinasi diproses")
        else:
            st.warning("Tidak ada kombinasi dengan data cukup.")

    @st.fragment
    def _render_spc(self):
        tab_pred, tab_hist = st.tabs(["Prediksi", "Riwayat Deteksi"])

        with tab_pred:
            st.markdown(
                '<div class="section-desc">Linear Trend · Scan otomatis semua titik · proyeksikan tren ke depan · deteksi rule sebelum terjadi.</div>',
                unsafe_allow_html=True
            )
            self._render_prediksi_rule()

        with tab_hist:
            st.markdown(
                '<div class="section-desc">Daftar semua titik yang pernah melanggar rule SPC pada data historis.</div>',
                unsafe_allow_html=True
            )
            # ── RIWAYAT ──────────────────────────────────────────────
            # ── Filter Baris 1: Part·Model | Kategori  (selectbox cascade) ──
            spc_combos = (
                self.df_all[["PartName","ModelName"]].dropna().drop_duplicates()
                .sort_values(["PartName","ModelName"])
            )
            spc_combo_opts = ["Semua Part & Model"] + [
                f"{r.PartName} · {r.ModelName}" for _, r in spc_combos.iterrows()
            ]
            if st.session_state.get("pred_combo") not in spc_combo_opts:
                st.session_state["pred_combo"] = "Semua Part & Model"

            cur_spc_combo = st.session_state.get("pred_combo", "Semua Part & Model")
            df_spc_combo  = self.df_all.copy()
            if cur_spc_combo != "Semua Part & Model":
                _sp = cur_spc_combo.split(" · ", 1)
                if len(_sp) == 2:
                    df_spc_combo = self.df_all[(self.df_all["PartName"]==_sp[0])&(self.df_all["ModelName"]==_sp[1])]

            cat_spc_vals = sorted(df_spc_combo["Category"].dropna().unique().tolist()) if "Category" in df_spc_combo.columns else []
            cat_spc_opts = ["Semua Kategori"] + cat_spc_vals
            if st.session_state.get("pred_cat") not in cat_spc_opts:
                st.session_state["pred_cat"] = "Produksi" if "Produksi" in cat_spc_opts else "Semua Kategori"

            spc_r1c1, spc_r1c2 = st.columns([2.5, 1.5], gap="small")
            with spc_r1c1:
                f_spc_combo = st.selectbox("Part · Model", spc_combo_opts, key="pred_combo")
            with spc_r1c2:
                f_cat = st.selectbox("Kategori", cat_spc_opts, key="pred_cat")

            # Baris 2: KP | Ref/Point | Parameter (cascade dari combo+cat)
            cur_spc_cat  = st.session_state.get("pred_cat", "Semua Kategori")
            df_spc_cat   = df_spc_combo[df_spc_combo["Category"]==cur_spc_cat] if cur_spc_cat != "Semua Kategori" and "Category" in df_spc_combo.columns else df_spc_combo

            _ref_col_spc   = "ref"   if "ref"   in df_spc_cat.columns else "PartName"
            _param_col_spc = "point" if "point" in df_spc_cat.columns else "Parameter"

            ref_spc_vals = sorted([r for r in df_spc_cat[_ref_col_spc].dropna().astype(str).unique() if r not in ("","-","nan")])
            ref_spc_opts = ["Semua Ref / Point"] + ref_spc_vals
            if st.session_state.get("pred_ref") not in ref_spc_opts:
                st.session_state["pred_ref"] = "Semua Ref / Point"

            cur_spc_ref  = st.session_state.get("pred_ref", "Semua Ref / Point")
            df_spc_ref   = df_spc_cat[df_spc_cat[_ref_col_spc].astype(str)==cur_spc_ref] if cur_spc_ref != "Semua Ref / Point" else df_spc_cat

            param_spc_vals = sorted([p for p in df_spc_ref[_param_col_spc].dropna().astype(str).unique() if p not in ("","-","nan")])
            param_spc_opts = ["Semua Parameter"] + param_spc_vals
            if st.session_state.get("pred_param") not in param_spc_opts:
                st.session_state["pred_param"] = "Semua Parameter"

            kp_spc_opts = ["Semua Titik", "KP saja"]
            if st.session_state.get("pred_kp") not in kp_spc_opts:
                st.session_state["pred_kp"] = "Semua Titik"

            spc_r2c1, spc_r2c2, spc_r2c3 = st.columns([1.2, 1.5, 2.5], gap="small")
            with spc_r2c1:
                f_kp_spc = st.selectbox("Kritikal Point", kp_spc_opts, key="pred_kp")
            with spc_r2c2:
                f_ref_spc = st.selectbox("Ref / Point", ref_spc_opts, key="pred_ref")
            with spc_r2c3:
                f_param_spc = st.selectbox("Parameter", param_spc_opts, key="pred_param")

            # ── Filter Baris 3: Rule (tetap pills) ──
            st.markdown('<div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:4px;">Filter Rule SPC</div>', unsafe_allow_html=True)
            rule_opts = ["Semua Rule"] + [f"Rule {i}" for i in range(1,8)]
            f_rule = st.pills(
                "Rule", rule_opts, default="Semua Rule",
                key="pred_rule", label_visibility="collapsed",
                selection_mode="single",
            ) or "Semua Rule"

            # Pecah combo → part & model
            f_part, f_model = "Semua Part", "Semua Model"
            if f_spc_combo != "Semua Part & Model":
                _sp = f_spc_combo.split(" · ", 1)
                if len(_sp) == 2:
                    f_part, f_model = _sp[0], _sp[1]

            # ── Session state cache untuk deteksi kendali ─────────────────────
            import time as _time
            nelson_key = f"kendali_{f_part}_{f_model}_{f_cat}"
            ts_key     = f"{nelson_key}_ts"
            TTL        = 300
            if nelson_key not in st.session_state or \
               _time.time() - st.session_state.get(ts_key, 0) > TTL:
                df_src = self.df_all.copy()
                if f_part != "Semua Part":
                    df_src = df_src[df_src["PartName"] == f_part]
                if f_model != "Semua Model":
                    df_src = df_src[df_src["ModelName"] == f_model]
                if f_cat != "Semua Kategori" and "Category" in df_src.columns:
                    df_src = df_src[df_src["Category"] == f_cat]
                if f_kp_spc == "KP saja" and "KP" in df_src.columns:
                    df_src = df_src[df_src["KP"].astype(str).isin(["1","1.0","True"])]
                if f_ref_spc != "Semua Ref / Point" and _ref_col_spc in df_src.columns:
                    df_src = df_src[df_src[_ref_col_spc].astype(str) == f_ref_spc]
                if f_param_spc != "Semua Parameter" and _param_col_spc in df_src.columns:
                    df_src = df_src[df_src[_param_col_spc].astype(str) == f_param_spc]
                with st.spinner("Mendeteksi kondisi proses di luar kendali..."):
                    st.session_state[nelson_key] = _build_kendali_history(df_src)
                    st.session_state[ts_key]     = _time.time()

            df_hist = st.session_state[nelson_key]

            if df_hist.empty:
                st.success("Tidak ada kondisi proses di luar kendali yang terdeteksi.")
                return

            if f_rule != "Semua Rule":
                r_num = int(f_rule.split(" ")[1])
                df_hist = df_hist[df_hist["Rule"] == r_num]
            if df_hist.empty:
                st.info("Tidak ada violation untuk filter yang dipilih.")
                return

            # ── KPI summary ───────────────────────────────────────────
            n_total    = len(df_hist)
            n_critical = int((df_hist["Severity"] == "Critical").sum())
            n_warning  = int((df_hist["Severity"] == "Warning").sum())
            n_titik    = df_hist[["Part","Model","Ref","Parameter"]].drop_duplicates().shape[0]

            st.markdown(
                f'<div style="display:grid;grid-template-columns:repeat(4,1fr);'
                f'gap:10px;margin:12px 0 16px;">'
                + "".join([
                    f'<div style="background:{bg};border-radius:8px;padding:12px 16px;text-align:center;">'
                    f'<div style="font-size:22px;font-weight:700;color:{fc};">{val}</div>'
                    f'<div style="font-size:10px;color:#64748B;text-transform:uppercase;'
                    f'letter-spacing:.5px;margin-top:3px;">{lbl}</div></div>'
                    for bg, fc, val, lbl in [
                        ("#F8FAFC", "#0F172A", n_total,    "Total Violations"),
                        ("#FEF2F2", "#DC2626", n_critical, "Critical"),
                        ("#FFFBEB", "#D97706", n_warning,  "Warning"),
                        ("#F0F9FF", "#0369A1", n_titik,    "Titik Ukur Terdampak"),
                    ]
                ])
                + '</div>',
                unsafe_allow_html=True
            )

            # ── Chart: violations per rule ────────────────────────────
            c_left, c_right = st.columns([1.5, 2], gap="small")
            with c_left:
                rule_counts = df_hist.groupby(["Rule","Rule Label","Severity"]).size().reset_index(name="count")
                rule_counts = rule_counts.sort_values("Rule")
                st_echarts({
                    "title": {"text": "Violations per Rule",
                              "textStyle": {"fontSize": 13, "fontWeight": 700}},
                    "tooltip": {"trigger": "axis"},
                    "grid": {"top": 36, "bottom": 8, "left": 8, "right": 40,
                             "containLabel": True},
                    "xAxis": {"type": "value"},
                    "yAxis": {"type": "category",
                              "data": rule_counts["Rule Label"].tolist(),
                              "axisLabel": {"fontSize": 10}},
                    "series": [{
                        "data": rule_counts["count"].tolist(),
                        "type": "bar",
                        "itemStyle": {
                            "color": {"type": "linear", "x": 0, "y": 0, "x2": 1, "y2": 0,
                                      "colorStops": [{"offset": 0, "color": "#6366F1"},
                                                     {"offset": 1, "color": "#A78BFA"}]},
                            "borderRadius": [0, 4, 4, 0]
                        },
                        "label": {"show": True, "position": "right", "fontSize": 10}
                    }],
                }, height="260px", key="pred_rule_bar")

            with c_right:
                # Semua titik dengan violations, per SampleNo
                grp_cols = ["Ref","Parameter","SampleNo"] if "SampleNo" in df_hist.columns else ["Ref","Parameter"]
                top_titik = (df_hist.groupby(grp_cols)["n Titik"]
                             .sum().sort_values(ascending=False))
                if "SampleNo" in df_hist.columns:
                    labels = [f"{r} · {p} (No.{s})" for r, p, s in top_titik.index]
                else:
                    labels = [f"{r} · {p}" for r, p in top_titik.index]
                n_items  = len(labels)
                st_echarts({
                    "title": {"text": "Titik — Total Violations",
                              "textStyle": {"fontSize": 13, "fontWeight": 700}},
                    "tooltip": {"trigger": "axis"},
                    "grid": {"top": 36, "bottom": 8, "left": 8, "right": 60,
                             "containLabel": True},
                    "xAxis": {"type": "value"},
                    "yAxis": {"type": "category",
                              "data": list(reversed(labels)),
                              "axisLabel": {"fontSize": 9}},
                    "dataZoom": [{"type": "slider", "yAxisIndex": 0,
                                  "start": max(0, 100 - round(15/max(n_items,1)*100)) if n_items > 15 else 0,
                                  "end": 100,
                                  "width": 15, "right": 5,
                                  "borderColor": "transparent",
                                  "fillerColor": "rgba(99,102,241,0.15)",
                                  "handleStyle": {"color": "#6366F1"}}],
                    "series": [{
                        "data": list(reversed(top_titik.values.tolist())),
                        "type": "bar",
                        "itemStyle": {"color": "#F59E0B", "borderRadius": [0,4,4,0]},
                        "label": {"show": True, "position": "right", "fontSize": 10}
                    }],
                }, height="260px", key="pred_top_titik")
            # ── Deskripsi kondisi proses di luar kendali ─────────────
            with st.expander("📋 Keterangan Kondisi Proses di Luar Kendali", expanded=False):
                RULE_META = [
                    (1, "#EF4444", "Critical", "Satu atau lebih titik data berada di luar batas kendali."),
                    (2, "#F59E0B", "Warning",  "Delapan titik data berurutan berada di satu sisi nilai rata-rata."),
                    (3, "#8B5CF6", "Warning",  "Tujuh titik data berturut-turut yang meningkat atau menurun."),
                    (4, "#06B6D4", "Warning",  "Empat belas titik data berurutan yang bergantian naik dan turun."),
                    (5, "#10B981", "Warning",  "Dua titik data, dari tiga titik data berurutan, berada di sisi yang sama dari rata-rata di zona A atau di luarnya."),
                    (6, "#10B981", "Warning",  "Empat titik data, dari lima titik data berurutan, berada di sisi yang sama dari rata-rata di zona B atau lebih jauh."),
                    (7, "#3B82F6", "Warning",  "Lima belas titik data berurutan berada dalam zona C (di atas dan di bawah rata-rata)."),
                ]
                cols = st.columns(2)
                for idx, (r_num, clr, sev, desc) in enumerate(RULE_META):
                    is_crit = sev == "Critical"
                    sev_bg  = "#FEE2E2" if is_crit else "#EFF6FF"
                    sev_clr = "#991B1B" if is_crit else "#1D4ED8"
                    card_bg = "#FFF0F0" if is_crit else "#F0F4FF"
                    with cols[idx % 2]:
                        st.markdown(
                            f'<div style="background:{card_bg};border:1.5px solid {clr}88;'
                            f'border-left:5px solid {clr};border-radius:10px;'
                            f'padding:12px 14px;margin-bottom:10px;'
                            f'box-shadow:0 2px 8px rgba(0,0,0,0.08);">'
                            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">'
                            f'<span style="background:{clr};color:#fff;border-radius:6px;'
                            f'padding:2px 10px;font-size:11px;font-weight:700;">Rule {r_num}</span>'
                            f'<span style="background:{sev_bg};color:{sev_clr};border-radius:4px;'
                            f'padding:1px 8px;font-size:10px;font-weight:700;">{sev}</span>'
                            f'</div>'
                            f'<div style="font-size:12px;color:#1E293B;line-height:1.5;font-weight:500;">{desc}</div>'
                            f'<div style="margin-top:8px;border-radius:6px;overflow:hidden;'
                            f'border:1px dashed {clr}66;background:#F8FAFC;'
                            f'height:80px;display:flex;align-items:center;justify-content:center;">' +
                            _get_rule_img_html(r_num, clr) +
                            f'</div>'
                            f'</div>',
                            unsafe_allow_html=True
                        )

            # ── Tabel history lengkap ─────────────────────────────────
            st.markdown(
                '<div style="font-size:14px;font-weight:700;color:#0F172A;'
                'margin:16px 0 8px;">History Deteksi Proses di Luar Kendali</div>',
                unsafe_allow_html=True
            )

            # Filter severity
            sev_filter = st.pills(
                "Severity", ["Semua","Critical","Warning"],
                default="Semua", key="pred_sev",
                label_visibility="collapsed", selection_mode="single"
            ) or "Semua"
            if sev_filter != "Semua":
                df_show = df_hist[df_hist["Severity"] == sev_filter].copy()
            else:
                df_show = df_hist.copy()

            RULE_CLR = {
                "Critical": "background-color:#FEF2F2;color:#991B1B;font-weight:700;",
                "Warning":  "background-color:#FFFBEB;color:#92400E;font-weight:700;",
            }
            RULE_LABEL_CLR = {
                "Rule 1": "#EF4444", "Rule 2": "#F59E0B", "Rule 3": "#8B5CF6",
                "Rule 4": "#06B6D4", "Rule 5": "#10B981", "Rule 6": "#F97316",
                "Rule 7": "#3B82F6",
            }

            def color_sev(row):
                styles = [""] * len(row)
                idx = list(row.index)
                si  = idx.index("Severity")
                ri  = idx.index("Rule Label")
                styles[si] = RULE_CLR.get(row["Severity"], "")
                styles[ri] = f"color:{RULE_LABEL_CLR.get(row['Rule Label'], '#64748B')};font-weight:700;"
                return styles

            cols_show = [c for c in ["Part","Model","Category","Ref","Parameter","SampleNo",
                         "Rule Label","Deskripsi","Severity","n Titik","Terakhir"]
                         if c in df_show.columns]

            st.markdown(
                '<div style="font-size:11px;color:#64748B;margin-bottom:6px;">'
                'Klik baris untuk melihat grafik tren</div>',
                unsafe_allow_html=True
            )

            sel = st.dataframe(
                df_show[cols_show].style.apply(color_sev, axis=1),
                use_container_width=True,
                hide_index=True,
                height=min(520, 42 + len(df_show) * 36),
                on_select="rerun",
                selection_mode="single-row",
                key="pred_kendali_table",
            )

            # ── Chart tren untuk baris yang dipilih ────────────
            sel_rows = sel.selection.rows if sel and hasattr(sel, "selection") else []
            if sel_rows:
                row     = df_show[cols_show].iloc[sel_rows[0]]
                s_ref   = str(row["Ref"])
                s_param = str(row["Parameter"])
                s_part  = str(row["Part"])
                s_model = str(row["Model"])
                s_sno   = str(row["SampleNo"]) if "SampleNo" in row.index else None

                param_col = "point" if "point" in self.df_all.columns else "Parameter"
                df_t = self.df_all[
                    (self.df_all["PartName"]  == s_part) &
                    (self.df_all["ModelName"] == s_model) &
                    (self.df_all["ref"].astype(str).str.strip().str.upper() == s_ref.upper()) &
                    (self.df_all[param_col].astype(str) == s_param)
                ].copy()
                if s_sno and "SampleNo" in df_t.columns:
                    df_t = df_t[df_t["SampleNo"].astype(str) == s_sno]

                df_t = df_t.sort_values(["Date","Shift","Cycle"]).dropna(subset=["Actual","Date"])

                if len(df_t) >= 2:
                    st.markdown(
                        f'<div style="font-size:13px;font-weight:700;color:#0F172A;margin:16px 0 6px;">'
                        f'Tren Kendali — {s_ref} · {s_param}'
                        + (f' · No.{s_sno}' if s_sno else '') + '</div>',
                        unsafe_allow_html=True
                    )
                    y_vals   = df_t["Actual"].tolist()
                    x_labels = df_t.apply(
                        lambda r: f"{r['Date'].strftime('%d %b')} S{r['Shift']}", axis=1
                    ).tolist()
                    mean_v  = float(np.mean(y_vals))
                    sigma_v = float(np.std(y_vals, ddof=1)) if len(y_vals) > 1 else 0.0
                    ucl_v   = round(mean_v + 3*sigma_v, 5)
                    lcl_v   = round(mean_v - 3*sigma_v, 5)

                    # USL/LSL dari data — coba kolom langsung, fallback ke Nominal+Tol
                    nom_v = float(df_t["Nominal"].dropna().iloc[0]) if "Nominal" in df_t.columns and df_t["Nominal"].notna().any() else None
                    if "USL" in df_t.columns and df_t["USL"].notna().any():
                        usl_v = float(df_t["USL"].dropna().iloc[0])
                    elif nom_v is not None and "Uppertol" in df_t.columns and df_t["Uppertol"].notna().any():
                        usl_v = round(nom_v + float(df_t["Uppertol"].dropna().iloc[0]), 5)
                    else:
                        usl_v = None
                    if "LSL" in df_t.columns and df_t["LSL"].notna().any():
                        lsl_v = float(df_t["LSL"].dropna().iloc[0])
                    elif nom_v is not None and "Lowertol" in df_t.columns and df_t["Lowertol"].notna().any():
                        lsl_v = round(nom_v + float(df_t["Lowertol"].dropna().iloc[0]), 5)
                    else:
                        lsl_v = None

                    # Deteksi violations — persis seperti descriptive
                    vbr = _detect_kendali(y_vals)
                    RC  = {1:"#EF4444",2:"#F59E0B",3:"#8B5CF6",
                           4:"#06B6D4",5:"#10B981",6:"#F97316",7:"#3B82F6"}

                    def pt_style(i):
                        for r in [1,2,3,4,5,6,7]:
                            if i in vbr[r]:
                                return {"color":"#6366F1","borderColor":RC[r],"borderWidth":2.5}
                        return {"color":"#6366F1"}

                    series_data = [{"value": v, "itemStyle": pt_style(i)}
                                   for i, v in enumerate(y_vals)]

                    # Legend warna
                    st.markdown("""
                    <div style="display:flex;flex-wrap:wrap;gap:14px;font-size:11px;
                                color:#64748B;margin-bottom:6px;">
                      <span>&#8943; <span style="color:#EF4444;">dashed</span> UCL/LCL (3&sigma;)</span>
                      <span style="color:#EF4444;">&#9711;</span> Rule 1 &nbsp;
                      <span style="color:#F59E0B;">&#9711;</span> Rule 2 &nbsp;
                      <span style="color:#8B5CF6;">&#9711;</span> Rule 3 &nbsp;
                      <span style="color:#06B6D4;">&#9711;</span> Rule 4 &nbsp;
                      <span style="color:#10B981;">&#9711;</span> Rule 5 &nbsp;
                      <span style="color:#F97316;">&#9711;</span> Rule 6 &nbsp;
                      <span style="color:#3B82F6;">&#9711;</span> Rule 7
                    </div>
                    """, unsafe_allow_html=True)

                    mark_lines = [
                        {"yAxis": ucl_v, "lineStyle": {"color":"#EF4444","width":1,"type":"dashed"},
                         "label": {"formatter":f"UCL {ucl_v}","fontSize":9,"color":"#EF4444"}},
                        {"yAxis": lcl_v, "lineStyle": {"color":"#EF4444","width":1,"type":"dashed"},
                         "label": {"formatter":f"LCL {lcl_v}","fontSize":9,"color":"#EF4444"}},
                    ]
                    if usl_v: mark_lines += [
                        {"yAxis": usl_v, "lineStyle": {"color":"#EF4444","width":2,"type":"solid"},
                         "label": {"formatter":f"USL {usl_v}","fontSize":10,"color":"#EF4444"}},
                    ]
                    if lsl_v: mark_lines += [
                        {"yAxis": lsl_v, "lineStyle": {"color":"#EF4444","width":2,"type":"solid"},
                         "label": {"formatter":f"LSL {lsl_v}","fontSize":10,"color":"#EF4444"}},
                    ]
                    if nom_v: mark_lines += [
                        {"yAxis": nom_v, "lineStyle": {"color":"#22C55E","width":1.5,"type":"dashed"},
                         "label": {"formatter":f"Nom {nom_v}","fontSize":10,"color":"#22C55E"}},
                    ]

                    # Hitung y_min / y_max agar semua garis referensi terlihat
                    all_ref = [ucl_v, lcl_v] + \
                              ([usl_v] if usl_v else []) + \
                              ([lsl_v] if lsl_v else []) + \
                              ([nom_v] if nom_v else [])
                    all_y   = y_vals + all_ref
                    y_pad   = (max(all_y) - min(all_y)) * 0.1 or sigma_v * 0.5 or 0.01
                    y_min_v = round(min(all_y) - y_pad, 5)
                    y_max_v = round(max(all_y) + y_pad, 5)

                    st_echarts({
                        "title": {"text": f"Tren — {s_ref} · {s_param}" + (f" · No.{s_sno}" if s_sno else ""),
                                  "left": 12, "top": 8,
                                  "textStyle": {"fontSize":13,"fontWeight":700,"color":"#0F172A"}},
                        "grid": {"top":50,"right":80,"bottom":55,"left":60},
                        "tooltip": {"trigger":"axis","formatter":"{b}<br/>Aktual: <b>{c}</b>"},
                        "xAxis": {"type":"category","data":x_labels,
                                  "axisLabel":{"rotate":20,"fontSize":9,"interval":"auto"}},
                        "yAxis": {"type":"value","min":y_min_v,"max":y_max_v,"name":"Aktual",
                                  "axisLabel":{"fontSize":10}},
                        "dataZoom": [{"type":"inside","start":0,"end":100},
                                     {"type":"slider","bottom":8,"height":16}],
                        "series": [{
                            "data": series_data, "type": "line",
                            "symbol": "circle", "symbolSize": 8,
                            "lineStyle": {"color":"#6366F1","width":1.5},
                            "markLine": {"symbol":["none","none"],"silent":True,
                                         "data": mark_lines},
                        }],
                    }, height="340px", key=f"pred_trend_{s_ref}_{s_param}_{s_sno}")

                    # Penjelasan per rule yang terdeteksi
                    KONTEKS = {
                        1: "Titik berada di luar batas kendali — indikasi penyebab khusus (special cause) yang perlu segera diinvestigasi.",
                        2: "Proses mengalami pergeseran (shift) dari nilai rata-rata — kemungkinan ada perubahan pada material, mesin, atau operator.",
                        3: "Tren naik atau turun secara konsisten — indikasi adanya drift pada proses, misalnya keausan alat atau perubahan suhu bertahap.",
                        4: "Pola osilasi berlebihan — kemungkinan over-adjustment atau gangguan sistematis pada proses pengukuran.",
                        5: "Peringatan dini pergeseran proses — dua dari tiga titik mendekati batas kendali di sisi yang sama.",
                        6: "Proses bergeser secara halus dari rata-rata — empat dari lima titik berada jauh dari pusat di sisi yang sama.",
                        7: "Proses terlalu konsisten di dekat rata-rata — bisa mengindikasikan stratifikasi data atau masalah pada sistem pengukuran.",
                    }
                    triggered = [r for r in range(1,8) if vbr[r]]
                    if triggered:
                        st.markdown(
                            '<div style="font-size:12px;font-weight:700;color:#0F172A;'
                            'margin:12px 0 6px;">Kondisi Terdeteksi</div>',
                            unsafe_allow_html=True
                        )
                        for r_num in triggered:
                            clr     = RC[r_num]
                            sev     = RULES[r_num]["severity"]
                            desc    = RULES[r_num]["desc"]
                            konteks = KONTEKS[r_num]
                            is_crit = sev == "Critical"
                            sev_bg  = "#FEE2E2" if is_crit else "#FEF3C7"
                            sev_clr = "#991B1B" if is_crit else "#92400E"
                            card_bg = "#FFF0F0" if is_crit else "#F5F7FF"
                            st.markdown(
                                f'<div style="display:flex;align-items:flex-start;gap:12px;'
                                f'background:{card_bg};border:1.5px solid {clr}66;border-left:5px solid {clr};'
                                f'border-radius:10px;padding:12px 16px;margin-bottom:8px;'
                                f'box-shadow:0 2px 8px rgba(0,0,0,0.07);">'
                                f'<div style="min-width:64px;padding-top:1px;">'
                                f'<span style="background:{clr};color:#fff;'
                                f'border-radius:6px;padding:3px 10px;font-size:11px;font-weight:700;'
                                f'white-space:nowrap;">Rule {r_num}</span></div>'
                                f'<div style="flex:1;">'
                                f'<div style="font-size:12px;color:#0F172A;font-weight:600;margin-bottom:3px;">'
                                f'{desc}</div>'
                                f'<div style="font-size:11px;color:#475569;margin-bottom:6px;line-height:1.5;">'
                                f'{konteks}</div>'
                                f'<div style="display:flex;align-items:center;gap:8px;font-size:11px;color:#64748B;">'
                                f'<span>📍 {len(vbr[r_num])} titik terdampak</span>'
                                f'<span style="color:#CBD5E1;">|</span>'
                                f'<span style="background:{sev_bg};color:{sev_clr};'
                                f'border-radius:4px;padding:1px 8px;font-weight:700;font-size:10px;">'
                                f'{sev}</span>'
                                f'</div></div></div>',
                                unsafe_allow_html=True
                            )
                else:
                    st.info("Data tidak cukup untuk menampilkan tren.")