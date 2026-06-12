"""
pages_app/settings.py — Halaman Pengaturan aplikasi.
═══════════════════════════════════════════════════════════════════════
Tiga tab:
  • Target OK      — target rasio OK global (dipakai Dashboard & Descriptive)
  • Target Sample  — jumlah sample per shift per part/model
  • Info           — info sistem & reset ke nilai default
Konfigurasi disimpan/dibaca lewat settings_config.py (file JSON).
"""
import streamlit as st
import pandas as pd
import sys
from pathlib import Path

# Pastikan root project ada di sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from settings_config import load_settings, save_settings, DEFAULTS

# ─────────────────────────────────────────────────────────────────
# MAIN PAGE CLASS
# ─────────────────────────────────────────────────────────────────

class SettingsPage:
    def __init__(self, df_all: pd.DataFrame, current_user: str = "Operator"):
        self.df_all       = df_all
        self.current_user = current_user

        # Ambil opsi part & model dari data
        self.all_parts  = sorted(df_all["PartName"].dropna().unique().tolist()) if not df_all.empty else []
        self.all_models = sorted(df_all["ModelName"].dropna().unique().tolist()) if not df_all.empty else []

    # ─────────────────────────────────────────────────────────────
    def render(self):
        st.markdown(
            '<div class="page-hdr">'
            '<span class="page-title">Settings</span>'
            '</div>'
            '<div class="section-desc">Konfigurasi target OK rate dan jumlah sample per shift.</div>',
            unsafe_allow_html=True,
        )

        tab1, tab2, tab3 = st.tabs([
            "Target OK",
            "Target Sample",
            "Info",
        ])

        with tab1:
            self._render_target_ok()
        with tab2:
            self._render_sample_targets()
        with tab3:
            self._render_info()

    # ══════════════════════════════════════════════════════════════
    #  TAB 1 — TARGET OK GLOBAL
    # ══════════════════════════════════════════════════════════════
    def _render_target_ok(self):
        cfg = load_settings()

        st.markdown("### Target OK Rate")

        with st.container(border=True):
            st.markdown("**Target OK Global (%)**")
            st.markdown(
                '<div style="font-size:11px;color:#64748B;margin-bottom:10px;">'
                'Dipakai di Dashboard chart target line, KPI coloring, dan Descriptive.</div>',
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns([1, 3])
            with c1:
                new_global = st.number_input(
                    "Target OK Global (%)",
                    min_value=0.0, max_value=100.0,
                    value=float(cfg.get("target_ok_global", 98.65)),
                    step=0.01, format="%.2f",
                    key="cfg_global_ok",
                    label_visibility="collapsed",
                )
            with c2:
                st.markdown(
                    f'<div style="padding:6px 0;font-size:12px;color:#64748B;">'
                    f'Nilai saat ini: <b style="color:#0F172A;">{cfg.get("target_ok_global", 98.65):.2f}%</b></div>',
                    unsafe_allow_html=True,
                )

        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

        if st.button("Simpan", type="primary", key="save_target_ok"):
            cfg["target_ok_global"] = round(float(new_global), 4)
            if save_settings(cfg):
                st.success("✓ Target OK tersimpan.")
                st.rerun()
            else:
                st.error("Gagal menyimpan settings.")

    # ══════════════════════════════════════════════════════════════
    #  TAB 2 — SAMPLE TARGETS
    # ══════════════════════════════════════════════════════════════
    def _render_sample_targets(self):
        cfg = load_settings()

        st.markdown("### Target Sample per Part / Model / Shift")
        st.markdown(
            '<div style="font-size:12px;color:#64748B;margin-bottom:16px;">'
            'Target jumlah sample yang harus diukur per shift. '
            'Shift 0 = default semua shift. Digunakan di card Status Kualitas per Part.</div>',
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            raw = cfg.get("sample_targets", {})
            rows_st = []
            for key, val in raw.items():
                parts = key.split("|")
                if len(parts) == 3:
                    rows_st.append({
                        "Part":   parts[0],
                        "Model":  parts[1],
                        "Shift":  parts[2],
                        "Target": int(val),
                    })

            df_st = pd.DataFrame(
                rows_st if rows_st else [{"Part": "", "Model": "", "Shift": "0", "Target": 0}],
                columns=["Part", "Model", "Shift", "Target"],
            )

            # Sort supaya rapi
            df_st = df_st.sort_values(["Part", "Model", "Shift"]).reset_index(drop=True)

            edited_st = st.data_editor(
                df_st,
                use_container_width=True,
                num_rows="dynamic",
                hide_index=True,
                key="cfg_sample_targets_editor",
                column_config={
                    "Part": st.column_config.SelectboxColumn(
                        "Part", options=self.all_parts, required=False,
                    ),
                    "Model": st.column_config.SelectboxColumn(
                        "Model", options=self.all_models, required=False,
                    ),
                    "Shift": st.column_config.SelectboxColumn(
                        "Shift",
                        options=["0", "1", "2", "3"],
                        help="0 = default semua shift",
                        required=False,
                    ),
                    "Target": st.column_config.NumberColumn(
                        "Target Sample", min_value=0, step=1, format="%d",
                    ),
                },
            )

        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

        if st.button("Simpan", type="primary", key="save_sample_targets"):
            new_st = {}
            for _, row in edited_st.iterrows():
                p = str(row.get("Part", "")).strip()
                m = str(row.get("Model", "")).strip()
                s = str(row.get("Shift", "0")).strip()
                t = row.get("Target")
                if p and m and s and t is not None:
                    new_st[f"{p}|{m}|{s}"] = int(t)

            cfg["sample_targets"] = new_st

            if save_settings(cfg):
                st.success("✓ Sample Targets tersimpan.")
                st.rerun()
            else:
                st.error("Gagal menyimpan settings.")

    # ══════════════════════════════════════════════════════════════
    #  TAB 3 — INFO SISTEM
    # ══════════════════════════════════════════════════════════════
    def _render_info(self):
        from settings_config import SETTINGS_PATH

        st.markdown("### ℹ️ Info Sistem")

        with st.container(border=True):
            c1, c2 = st.columns(2)

            with c1:
                st.markdown("**📁 Data CSV**")
                if not self.df_all.empty:
                    n_rows  = len(self.df_all)
                    n_parts = self.df_all["PartName"].nunique()
                    n_model = self.df_all["ModelName"].nunique()
                    last_dt = self.df_all["Date"].max().strftime("%d %b %Y") if "Date" in self.df_all.columns else "—"
                    st.markdown(
                        f'<div style="font-size:12px;line-height:2;">'
                        f'Jumlah baris: <b>{n_rows:,}</b><br>'
                        f'Part: <b>{n_parts}</b> &nbsp;·&nbsp; Model: <b>{n_model}</b><br>'
                        f'Data terakhir: <b>{last_dt}</b>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.warning("Data CSV kosong atau tidak ditemukan.")

            with c2:
                st.markdown("**Settings JSON**")
                exists = SETTINGS_PATH.exists()
                if exists:
                    import os
                    size = os.path.getsize(SETTINGS_PATH)
                    mtime = pd.Timestamp(SETTINGS_PATH.stat().st_mtime, unit="s").strftime("%d %b %Y %H:%M")
                    st.markdown(
                        f'<div style="font-size:12px;line-height:2;">'
                        f'Status: <b style="color:#16A34A;">✓ Ada</b><br>'
                        f'Ukuran: <b>{size} bytes</b><br>'
                        f'Terakhir diubah: <b>{mtime}</b>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        '<div style="font-size:12px;line-height:2;">'
                        'Status: <b style="color:#F59E0B;">⚠ Belum ada</b><br>'
                        '<span style="color:#94A3B8;">Akan dibuat otomatis saat pertama kali simpan.</span>'
                        '</div>',
                        unsafe_allow_html=True,
                    )

        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

        # Reset ke default
        with st.expander("Reset ke Default", expanded=False):
            st.warning("Semua setting akan dikembalikan ke nilai default. Data Root Cause dan laporan tidak terpengaruh.")
            if st.button("Reset Settings", type="secondary", key="reset_settings"):
                from settings_config import DEFAULTS
                if save_settings({k: (v.copy() if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}):
                    st.success("✓ Settings direset ke default.")
                    st.rerun()