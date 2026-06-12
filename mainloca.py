"""
mainloca.py — Entry point CMM Quality Dashboard (PT Astra Honda Motor).
═══════════════════════════════════════════════════════════════════════
Berisi shell aplikasi:
  • Konfigurasi halaman + CSS global (apply_custom_css)
  • Halaman login (render_login) dengan kredensial & role di USERS
  • Sidebar navigasi (render_sidebar) memakai PAGE_LABELS untuk tampilan
  • Routing ke 8 halaman di folder pages_app/ (lihat page_map di run())
  • Warmup model XGBoost + rule SPC sekali per sesi (di-cache 30 menit)

Jalankan dengan:  streamlit run mainloca.py
"""
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_option_menu import option_menu
import pandas as pd
import os
import base64
from datetime import datetime, timedelta
from pathlib import Path as _PPath

# ── Logo AHM sebagai base64 (dipakai di login, sidebar, report) ──
def _ahm_logo_b64() -> str:
    p = _PPath("assets/Logo_AHM.svg")
    if p.exists():
        return "data:image/svg+xml;base64," + base64.b64encode(p.read_bytes()).decode()
    return ""

# Import class halaman dari folder pages_app
from pages_app.dashboard import DashboardPage
from pages_app.descriptive import DescriptivePage
from pages_app.diagnostic import DiagnosticPage
from pages_app.predictive import PredictivePage
from pages_app.prescriptive import PrescriptivePage
from pages_app.messages import MessagePage
from pages_app.report import ReportPage
from pages_app.settings import SettingsPage
from local_db import get_unread_count, init_db
from floating_chatbot import render_floating_chatbot



# ─────────────────────────────────────────────────────────────────
#  USER CREDENTIALS & ROLES
# ─────────────────────────────────────────────────────────────────
USERS = {
    "admin":       {"password": "admin",       "role": "Admin"},
    "cmm": {"password": "cmm", "role": "Measurement"},
    "produksi":    {"password": "produksi",    "role": "Produksi"},
}

# Pages accessible per role
ALL_PAGES = [
    "Dashboard", "Descriptive", "Diagnostic", "Predictive",
    "Prescriptive", "Messages", "Report", "Settings",
]

ROLE_PAGES = {
    "Admin":       ALL_PAGES,
    "Measurement": ALL_PAGES,
    "Produksi":    ALL_PAGES,
}

PAGE_ICONS = {
    "Dashboard":    "house",
    "Descriptive":  "bar-chart",
    "Diagnostic":   "activity",
    "Predictive":   "graph-up",
    "Prescriptive": "lightbulb",
    "Messages":     "envelope",
    "Report":       "file-text",
    "Settings":     "gear",
}

# Label tampilan sidebar (Indonesia) — key tetap dipakai untuk routing.
# Istilah teknis analytics (Descriptive/Diagnostic/Predictive/Prescriptive) dipertahankan.
PAGE_LABELS = {
    "Dashboard":    "Dashboard",
    "Descriptive":  "Descriptive",
    "Diagnostic":   "Diagnostic",
    "Predictive":   "Predictive",
    "Prescriptive": "Prescriptive",
    "Messages":     "Pesan",
    "Report":       "Laporan",
    "Settings":     "Pengaturan",
}

# ─────────────────────────────────────────────────────────────────
#  CSV DATA LOADING
# ─────────────────────────────────────────────────────────────────
def _db_mtime() -> float:
    """Ambil mtime file DB. Return 0 kalau tidak ada."""
    try:
        return os.path.getmtime(os.path.join("data", "cmm.db"))
    except Exception:
        return 0.0


@st.cache_data(ttl=300)
def load_data() -> pd.DataFrame:
    """Baca data pengukuran dari SQLite (tabel measurements)."""
    from local_db import load_measurements
    try:
        return load_measurements()
    except Exception as e:
        st.error(f"Terjadi kesalahan saat membaca data: {e}")
        return pd.DataFrame()

