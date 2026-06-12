"""
floating_chatbot.py — Asisten AI mengambang (floating chatbot).
═══════════════════════════════════════════════════════════════════════
Data diambil dari SQLite (data/cmm.db) — 7 hari terakhir dari tabel
measurements, max 8000 baris. API key Gemini dari .streamlit/secrets.toml.
"""
import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
from google import genai

if "GEMINI_API_KEY" in st.secrets:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
else:
    client = None

DB_PATH = Path("data/cmm.db")


@st.cache_data(ttl=300)
def load_chat_data() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    try:
        con = sqlite3.connect(DB_PATH, check_same_thread=False)
        df = pd.read_sql_query("""
            SELECT * FROM measurements
            WHERE Date >= date('now', '-7 days')
            ORDER BY Date DESC, Shift DESC
            LIMIT 8000
        """, con)
        con.close()
        num_cols = ["Nominal", "Uppertol", "Lowertol", "Actual", "Deviation"]
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()


def _get_hybrid_response(user_text: str) -> str:
    if not client:
        return "⚠️ Konfigurasi gagal: API Key Gemini belum dimasukkan di `.streamlit/secrets.toml`."

    df = load_chat_data()

    if df.empty:
        return "Maaf, saya tidak bisa menemukan data pengukuran di database."

    warning_msg = f"Catatan: Menampilkan {len(df):,} baris data 7 hari terakhir." if len(df) > 0 else ""
    csv_string  = df.to_csv(index=False)

    system_prompt = f"""
    Kamu adalah Asisten Quality Control AI yang ramah, cerdas, dan luwes untuk mesin CMM di PT Astra Honda Motor (AHM).

    ATURAN INTERAKSI:
    1. JIKA PENGGUNA MENYAPA (misal: "pagi", "halo", "bro", "terima kasih"):
       - Jawab dengan hangat dan natural layaknya rekan kerja.
       - Tawarkan bantuan untuk mengecek data produksi hari ini.
       - Jangan bertingkah kaku atau menyebutkan bahwa kamu sedang membaca data.

    2. JIKA PENGGUNA BERTANYA TENTANG ANGKA/DATA:
       - HANYA gunakan informasi dari DATA CSV MENTAH di bawah ini.
       - DILARANG KERAS berhalusinasi atau mengarang angka/nama part.
       - Jika datanya tidak ada, bilang saja tidak ditemukan di laporan saat ini.

    3. JIKA PERTANYAAN DI LUAR PEKERJAAN (misal: cuaca, politik, dll):
       - Tolak dengan sopan dan ingatkan bahwa fokusmu hanya untuk data CMM AHM.

    {warning_msg}

    ================ DATA CSV MENTAH ================
    {csv_string}
    =================================================

    Pertanyaan pengguna: "{user_text}"
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=system_prompt,
        )
        return response.text
    except Exception as e:
        return f"⚠️ Gagal terhubung ke server AI: {str(e)}"


def handle_chat_submit():
    user_text = st.session_state.user_chat_input
    if user_text.strip():
        st.session_state.chatbot_history.append({"role": "user", "content": user_text})


@st.fragment
def render_floating_chatbot():
    st.markdown("""
    <style>
    [data-testid="stPopover"] button svg { display: none !important; }
    [data-testid="stPopover"] { position: fixed !important; bottom: 28px !important; right: 28px !important; width: fit-content !important; z-index: 99999 !important; }
    [data-testid="stPopover"] > button { background-color: #1E293B !important; color: #FFFFFF !important; border-radius: 22px !important; padding: 0px 20px 0px 20px !important; height: 44px !important; width: fit-content !important; border: none !important; box-shadow: 0 4px 16px rgba(15,23,42,0.35) !important; font-weight: 600 !important; font-size: 14px !important; font-family: 'Inter', sans-serif !important; letter-spacing: 0.01em !important; transition: background .2s, transform .15s, box-shadow .2s !important; display: flex !important; align-items: center !important; justify-content: center !important; white-space: nowrap !important; }
    [data-testid="stPopover"] > button:hover, [data-testid="stPopover"] > button:active, [data-testid="stPopover"] > button:focus { background-color: #DC2626 !important; transform: translateY(-1px) !important; box-shadow: 0 6px 20px rgba(220,38,38,0.4) !important; color: #FFFFFF !important; border: none !important; outline: none !important; }
    [data-testid="stPopoverBody"] { width: 360px !important; border-radius: 16px !important; padding: 16px 20px !important; border: 1px solid #E2E8F0 !important; box-shadow: 0 20px 40px rgba(0, 0, 0, 0.12) !important; background-color: #FFFFFF !important; margin-bottom: 10px !important; overflow: hidden !important; }
    [data-testid="stPopoverBody"] [data-testid="stVerticalBlockBorderWrapper"] { border: none !important; padding: 0 !important; }
    [data-testid="stPopoverBody"] > div > div > div { gap: 4px !important; }
    [data-testid="stForm"] { border: none !important; padding: 0 !important; margin-top: 4px !important; }
    div[data-testid="InputInstructions"] { display: none !important; }
    .st-emotion-cache-1wmy9hl { scrollbar-width: none; }
    </style>
    """, unsafe_allow_html=True)

    with st.popover("💬 Tanya AI"):
        st.markdown("""
        <div style="margin-bottom: 4px;">
            <h4 style='margin: 0 0 2px 0; color:#0F172A; font-weight:800;'>🤖 CMM Assistant</h4>
            <p style='margin: 0 0 10px 0; font-size:13px; color:#64748B; font-weight:500;'>Ditenagai oleh Gemini AI</p>
            <hr style="margin: 0 0 6px 0; border: none; border-top: 1px solid #E2E8F0;">
        </div>
        """, unsafe_allow_html=True)

        if "chatbot_history" not in st.session_state:
            st.session_state.chatbot_history = [
                {"role": "ai", "content": "Halo! Saya Asisten AI Anda. Ada yang bisa dibantu terkait data CMM hari ini?"}
            ]

        chat_box = st.container(height=280)
        with chat_box:
            for msg in st.session_state.chatbot_history:
                if msg["role"] == "user":
                    st.markdown(f"""
                    <div style='display:flex; justify-content:flex-end; margin-bottom:8px;'>
                        <div style='background-color:#F1F5F9; padding:10px 14px; border-radius:14px 14px 0 14px; max-width:85%;'>
                            <span style='font-size:13.5px; color:#334155; line-height:1.4;'>{msg['content']}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style='display:flex; justify-content:flex-start; margin-bottom:8px;'>
                        <div style='background-color:#FEF2F2; border:1px solid #FECACA; padding:10px 14px; border-radius:14px 14px 14px 0; max-width:85%;'>
                            <span style='font-size:13.5px; color:#991B1B; line-height:1.4;'>{msg['content']}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            if st.session_state.chatbot_history and st.session_state.chatbot_history[-1]["role"] == "user":
                with st.spinner("🤖 AI sedang berpikir..."):
                    user_msg = st.session_state.chatbot_history[-1]["content"]
                    reply    = _get_hybrid_response(user_msg)

                    st.markdown(f"""
                    <div style='display:flex; justify-content:flex-start; margin-bottom:8px;'>
                        <div style='background-color:#FEF2F2; border:1px solid #FECACA; padding:10px 14px; border-radius:14px 14px 14px 0; max-width:85%;'>
                            <span style='font-size:13.5px; color:#991B1B; line-height:1.4;'>{reply}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    st.session_state.chatbot_history.append({"role": "ai", "content": reply})

        with st.form("chat_input_form", clear_on_submit=True):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.text_input("Pesan", placeholder="Ketik pesan...", key="user_chat_input", label_visibility="collapsed")
            with col2:
                st.form_submit_button("➤", use_container_width=True, on_click=handle_chat_submit)