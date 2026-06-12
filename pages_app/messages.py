"""
pages/messages.py  —  Notifikasi NG · Root Cause Produksi
"""
import streamlit as st
from datetime import datetime

from local_db import (
    get_ng_notifs, get_ng_notifs_sent,
    mark_ng_notif_read,
    save_root_cause, get_root_causes,
    RC_CATEGORIES, RC_STATUSES, _rc_key,
)

STATUS_CLR = {
    "Open":         ("background-color:#FEE2E2;color:#991B1B;font-weight:600;"),
    "Investigated": ("background-color:#FEF3C7;color:#92400E;font-weight:600;"),
    "Resolved":     ("background-color:#DCFCE7;color:#14532D;font-weight:600;"),
}
STATUS_BADGE = {
    "Open":         ("#DC2626","#FEE2E2"),
    "Investigated": ("#D97706","#FEF3C7"),
    "Resolved":     ("#16A34A","#DCFCE7"),
}

# ── Cached loaders ────────────────────────────────────────────────────────────
@st.cache_data(ttl=15, show_spinner=False)
def _cached_notifs(to_role: str = "Produksi") -> list:
    return get_ng_notifs(to_role)

@st.cache_data(ttl=15, show_spinner=False)
def _cached_notifs_sent(username: str) -> list:
    return get_ng_notifs_sent(username)

@st.cache_data(ttl=15, show_spinner=False)
def _cached_rc_all() -> dict:
    return {rc["rc_key"]: rc for rc in get_root_causes()}

def _invalidate():
    _cached_notifs.clear()
    _cached_notifs_sent.clear()
    _cached_rc_all.clear()

def _fmt(ts: str) -> str:
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").strftime("%d %b %Y  %H:%M")
    except Exception:
        return ts or "—"

def _notif_key(n: dict) -> str:
    return _rc_key(n.get("date",""), n.get("shift",""), n.get("sampleno",""),
                   n.get("part",""), n.get("model",""), n.get("ref",""), n.get("parameter",""))