# ─────────────────────────────────────────────────────────────────
#  APP CLASS
# ─────────────────────────────────────────────────────────────────
class QualityDashboardApp:
    def __init__(self):
        st.set_page_config(page_title="CMM Quality Dashboard", layout="wide", initial_sidebar_state="expanded")
        self.apply_custom_css()

    # ── CSS ──────────────────────────────────────────────────────
    def apply_custom_css(self):
        st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;0,800&display=swap');
        html, body, [class*="css"], p, div, span, h1, h2, h3, h4, h5, h6 { font-family: 'Inter', sans-serif; }
        #MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stHeader"] { display: none !important; height: 0 !important; min-height: 0 !important; padding: 0 !important; margin: 0 !important; }
        [data-testid="stSidebarCollapseButton"], [data-testid="collapsedControl"], [data-testid="stSidebarHeader"] { display: none !important; padding: 0 !important; margin: 0 !important; }
        button[title="View fullscreen"] { display: none !important; }
        [data-testid="stAppViewContainer"] { background: #F1F4F9 !important; }
        [data-testid="stSidebar"] { background: #FFFFFF !important; width: 240px !important; min-width: 240px !important; max-width: 240px !important; border-right: 1px solid #E8ECF2 !important; }
        [data-testid="stSidebar"] > div:first-child { padding-top: 0 !important; overflow-x: hidden; }
        iframe[title="streamlit_option_menu.option_menu"] { background-color: #FFFFFF !important; border: none !important; outline: none !important; }
        div.block-container { padding-top: 1.5rem !important; padding-bottom: 0rem !important; padding-left: 2rem !important; padding-right: 2rem !important; max-width: 100% !important; }
        .page-hdr { display: flex; align-items: center; gap: 10px; margin-top: 0 !important; margin-bottom: 8px; }
        .page-title { font-size: 18px; font-weight: 800; color: #0F172A; letter-spacing: -0.5px; }
        .page-sub { font-size: 12.5px; color: #475569; font-weight: 500; margin-left: 8px; }
        .section-desc { font-size: 12px; color: #64748B; font-weight: 500; margin: 2px 0 12px 0; line-height: 1.5; }
        .prediksi-badge { background: #DC2626; color: #fff; border-radius: 4px; padding: 2px 8px; font-size: 10.5px; font-weight: 600; letter-spacing: 0.1px; }
        [data-testid="stSelectbox"] > div > div { background: #fff !important; border: 1px solid #DDE1EA !important; border-radius: 6px !important; font-size: 12px !important; color: #374151 !important; box-shadow: 0 1px 2px rgba(0,0,0,.04) !important; min-height: 32px !important; }
        div[data-baseweb="select"] > div { border: none !important; box-shadow: none !important; }
        .kpi-card { background: #fff; border-radius: 10px; border: 1px solid #E8ECF2; box-shadow: 0 2px 4px rgba(15,23,42,.03); padding: 12px 16px; display: flex; align-items: center; gap: 12px; min-height: 65px; }
        .kpi-icon { width: 38px; height: 38px; border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
        .kpi-icon svg { width: 18px; height: 18px; }
        .kpi-blue  { background: #EFF6FF; }
        .kpi-green { background: #F0FDF4; }
        .kpi-red   { background: #FEF2F2; }
        .kpi-val { font-size: 20px; font-weight: 800; color: #0F172A; line-height: 1; letter-spacing: -0.5px; }
        .kpi-val-green { color: #15803D; }
        .kpi-val-red   { color: #B91C1C; }
        .kpi-lbl { font-size: 11.5px; font-weight: 600; color: #475569; margin-top: 2px; }
        .kpi-sub { font-size: 10.5px; color: #64748B; margin-top: 1px; }
        iframe[title*="echarts"] { background-color: #ffffff !important; border-radius: 10px !important; border: 1px solid #E8ECF2 !important; box-shadow: 0 2px 4px rgba(15,23,42,.03) !important; overflow: hidden !important; display: block; }
        .row-gap { margin-bottom: 8px; }

        /* ── Widget native Streamlit — selaras palet, tidak lebur dgn background ── */
        /* Tabs */
        button[data-baseweb="tab"] { font-size: 13px !important; font-weight: 600 !important; color: #64748B !important; }
        button[data-baseweb="tab"][aria-selected="true"] { color: #DC2626 !important; }
        div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"] { background-color: #DC2626 !important; }

        /* Expander — kartu putih dengan border, tidak menyatu dgn latar */
        div[data-testid="stExpander"] { background: #FFFFFF !important; border: 1px solid #E2E8F0 !important; border-radius: 10px !important; margin-bottom: 10px !important; box-shadow: 0 1px 2px rgba(15,23,42,.04) !important; }
        div[data-testid="stExpander"] summary { background: #FFFFFF !important; border-radius: 10px !important; padding: 6px 10px !important; position: static !important; }
        div[data-testid="stExpander"] details > div { background: #FFFFFF !important; padding: 6px 14px 14px !important; }
        details summary { position: static !important; }

        /* Dataframe — beri border supaya area tabel jelas batasnya */
        div[data-testid="stDataFrame"] { border: 1px solid #E2E8F0 !important; border-radius: 10px !important; overflow: hidden !important; }

        /* Selectbox & input — putih bersih, kontras dgn latar */
        div[data-baseweb="select"] > div { background: #FFFFFF !important; border: 1px solid #E2E8F0 !important; border-radius: 8px !important; min-height: 38px !important; }
        div[data-baseweb="select"] > div:hover { border-color: #CBD5E1 !important; }
        div[data-testid="stSelectbox"] > div > div { background: #FFFFFF !important; border: 1px solid #E2E8F0 !important; border-radius: 8px !important; }
        textarea[data-testid="stTextAreaTextArea"] { background: #F8FAFC !important; border: 1px solid #E2E8F0 !important; border-radius: 8px !important; }
        textarea[data-testid="stTextAreaTextArea"]:focus { border-color: #3B82F6 !important; box-shadow: 0 0 0 3px rgba(59,130,246,.1) !important; }
        div[data-testid="stTextInput"] input, div[data-baseweb="input"] input { background: #FFFFFF !important; border-radius: 8px !important; }
        div[data-baseweb="input"], div[data-testid="stTextInput"] > div { background: #FFFFFF !important; border: 1px solid #D1D5DB !important; border-radius: 8px !important; }
        div[data-baseweb="input"]:focus-within, div[data-testid="stTextInput"] > div:focus-within { border-color: #3B82F6 !important; box-shadow: 0 0 0 3px rgba(59,130,246,.1) !important; }
        div[data-testid="stExpander"] div[data-testid="stVerticalBlockBorderWrapper"] { background: #FFFFFF !important; border: 1px solid #E2E8F0 !important; border-radius: 8px !important; }

        /* ── Kontrol animasi alert carousel ── */
        /* Pause saat hover supaya isi alert bisa dibaca */
        .ng-alert-bar:hover .ng-slide,
        .alert-carousel:hover .alert-slide,
        .rule-alert-bar:hover .rule-slide { animation-play-state: paused !important; }
        /* Hormati preferensi pengguna yang sensitif gerakan — tampilkan statis */
        @media (prefers-reduced-motion: reduce) {
            .ng-slide, .alert-slide, .rule-slide { animation: none !important; opacity: 1 !important; }
            .ng-slide:not(:first-child), .alert-slide:not(:first-child), .rule-slide:not(:first-child) { display: none !important; }
        }

        /* ── Login Page ── */
        .login-wrap {
            display: flex; align-items: center; justify-content: center;
            min-height: 100vh; background: #F1F4F9;
        }
        .login-card {
            background: #fff; border-radius: 16px; border: 1px solid #E8ECF2;
            box-shadow: 0 8px 32px rgba(15,23,42,.08);
            padding: 40px 36px 36px; width: 100%; max-width: 380px;
        }
        .login-logo {
            display: flex; align-items: center; gap: 12px; margin-bottom: 28px;
        }
        .login-logo-box {
            background: #DC2626; border-radius: 10px;
            width: 42px; height: 42px; display: flex; align-items: center; justify-content: center;
        }
        .login-logo-box span { color: #fff; font-weight: 900; font-size: 11px; letter-spacing: -0.3px; }
        .login-title { font-size: 20px; font-weight: 800; color: #0F172A; margin-bottom: 4px; }
        .login-sub   { font-size: 12px; font-weight: 500; color: #64748B; }

        /* ── Date Input — putih bersih ── */
        div[data-testid="stDateInput"] > div {
            background: #FFFFFF !important;
            border: 1px solid #E2E8F0 !important;
            border-radius: 8px !important;
        }
        div[data-testid="stDateInput"] > div:focus-within {
            border-color: #94A3B8 !important;
            box-shadow: 0 0 0 2px rgba(148,163,184,0.15) !important;
        }
        div[data-testid="stDateInput"] input {
            background: #FFFFFF !important;
            color: #0F172A !important;
        }

        </style>
        """, unsafe_allow_html=True)

    # ── LOGIN PAGE ────────────────────────────────────────────────
# ── LOGIN PAGE ────────────────────────────────────────────────
    def render_login(self):
        # CSS tambahan khusus untuk halaman login
        st.markdown("""
        <style>
        /* 1. Background utama halaman (Abu-abu kebiruan sangat soft) */
        [data-testid="stAppViewContainer"] {
            background: #F1F5F9 !important; 
        }
        
        /* 2. Mengubah kotak st.container menjadi Card Putih bersih dengan bayangan lembut */
        [data-testid="stVerticalBlockBorderWrapper"] {
            background-color: #FFFFFF !important;
            border-radius: 16px !important;
            border: 1px solid #E2E8F0 !important;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.04) !important;
        }
        
        /* 3. Memaksa area di dalam kotak ikut menjadi putih */
        [data-testid="stVerticalBlockBorderWrapper"] > div {
            background-color: #FFFFFF !important;
            border-radius: 16px !important;
        }

        /* 4. Membuat kotak input (username/password) sedikit abu-abu terang sebagai kontras */
        [data-testid="stTextInput"] > div > div {
            background-color: #F8FAFC !important;
            border: 1px solid #E2E8F0 !important;
            box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.02) !important;
        }
        [data-testid="stTextInput"] > div > div:focus-within {
            border-color: #FCA5A5 !important; /* Garis tepi merah muda saat diklik */
            box-shadow: 0 0 0 2px #FEE2E2 !important;
        }
        </style>
        """, unsafe_allow_html=True)
        # Center the login card using columns
        col1, col2, col3 = st.columns([1, 1.2, 1])
        with col2:
            _logo_url = _ahm_logo_b64()
            st.markdown(f"""
            <div style="margin-top: 80px;">
              <div style="display:flex; align-items:center; gap:12px; margin-bottom:28px;">
                {"<img src='"+_logo_url+"' style='height:42px;width:auto;object-fit:contain;flex-shrink:0;' />" if _logo_url else "<div style='background:#DC2626;border-radius:10px;width:42px;height:42px;display:flex;align-items:center;justify-content:center;'><span style='color:#fff;font-weight:900;font-size:11px;'>AHM</span></div>"}
                <div>
                  <div style="font-size:18px; font-weight:800; color:#0F172A; line-height:1.2;">CMM Quality Dashboard</div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            with st.container(border=True):
                st.markdown("<div style='margin-bottom:4px; font-size:15px; font-weight:700; color:#0F172A;'>Sign In</div>", unsafe_allow_html=True)
                st.markdown("<div style='font-size:11.5px; color:#64748B; margin-bottom:20px;'>Masukkan kredensial Anda untuk melanjutkan</div>", unsafe_allow_html=True)

                username = st.text_input("Username", placeholder="Username", label_visibility="collapsed")
                password = st.text_input("Password", placeholder="Password", type="password", label_visibility="collapsed")

                if st.button("Login", use_container_width=True, type="primary"):
                    if username in USERS and USERS[username]["password"] == password:
                        st.session_state["logged_in"] = True
                        st.session_state["username"]  = username
                        st.session_state["role"]      = USERS[username]["role"]
                        st.rerun()
                    else:
                        st.error("Username atau password salah.", icon="🔒")

    # ── SIDEBAR ───────────────────────────────────────────────────
# ── SIDEBAR ───────────────────────────────────────────────────
    def render_sidebar(self):
        role     = st.session_state.get("role", "Operator")
        username = st.session_state.get("username", "user")

        # Badge notifikasi untuk Messages
        unread = get_unread_count(role) if role in ("Produksi", "Admin") else 0

        pages = ROLE_PAGES[role]
        icons = [PAGE_ICONS[p] for p in pages]

        # Tambahkan badge ke label Messages kalau ada unread
        display_pages = []
        for p in pages:
            lbl = PAGE_LABELS.get(p, p)
            if p == "Messages" and unread > 0:
                display_pages.append(f"{lbl} ({unread})")
            else:
                display_pages.append(lbl)
        display_pages.append("Keluar")

        display_icons = icons + ["box-arrow-right"]

        # Map display label → page key sebenarnya
        label_to_page = {}
        for i, p in enumerate(pages):
            label_to_page[display_pages[i]] = p
        label_to_page["Keluar"] = "Logout"

        initials = username[:2].upper()

        with st.sidebar:
            # Header AHM — Logo SVG
            _logo_url_sb = _ahm_logo_b64()
            _logo_html = (f"<img src='{_logo_url_sb}' style='height:34px;width:auto;object-fit:contain;flex-shrink:0;' />"
                          if _logo_url_sb else
                          "<div style='background:#DC2626;border-radius:8px;width:34px;height:34px;flex-shrink:0;display:flex;align-items:center;justify-content:center;'><span style='color:#fff;font-weight:900;font-size:10px;'>AHM</span></div>")
            st.markdown(f"""
            <div style="padding:16px 20px 14px; display:flex; align-items:center; gap:12px;">
              {_logo_html}
            </div>
            <div style="height:1px; background:#E8ECF2; margin:0;"></div>
            <div style="height:8px;"></div>
            """, unsafe_allow_html=True)

            selected_label = option_menu(
                menu_title=None,
                options=display_pages,
                icons=display_icons,
                default_index=0,
                styles={
                    "container": {"padding": "0!important", "background-color": "#FFFFFF", "border": "none"},
                    "icon": {"color": "#64748B", "font-size": "15px"},
                    "nav-link": {"font-size": "13px", "text-align": "left", "margin": "2px 14px", "padding": "8px 14px", "color": "#475569", "font-weight": "600", "border-radius": "6px", "--hover-color": "#F1F5F9"},
                    "nav-link-selected": {"background-color": "#DC2626", "color": "#FFFFFF", "font-weight": "700"},
                }
            )

            if selected_label == "Keluar":
                st.session_state.clear()
                st.rerun()

            st.markdown(f"""
            <div style="position:fixed;bottom:0;left:0;width:240px;background:#FFFFFF;
                        z-index:99;border-top:1px solid #E8ECF2;padding:10px 16px;height:56px;">
              <div style="display:flex;align-items:center;gap:10px;">
                <div style="width:28px;height:28px;border-radius:50%;background:#DC2626;
                            flex-shrink:0;display:flex;align-items:center;justify-content:center;">
                  <span style="color:#fff;font-size:9px;font-weight:700;">{initials}</span>
                </div>
                <div>
                  <div style="font-size:12px;font-weight:700;color:#0F172A;">{username}</div>
                  <div style="font-size:10px;font-weight:500;color:#64748B;">{role}</div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        return label_to_page.get(selected_label, selected_label)

    # ── MAIN RUN ──────────────────────────────────────────────────
    def run(self):
        if "logged_in" not in st.session_state:
            st.session_state["logged_in"] = False

        if not st.session_state["logged_in"]:
            self.render_login()
            return

        # ── Keepalive via JS — tidak trigger rerun ─────────────────
        st.components.v1.html("""
        <script>
        // Kirim ping tiap 30 detik supaya WebSocket tidak putus
        setInterval(function() {
            window.parent.postMessage({type: 'streamlit:setComponentValue', value: null}, '*');
        }, 30000);
        </script>
        """, height=0)

        # Inisialisasi database lokal
        init_db()

        # ── Auto-refresh — hanya jalan kalau di halaman Dashboard ──
        # Halaman lain (Predictive, dll.) tidak boleh di-interrupt refresh
        _cur_page = st.session_state.get("_active_page", "Dashboard")
        if _cur_page == "Dashboard":
            st_autorefresh(interval=60_000, key="mtime_autorefresh")

        # ── Mtime check — reload cache hanya kalau DB berubah ─────
        # Gunakan threshold 5 detik agar file-write kecil tidak langsung trigger
        curr_mtime = _db_mtime()
        last_mtime = st.session_state.get("_db_mtime_last", 0.0)
        if curr_mtime - last_mtime > 5:
            load_data.clear()  # hanya reload measurements, bukan semua cache
            st.session_state["_db_mtime_last"] = curr_mtime

        df_all = load_data()

        # ── Warmup XGBoost + SPC rules ───────────────────────────
        # Fast path : load dari JSON (< 1 detik) kalau shift sama
        # Slow path : background thread kalau JSON belum ada / shift baru
        if not df_all.empty:
            import threading as _th
            from streamlit.runtime.scriptrunner import add_script_run_ctx
            from utils.xgb_inference import (
                run_xgb_inference, get_xgb_cache_key,
                run_rule_prediction, RULE_CACHE_KEY,
            )
            from utils.prediction_cache import load_xgb, load_rules

            _ck, _, _, _ = get_xgb_cache_key()
            _flag_key = f"_warmup_started_{_ck}"

            # Selalu coba load dari JSON dulu (tiap rerun — mungkin thread sudah selesai)
            if _ck not in st.session_state:
                _cached_xgb = load_xgb(_ck)
                if _cached_xgb is not None:
                    st.session_state[_ck] = _cached_xgb

            if RULE_CACHE_KEY not in st.session_state:
                _cached_rules = load_rules(_ck)
                if _cached_rules is not None:
                    st.session_state[RULE_CACHE_KEY] = _cached_rules

            _need_xgb  = _ck not in st.session_state
            _need_rule = RULE_CACHE_KEY not in st.session_state

            # Spawn thread hanya SEKALI per shift (flag di session_state)
            if (_need_xgb or _need_rule) and not st.session_state.get(_flag_key):
                st.session_state[_flag_key] = True

                def _bg_warmup(_df=df_all, _xgb=_need_xgb, _rule=_need_rule):
                    try:
                        if _xgb:  run_xgb_inference(_df)
                        if _rule: run_rule_prediction(_df)
                    except Exception:
                        pass
                _t = _th.Thread(target=_bg_warmup, daemon=True)
                # Attach ScriptRunContext dari main thread → tanpa ini,
                # st.session_state di dalam run_xgb_inference/run_rule_prediction
                # raise exception (no context), ketangkep "except Exception: pass",
                # dan thread ini SELALU gagal diam-diam tanpa compute apa-apa.
                add_script_run_ctx(_t)
                _t.start()
                st.toast("⚙️ Model prediksi sedang disiapkan di background...", icon="⚙️")

        username = st.session_state.get("username", "")

        selected_page = self.render_sidebar()

        # Override navigasi kalau ada flag dari halaman lain (misal Messages → Report)
        if st.session_state.get("nav_to_page"):
            selected_page = st.session_state.pop("nav_to_page")

        page_map = {
            "Dashboard":    lambda: DashboardPage(df_all),
            "Descriptive":  lambda: DescriptivePage(df_all),
            "Diagnostic":   lambda: DiagnosticPage(df_all),
            "Predictive":   lambda: PredictivePage(df_all),
            "Prescriptive": lambda: PrescriptivePage(df_all),
            "Messages":     lambda: MessagePage(df_all),
            "Report":       lambda: ReportPage(df_all, current_user=username),
            "Settings":     lambda: SettingsPage(df_all),
        }

        # Simpan halaman aktif — dipakai untuk kontrol auto-refresh
        st.session_state["_active_page"] = selected_page

        if selected_page in page_map:
            # Halaman berat (chart banyak) — tampil spinner singkat saat pertama render
            _heavy = {"Dashboard", "Descriptive", "Diagnostic", "Predictive", "Prescriptive"}
            _page_key = f"_page_rendered_{selected_page}"
            if selected_page in _heavy and not st.session_state.get(_page_key):
                with st.spinner(f"Memuat {selected_page}..."):
                    st.session_state[_page_key] = True
                    page_map[selected_page]().render()
            else:
                page_map[selected_page]().render()
            render_floating_chatbot()
        else:
            st.markdown(f"""
            <div style="display:flex; align-items:center; justify-content:center; height:60vh; flex-direction:column; gap:12px;">
              <div style="font-size:40px; color:#CBD5E1;">—</div>
              <div style="font-size:22px; font-weight:800; color:#0F172A;">{selected_page}</div>
              <div style="font-size:14px; color:#94A3B8;">Halaman ini belum tersedia.</div>
            </div>
            """, unsafe_allow_html=True)


if __name__ == "__main__":
    app = QualityDashboardApp()
    app.run()