# ── Page ──────────────────────────────────────────────────────────────────────
class MessagePage:
    def __init__(self, df_all=None):
        self.df_all = df_all

    def render(self):
        role     = st.session_state.get("role", "")
        username = st.session_state.get("username", "")
        st.markdown("""
        <div class="page-hdr"><span class="page-title">Pesan</span>
        <span class="page-sub">Notifikasi Titik NG</span></div>
        <div class="section-desc">Notifikasi NG otomatis dari laporan CMM · Produksi input root cause langsung dari sini.</div>
        """, unsafe_allow_html=True)
        if role == "Produksi":
            self._render_inbox(username)
        else:
            self._render_sent(username)

    # ── INBOX Produksi ────────────────────────────────────────────────────────
    @st.fragment
    def _render_inbox(self, username: str):
        import pandas as pd

        notifs = _cached_notifs("Produksi")
        rc_all = _cached_rc_all()

        if not notifs:
            st.markdown(
                '<div style="text-align:center;padding:60px;color:#94A3B8;">'
                '<div style="font-size:32px;margin-bottom:12px;">✅</div>'
                '<div style="font-size:14px;font-weight:600;">Tidak ada titik NG</div>'
                '</div>', unsafe_allow_html=True)
            return

        # Pre-compute RC status untuk semua notif (1 pass)
        for n in notifs:
            rc = rc_all.get(_notif_key(n), {})
            n["_rc_status"] = rc.get("status","Open") if rc else "Open"
            n["_rc_key"]    = _notif_key(n)

        unread = sum(1 for n in notifs if n.get("is_read") == "0")
        if unread > 0:
            st.info(f"**{unread} titik NG baru**")

        # ── Filter ────────────────────────────────────────────────────────────
        # Pills: status
        f_status = st.pills(
            "Status", ["Semua","Open","Resolved"],
            default="Open", key="msg_f_status",
            label_visibility="collapsed", selection_mode="single"
        ) or "Open"

        fa1, fa2, fa3 = st.columns(3)
        with fa1:
            _pm_opts = ["Semua Part & Model"] + sorted({
                f"{n.get('part','')} · {n.get('model','')}"
                for n in notifs if n.get("part") or n.get("model")
            })
            f_pm = st.selectbox("Part · Model", _pm_opts, key="msg_f_pm")
        with fa2:
            _dates = ["Semua Tanggal"] + sorted(
                {n.get("date","") for n in notifs if n.get("date","")}, reverse=True)
            f_date = st.selectbox("Tanggal", _dates, key="msg_f_date")
        with fa3:
            f_sort = st.selectbox("Urutkan", ["Terbaru","Terlama"], key="msg_f_sort")

        # Terapkan filter
        filtered = list(notifs)
        if f_status != "Semua":
            filtered = [n for n in filtered if n["_rc_status"] == f_status]
        if f_pm != "Semua Part & Model":
            filtered = [n for n in filtered
                        if f"{n.get('part','')} · {n.get('model','')}" == f_pm]
        if f_date != "Semua Tanggal":
            filtered = [n for n in filtered if n.get("date","") == f_date]

        # Sort
        def _sort_key(n):
            try:
                return datetime.strptime(n.get("created_at",""), "%Y-%m-%d %H:%M:%S")
            except Exception:
                return datetime.min
        filtered.sort(key=_sort_key, reverse=(f_sort == "Terbaru"))

        if not filtered:
            st.info("Tidak ada notifikasi untuk filter ini.")
            return

        # ── Group by date / shift / part / model (mirip diagnostic) ──────────
        from collections import defaultdict
        groups: dict = defaultdict(list)
        for n in filtered:
            gk = (n.get("date",""), str(n.get("shift","")),
                  n.get("sampleno",""), n.get("part",""), n.get("model",""))
            groups[gk].append(n)

        # Pagination
        PER_PAGE   = 10
        grp_list   = list(groups.items())
        total_grps = len(grp_list)
        total_pages= max(1, (total_grps + PER_PAGE - 1) // PER_PAGE)

        _fsig = f"{f_status}|{f_pm}|{f_date}|{f_sort}"
        if st.session_state.get("_msg_fsig") != _fsig:
            st.session_state["_msg_fsig"] = _fsig
            st.session_state["msg_page"]  = 1
        cur_pg = max(1, min(st.session_state.get("msg_page", 1), total_pages))

        pc1, pc2, pc3, pc4, pc5 = st.columns([2, 1, 2, 1, 2])
        pc1.caption(f"{len(filtered)} titik · {total_grps} grup · hal. {cur_pg}/{total_pages}")
        if pc2.button("<", key="msg_prev", disabled=(cur_pg<=1)):
            st.session_state["msg_page"] = cur_pg - 1; st.rerun()
        pc3.markdown(
            f"<div style='text-align:center;font-size:12px;padding-top:6px;color:#64748B;'>"
            f"Hal. {cur_pg}/{total_pages}</div>", unsafe_allow_html=True)
        if pc4.button(">", key="msg_next", disabled=(cur_pg>=total_pages)):
            st.session_state["msg_page"] = cur_pg + 1; st.rerun()
        pc5.empty()

        page_groups = grp_list[(cur_pg-1)*PER_PAGE : cur_pg*PER_PAGE]

        for gk, items in page_groups:
            date_str, shift, sampleno_grp, part, model = gk
            n_open  = sum(1 for i in items if i["_rc_status"] == "Open")
            n_res   = sum(1 for i in items if i["_rc_status"] == "Resolved")
            n_kp_ng = sum(1 for i in items if i.get("kp","0") == "1")
            icon    = "🟢" if n_open == 0 else ("🔴" if n_open == len(items) else "🟡")

            _kp_txt = f"  ·  ⚠ {n_kp_ng} KP NG" if n_kp_ng > 0 else ""
            title = (
                f"{icon}  {part} — {model}"
                f"  ·  Sample {sampleno_grp}  ·  Shift {shift}  ·  {date_str}"
                f"  ·  {len(items)} NG{_kp_txt}"
                f"  ·  {n_open} Open  ·  {n_res} Resolved"
            )

            with st.expander(title, expanded=(n_open > 0 and len(groups) == 1)):
                # Tandai semua unread dalam grup ini sebagai read
                for n in items:
                    if n.get("is_read") == "0":
                        mark_ng_notif_read(n["id"])
                        _invalidate()

                # Build dataframe
                tbl_data = []
                for n in items:
                    rc  = rc_all.get(n["_rc_key"], {})
                    tbl_data.append({
                        "Ref":       n.get("ref","—"),
                        "Parameter": n.get("parameter","—"),
                        "Sample":    n.get("sampleno",""),
                        "KP":        n.get("kp","0") == "1",
                        "Deviasi":   n.get("deviation",""),
                        "Status":    n["_rc_status"],
                        "Kategori":  rc.get("category","") if rc else "",
                        "Penanggung Jawab":       rc.get("pic","") if rc else "",
                    })
                df_tbl = pd.DataFrame(tbl_data)

                safe_grp = str(abs(hash(str(gk))))[:8]
                tbl_key  = f"msg_tbl_{safe_grp}"

                def _row_style(row, _cols=df_tbl.columns):
                    styles = [""] * len(row)
                    idx_s = list(_cols).index("Status")
                    styles[idx_s] = STATUS_CLR.get(row["Status"], "")
                    return styles

                if st.session_state.pop(f"clear_{tbl_key}", False):
                    if tbl_key in st.session_state:
                        del st.session_state[tbl_key]
                    # Reset form keys agar re-init dari DB
                    for _ck in list(st.session_state.keys()):
                        if any(_ck.startswith(_pfx) for _pfx in
                               ("msg_cat_","msg_sts_","msg_desc_","msg_corr_","msg_pic_")):
                            del st.session_state[_ck]

                event = st.dataframe(
                    df_tbl.style.apply(_row_style, axis=1),
                    use_container_width=True,
                    hide_index=True,
                    height=min(400, 42 + len(tbl_data) * 36),
                    selection_mode="multi-row",
                    on_select="rerun",
                    key=tbl_key,
                    column_config={
                        "KP":      st.column_config.CheckboxColumn("KP", width="small"),
                        "Deviasi": st.column_config.TextColumn("Deviasi", width="small"),
                    }
                )

                sel_rows = [i for i in event.selection.rows if i < len(items)]

                if sel_rows:
                    sel_items = [items[i] for i in sel_rows]
                    sel_keys  = [n["_rc_key"] for n in sel_items]
                    n_sel     = len(sel_items)

                    # Pre-populate dari baris pertama yang punya RC tersimpan
                    first_rc  = next((rc_all[k] for k in sel_keys if k in rc_all), {})
                    safe_key  = str(abs(hash(tbl_key + str(sorted(sel_rows)))))[:8]

                    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
                    with st.container(border=True):
                        # Header
                        if n_sel == 1:
                            n_single = sel_items[0]
                            kp_tag = "  🔴 KP" if n_single.get("kp","0") == "1" else ""
                            st.markdown(
                                f'<div style="font-size:13px;font-weight:700;color:#0F172A;margin-bottom:3px;">'
                                f'{n_single.get("ref","—")} · {n_single.get("parameter","—")}{kp_tag}</div>'
                                f'<div style="font-size:11px;color:#64748B;margin-bottom:10px;">'
                                f'Deviasi: <b style="color:#DC2626;">{n_single.get("deviation","")}</b>'
                                f' · {part} {model} · Shift {shift} · {date_str}'
                                f' · Sample {sampleno_grp}</div>',
                                unsafe_allow_html=True
                            )
                        else:
                            refs_list = ", ".join(
                                f"{n.get('ref','—')} · {n.get('parameter','—')}"
                                for n in sel_items
                            )
                            st.markdown(
                                f'<div style="background:#EFF6FF;border-radius:8px;'
                                f'padding:8px 12px;margin-bottom:10px;">'
                                f'<span style="font-size:13px;font-weight:700;color:#1D4ED8;">'
                                f'{n_sel} titik dipilih</span>'
                                f'<div style="font-size:11px;color:#3B82F6;margin-top:3px;line-height:1.6;">{refs_list}</div>'
                                f'<div style="font-size:10px;color:#64748B;margin-top:4px;">'
                                f'Form di bawah akan diterapkan ke semua titik yang dipilih.</div>'
                                f'</div>',
                                unsafe_allow_html=True
                            )

                        rc1, rc2 = st.columns(2)
                        with rc1:
                            cat = st.selectbox(
                                "Kategori Root Cause", RC_CATEGORIES,
                                index=(RC_CATEGORIES.index(first_rc["category"])
                                       if first_rc.get("category") in RC_CATEGORIES else 0),
                                key=f"msg_cat_{safe_key}"
                            )
                        with rc2:
                            fst = st.selectbox(
                                "Status Root Cause", RC_STATUSES,
                                index=(RC_STATUSES.index(first_rc["status"])
                                       if first_rc.get("status") in RC_STATUSES else 1),
                                key=f"msg_sts_{safe_key}"
                            )
                        desc = st.text_area(
                            "Deskripsi Penyebab *",
                            value=first_rc.get("description",""),
                            placeholder="Jelaskan penyebab NG...",
                            height=80, key=f"msg_desc_{safe_key}"
                        )
                        corr = st.text_area(
                            "Tindakan Perbaikan",
                            value=first_rc.get("corrective_action",""),
                            placeholder="Tindakan perbaikan (opsional)...",
                            height=60, key=f"msg_corr_{safe_key}"
                        )
                        pic = st.text_input(
                            "Penanggung Jawab", value=first_rc.get("pic",""),
                            placeholder="Nama penanggung jawab...",
                            key=f"msg_pic_{safe_key}"
                        )
                        btn_lbl = f"Simpan ({n_sel} titik)" if n_sel > 1 else "Simpan Root Cause"
                        if st.button(btn_lbl, type="primary",
                                     use_container_width=True, key=f"msg_save_{safe_key}"):
                            if not desc.strip():
                                st.warning("Deskripsi wajib diisi.")
                            else:
                                for n_item in sel_items:
                                    save_root_cause({
                                        "rc_key":            n_item["_rc_key"],
                                        "date":              n_item.get("date",""),
                                        "shift":             n_item.get("shift",""),
                                        "sampleno":          n_item.get("sampleno",""),
                                        "part":              part,
                                        "model":             model,
                                        "ref":               n_item.get("ref",""),
                                        "id_ukur":           "",
                                        "parameter":         n_item.get("parameter",""),
                                        "deviation":         n_item.get("deviation",""),
                                        "category":          cat,
                                        "description":       desc.strip(),
                                        "corrective_action": corr.strip(),
                                        "status":            fst,
                                        "inputted_by":       username,
                                        "inputted_role":     "Produksi",
                                        "pic":               pic.strip(),
                                    })
                                _invalidate()
                                st.success(f"✓ {n_sel} titik tersimpan")
                                st.session_state[f"clear_{tbl_key}"] = True
                                st.rerun()
                else:
                    st.caption("👆 Klik satu atau lebih baris untuk input root cause.")

    # ── SENT BOX (Measurement) ────────────────────────────────────────────────
    @st.fragment
    def _render_sent(self, username: str):
        import pandas as pd
        from collections import defaultdict

        notifs = _cached_notifs_sent(username)
        rc_all = _cached_rc_all()

        st.markdown(
            '<div style="font-size:14px;font-weight:600;color:#0F172A;'
            'margin-bottom:12px;">Notifikasi NG Terkirim</div>',
            unsafe_allow_html=True
        )
        if not notifs:
            st.info("Notifikasi NG otomatis terkirim ke Produksi saat kamu Simpan laporan.")
            return

        # Pre-compute RC status
        for n in notifs:
            rc = rc_all.get(_notif_key(n), {})
            n["_rc_status"] = rc.get("status","Open") if rc else "Open"

        # Group by date / shift / sampleno / part / model
        groups: dict = defaultdict(list)
        for n in notifs:
            gk = (n.get("date",""), str(n.get("shift","")),
                  n.get("sampleno",""), n.get("part",""), n.get("model",""))
            groups[gk].append(n)

        st.caption(f"{len(notifs)} titik NG · {len(groups)} grup")

        for gk, items in groups.items():
            date_str, shift, sampleno_grp, part, model = gk
            n_open  = sum(1 for i in items if i["_rc_status"] == "Open")
            n_res   = sum(1 for i in items if i["_rc_status"] == "Resolved")
            n_kp_ng = sum(1 for i in items if i.get("kp","0") == "1")
            icon    = "🟢" if n_open == 0 else ("🔴" if n_open == len(items) else "🟡")

            _kp_txt = f"  ·  ⚠ {n_kp_ng} KP NG" if n_kp_ng > 0 else ""
            title = (
                f"{icon}  {part} — {model}"
                f"  ·  Sample {sampleno_grp}  ·  Shift {shift}  ·  {date_str}"
                f"  ·  {len(items)} NG{_kp_txt}"
                f"  ·  {n_open} Open  ·  {n_res} Resolved"
            )

            with st.expander(title, expanded=False):
                tbl_data = []
                for n in items:
                    rc = rc_all.get(_notif_key(n), {})
                    tbl_data.append({
                        "Ref":       n.get("ref","—"),
                        "Parameter": n.get("parameter","—"),
                        "KP":        n.get("kp","0") == "1",
                        "Deviasi":   n.get("deviation",""),
                        "Status Root Cause": n["_rc_status"],
                        "Kategori":  rc.get("category","") if rc else "",
                        "Penanggung Jawab":       rc.get("pic","") if rc else "",
                    })

                def _row_style_s(row, _cols=pd.DataFrame(tbl_data).columns):
                    styles = [""] * len(row)
                    idx_s = list(_cols).index("Status Root Cause")
                    styles[idx_s] = STATUS_CLR.get(row["Status Root Cause"], "")
                    return styles

                df_s = pd.DataFrame(tbl_data)
                st.dataframe(
                    df_s.style.apply(_row_style_s, axis=1),
                    use_container_width=True,
                    hide_index=True,
                    height=min(400, 42 + len(tbl_data) * 36),
                    column_config={
                        "KP":      st.column_config.CheckboxColumn("KP", width="small"),
                        "Deviasi": st.column_config.TextColumn("Deviasi", width="small"),
                    }
                )