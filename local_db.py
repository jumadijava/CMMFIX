"""
local_db.py
───────────
Persistent storage menggunakan SQLite (data/cmm.db).
Menggantikan semua CSV runtime dan REALNEO.csv.

Satu file DB:  data/cmm.db
  tabel measurements  ← pengganti REALNEO.csv
  tabel reports       ← metadata laporan
  tabel messages      ← inbox notifikasi
  tabel ng_notifs     ← notifikasi titik NG
  tabel root_causes   ← riwayat root cause

data/reports/*.json tetap disimpan sebagai JSON (data laporan lengkap).
Interface ke halaman lain tidak berubah sama sekali.
Migrasi CSV lama → SQLite terjadi otomatis sekali saat init_db().

Nanti kalau pindah ke PostgreSQL: ganti _conn() dan DB_PATH saja,
semua logic query tidak perlu diubah.
"""

import sqlite3
import uuid
import json
import csv
import pandas as pd
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

# ── Paths ─────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent
DATA_DIR    = BASE_DIR / "data"
DB_PATH     = DATA_DIR / "cmm.db"
REPORTS_DIR = DATA_DIR / "reports"

# Legacy CSV paths — hanya dipakai saat migrasi
REPORTS_CSV     = DATA_DIR / "reports.csv"
MESSAGES_CSV    = DATA_DIR / "messages.csv"
NG_NOTIFS_CSV   = DATA_DIR / "ng_notifs.csv"
ROOT_CAUSES_CSV = DATA_DIR / "root_causes.csv"

# ── Constants ─────────────────────────────────────────────────────
RC_CATEGORIES = [
    "Mesin / Machine", "Setup / Fixture", "Material",
    "Operator", "Program CMM", "Tooling", "Lainnya",
]
RC_STATUSES = ["Open", "Investigated", "Resolved"]


# ═══════════════════════════════════════════════════════════════
#  CONNECTION HELPER
# ═══════════════════════════════════════════════════════════════

@contextmanager
def _conn():
    """
    Context manager koneksi SQLite.
    WAL mode → banyak reader bisa jalan bersamaan dengan 1 writer.
    """
    DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── Schema ─────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    Date      TEXT,
    Shift     TEXT,
    Cycle     TEXT,
    SampleNo  TEXT,
    PartName  TEXT,
    ModelName TEXT,
    CMMName   TEXT,
    ref       TEXT,
    ID        TEXT,
    point     TEXT,
    Parameter TEXT,
    Nominal   REAL,
    Uppertol  REAL,
    Lowertol  REAL,
    Actual    REAL,
    Deviation REAL,
    Judgement TEXT,
    KP        TEXT,
    Category  TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id           TEXT PRIMARY KEY,
    part         TEXT,
    model        TEXT,
    shift        TEXT,
    tanggal      TEXT,
    sent_by      TEXT,
    status       TEXT DEFAULT 'draft',
    created_at   TEXT,
    sent_at      TEXT DEFAULT '',
    confirmed_by TEXT DEFAULT '',
    confirmed_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS messages (
    id         TEXT PRIMARY KEY,
    report_id  TEXT,
    from_user  TEXT,
    to_role    TEXT,
    created_at TEXT,
    is_read    TEXT DEFAULT '0'
);

CREATE TABLE IF NOT EXISTS ng_notifs (
    id          TEXT PRIMARY KEY,
    from_user   TEXT,
    from_role   TEXT,
    to_role     TEXT DEFAULT 'Produksi',
    part        TEXT,
    model       TEXT,
    ref         TEXT,
    parameter   TEXT,
    sampleno    TEXT,
    date        TEXT,
    shift       TEXT,
    deviation   TEXT,
    kp          TEXT DEFAULT '0',
    category    TEXT,
    description TEXT,
    pic         TEXT,
    status      TEXT DEFAULT 'Open',
    report_id   TEXT DEFAULT '',
    created_at  TEXT,
    is_read     TEXT DEFAULT '0'
);

CREATE TABLE IF NOT EXISTS root_causes (
    id                TEXT PRIMARY KEY,
    rc_key            TEXT UNIQUE,
    date              TEXT,
    shift             TEXT,
    sampleno          TEXT,
    part              TEXT,
    model             TEXT,
    ref               TEXT,
    id_ukur           TEXT,
    parameter         TEXT,
    deviation         TEXT,
    category          TEXT,
    description       TEXT,
    corrective_action TEXT,
    status            TEXT DEFAULT 'Investigated',
    inputted_by       TEXT,
    inputted_role     TEXT,
    pic               TEXT,
    inputted_at       TEXT,
    updated_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_meas_date     ON measurements(Date);
CREATE INDEX IF NOT EXISTS idx_meas_part     ON measurements(PartName);
CREATE INDEX IF NOT EXISTS idx_meas_model    ON measurements(ModelName);

CREATE INDEX IF NOT EXISTS idx_msg_role      ON messages(to_role, is_read);
CREATE INDEX IF NOT EXISTS idx_ng_role       ON ng_notifs(to_role, is_read);
CREATE INDEX IF NOT EXISTS idx_rc_key        ON root_causes(rc_key);
CREATE INDEX IF NOT EXISTS idx_rc_part_model ON root_causes(part, model);
CREATE INDEX IF NOT EXISTS idx_rep_sent_by   ON reports(sent_by);
"""


# ═══════════════════════════════════════════════════════════════
#  INIT & MIGRATION
# ═══════════════════════════════════════════════════════════════

def _ensure_unique_index() -> None:
    """
    Buat UNIQUE index di measurements.
    Aman untuk DB lama: deduplicate dulu sebelum buat index.
    Skip kalau index sudah ada.
    """
    with _conn() as con:
        exists = con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_meas_unique'"
        ).fetchone()
        if exists:
            return
        # Hapus duplikat — keep row dengan id terkecil
        con.execute("""
            DELETE FROM measurements WHERE id NOT IN (
                SELECT MIN(id) FROM measurements
                GROUP BY Date, Cycle, PartName, ModelName, ref, ID, point, Parameter, Nominal, Uppertol
            )
        """)
        con.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_meas_unique
            ON measurements(Date, Cycle, PartName, ModelName, ref, ID, point, Parameter, Nominal, Uppertol)
        """)


def init_db() -> None:
    """
    Buat folder, DB, schema.
    Auto-migrate CSV runtime lama ke SQLite kalau masih ada.
    """
    DATA_DIR.mkdir(exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)
    with _conn() as con:
        con.executescript(_SCHEMA)
    _ensure_unique_index()
    _migrate_csv_if_needed()


def _read_csv_file(path: Path, cols: list) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for c in cols:
            row.setdefault(c, "")
    return rows


def _migrate_csv_if_needed() -> None:
    """
    Migrasi satu kali dari CSV lama ke SQLite.
    Setelah selesai, CSV di-rename jadi .csv.bak agar tidak migrasi ulang.
    """
    pairs = [
        (REPORTS_CSV,     _migrate_reports),
        (MESSAGES_CSV,    _migrate_messages),
        (NG_NOTIFS_CSV,   _migrate_ng_notifs),
        (ROOT_CAUSES_CSV, _migrate_rc),
    ]
    for path, fn in pairs:
        if path.exists():
            fn(path)
            path.rename(path.with_suffix(".csv.bak"))


def _migrate_reports(path: Path) -> None:
    rows = _read_csv_file(path, [
        "id","part","model","shift","tanggal","sent_by","status",
        "created_at","sent_at","confirmed_by","confirmed_at",
    ])
    if not rows:
        return
    with _conn() as con:
        con.executemany(
            "INSERT OR IGNORE INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(r["id"], r["part"], r["model"], r["shift"], r["tanggal"],
              r["sent_by"], r["status"], r["created_at"], r["sent_at"],
              r["confirmed_by"], r["confirmed_at"]) for r in rows],
        )


def _migrate_messages(path: Path) -> None:
    rows = _read_csv_file(path, [
        "id","report_id","from_user","to_role","created_at","is_read",
    ])
    if not rows:
        return
    with _conn() as con:
        con.executemany(
            "INSERT OR IGNORE INTO messages VALUES (?,?,?,?,?,?)",
            [(r["id"], r["report_id"], r["from_user"], r["to_role"],
              r["created_at"], r["is_read"]) for r in rows],
        )


def _migrate_ng_notifs(path: Path) -> None:
    rows = _read_csv_file(path, [
        "id","from_user","from_role","to_role","part","model","ref",
        "parameter","sampleno","date","shift","deviation","kp",
        "category","description","pic","status","report_id",
        "created_at","is_read",
    ])
    if not rows:
        return
    with _conn() as con:
        con.executemany(
            "INSERT OR IGNORE INTO ng_notifs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(r["id"], r["from_user"], r["from_role"], r["to_role"],
              r["part"], r["model"], r["ref"], r["parameter"], r["sampleno"],
              r["date"], r["shift"], r["deviation"], r["kp"], r["category"],
              r["description"], r["pic"], r["status"], r["report_id"],
              r["created_at"], r["is_read"]) for r in rows],
        )


def _migrate_rc(path: Path) -> None:
    rows = _read_csv_file(path, [
        "id","rc_key","date","shift","sampleno","part","model","ref",
        "id_ukur","parameter","deviation","category","description",
        "corrective_action","status","inputted_by","inputted_role",
        "pic","inputted_at","updated_at",
    ])
    if not rows:
        return
    with _conn() as con:
        con.executemany(
            "INSERT OR IGNORE INTO root_causes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(r["id"], r["rc_key"], r["date"], r["shift"], r["sampleno"],
              r["part"], r["model"], r["ref"], r["id_ukur"], r["parameter"],
              r["deviation"], r["category"], r["description"],
              r["corrective_action"], r["status"], r["inputted_by"],
              r["inputted_role"], r["pic"], r["inputted_at"],
              r["updated_at"]) for r in rows],
        )


# ═══════════════════════════════════════════════════════════════
#  MEASUREMENTS  (pengganti REALNEO.csv)
# ═══════════════════════════════════════════════════════════════

def measurements_count() -> int:
    """Jumlah baris di tabel measurements. Dipakai untuk cek apakah perlu import."""
    if not DB_PATH.exists():
        return 0
    with _conn() as con:
        row = con.execute("SELECT COUNT(*) FROM measurements").fetchone()
    return row[0] if row else 0


def import_csv_to_db(csv_path: str = "REALNEO.csv") -> int:
    """
    Import REALNEO.csv ke tabel measurements (replace).
    Dipanggil dari mainloca.py kalau tabel masih kosong.
    Return jumlah baris yang diimport, 0 kalau gagal.
    """
    path = Path(csv_path)
    if not path.exists():
        return 0

    df = pd.read_csv(path)
    for c in ["Nominal", "Uppertol", "Lowertol", "Actual", "Deviation"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        # if_exists='replace' → drop + recreate tabel measurements
        df.to_sql("measurements", con, if_exists="replace", index=False)
        # Recreate indexes setelah replace
        con.execute("CREATE INDEX IF NOT EXISTS idx_meas_date   ON measurements(Date)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_meas_part   ON measurements(PartName)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_meas_model  ON measurements(ModelName)")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_meas_unique ON measurements(Date, Cycle, PartName, ModelName, ref, ID, point, Parameter, Nominal, Uppertol)")
        con.commit()
        return len(df)
    except Exception:
        return 0
    finally:
        con.close()


def load_measurements() -> pd.DataFrame:
    """
    Baca seluruh tabel measurements → DataFrame.
    Menggantikan pd.read_csv('REALNEO.csv') di mainloca.py.
    """
    if not DB_PATH.exists():
        return pd.DataFrame()
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        df = pd.read_sql_query("SELECT * FROM measurements", con)
        if df.empty:
            return df
        df["Date"] = pd.to_datetime(df["Date"])
        for c in ["Nominal", "Uppertol", "Lowertol", "Actual", "Deviation"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df
    finally:
        con.close()


# ═══════════════════════════════════════════════════════════════
#  REPORTS
# ═══════════════════════════════════════════════════════════════

def save_report(report: dict, sent_by: str) -> str:
    init_db()
    rid = report.get("id") or str(uuid.uuid4())[:8]

    json_path = REPORTS_DIR / f"{rid}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    h = report.get("header", {})
    with _conn() as con:
        existing = con.execute(
            "SELECT status, created_at, sent_at, confirmed_by, confirmed_at FROM reports WHERE id=?",
            (rid,),
        ).fetchone()

        if existing:
            con.execute(
                "UPDATE reports SET part=?, model=?, shift=?, tanggal=?, sent_by=? WHERE id=?",
                (h.get("namaPart",""), h.get("modelName",""),
                 h.get("shift",""), h.get("tanggal",""), sent_by, rid),
            )
        else:
            con.execute(
                "INSERT INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (rid, h.get("namaPart",""), h.get("modelName",""),
                 h.get("shift",""), h.get("tanggal",""), sent_by,
                 "draft", _now(), "", "", ""),
            )
    return rid


def update_report_status(report_id: str, status: str) -> bool:
    init_db()
    with _conn() as con:
        exists = con.execute(
            "SELECT 1 FROM reports WHERE id=?", (report_id,)
        ).fetchone()
        if not exists:
            return False
        if status == "sent":
            con.execute(
                "UPDATE reports SET status=?, sent_at=? WHERE id=?",
                (status, _now(), report_id),
            )
        elif status == "draft":
            con.execute(
                "UPDATE reports SET status=?, sent_at='' WHERE id=?",
                (status, report_id),
            )
        else:
            con.execute(
                "UPDATE reports SET status=? WHERE id=?",
                (status, report_id),
            )
    return True


def confirm_report(report_id: str, confirmed_by: str) -> bool:
    init_db()
    with _conn() as con:
        con.execute(
            "UPDATE reports SET status='confirmed', confirmed_by=?, confirmed_at=? WHERE id=?",
            (confirmed_by, _now(), report_id),
        )
        con.execute(
            "UPDATE messages SET is_read='1' WHERE report_id=?",
            (report_id,),
        )
    return True


def load_report_data(report_id: str) -> dict | None:
    init_db()
    path = REPORTS_DIR / f"{report_id}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_reports(role: str, username: str) -> list[dict]:
    init_db()
    with _conn() as con:
        if role == "Measurement":
            rows = con.execute(
                "SELECT * FROM reports WHERE sent_by=? ORDER BY created_at DESC",
                (username,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM reports ORDER BY created_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_report_meta(report_id: str) -> dict | None:
    init_db()
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM reports WHERE id=?", (report_id,)
        ).fetchone()
    return dict(row) if row else None


def delete_report(report_id: str) -> None:
    init_db()
    with _conn() as con:
        con.execute("DELETE FROM reports WHERE id=?", (report_id,))
        con.execute("DELETE FROM messages WHERE report_id=?", (report_id,))
    json_path = REPORTS_DIR / f"{report_id}.json"
    if json_path.exists():
        json_path.unlink()


# ═══════════════════════════════════════════════════════════════
#  MESSAGES
# ═══════════════════════════════════════════════════════════════

def send_message(report_id: str, from_user: str, to_role: str) -> str:
    init_db()
    mid = str(uuid.uuid4())[:8]
    with _conn() as con:
        con.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?)",
            (mid, report_id, from_user, to_role, _now(), "0"),
        )
    return mid


def get_messages(role: str) -> list[dict]:
    """Ambil pesan inbox sesuai role, dengan info laporan digabung (LEFT JOIN)."""
    init_db()
    with _conn() as con:
        rows = con.execute("""
            SELECT m.*,
                   r.part        AS rpt_part,
                   r.model       AS rpt_model,
                   r.shift       AS rpt_shift,
                   r.tanggal     AS rpt_tanggal,
                   r.sent_by     AS rpt_sent_by,
                   r.status      AS rpt_status,
                   r.created_at  AS rpt_created_at,
                   r.confirmed_by AS rpt_confirmed_by,
                   r.confirmed_at AS rpt_confirmed_at
            FROM messages m
            LEFT JOIN reports r ON m.report_id = r.id
            WHERE m.to_role = ?
            ORDER BY m.created_at DESC
        """, (role,)).fetchall()
    return [dict(r) for r in rows]


def get_sent_messages(username: str) -> list[dict]:
    """Ambil pesan yang sudah dikirim oleh username ini (LEFT JOIN ke reports)."""
    init_db()
    with _conn() as con:
        rows = con.execute("""
            SELECT m.*,
                   r.part        AS rpt_part,
                   r.model       AS rpt_model,
                   r.shift       AS rpt_shift,
                   r.tanggal     AS rpt_tanggal,
                   r.sent_by     AS rpt_sent_by,
                   r.status      AS rpt_status,
                   r.created_at  AS rpt_created_at,
                   r.confirmed_by AS rpt_confirmed_by,
                   r.confirmed_at AS rpt_confirmed_at
            FROM messages m
            LEFT JOIN reports r ON m.report_id = r.id
            WHERE m.from_user = ?
            ORDER BY m.created_at DESC
        """, (username,)).fetchall()
    return [dict(r) for r in rows]


def mark_read(message_id: str) -> None:
    init_db()
    with _conn() as con:
        con.execute(
            "UPDATE messages SET is_read='1' WHERE id=?", (message_id,)
        )


def get_unread_count(role: str) -> int:
    init_db()
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM messages WHERE to_role=? AND is_read='0'",
            (role,),
        ).fetchone()
    return row[0] if row else 0


# ═══════════════════════════════════════════════════════════════
#  ROOT CAUSE
# ═══════════════════════════════════════════════════════════════

def _rc_key(date: str, shift: str, sampleno: str,
            part: str, model: str, ref: str, parameter: str) -> str:
    return f"{date}|{shift}|{sampleno}|{part}|{model}|{ref}|{parameter}"


def save_root_cause(data: dict) -> str:
    init_db()
    key = data.get("rc_key") or _rc_key(
        data.get("date",""), data.get("shift",""),
        data.get("sampleno",""), data.get("part",""),
        data.get("model",""), data.get("ref",""),
        data.get("parameter",""),
    )

    with _conn() as con:
        existing = con.execute(
            "SELECT id, inputted_at FROM root_causes WHERE rc_key=?", (key,)
        ).fetchone()

        rc_id       = existing["id"]         if existing else str(uuid.uuid4())[:8]
        inputted_at = existing["inputted_at"] if existing else _now()

        con.execute("""
            INSERT INTO root_causes
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(rc_key) DO UPDATE SET
                category          = excluded.category,
                description       = excluded.description,
                corrective_action = excluded.corrective_action,
                status            = excluded.status,
                inputted_by       = excluded.inputted_by,
                inputted_role     = excluded.inputted_role,
                pic               = excluded.pic,
                updated_at        = excluded.updated_at
        """, (rc_id, key,
              data.get("date",""), data.get("shift",""),
              data.get("sampleno",""), data.get("part",""),
              data.get("model",""), data.get("ref",""),
              data.get("id_ukur",""), data.get("parameter",""),
              data.get("deviation",""), data.get("category",""),
              data.get("description",""), data.get("corrective_action",""),
              data.get("status","Investigated"),
              data.get("inputted_by",""), data.get("inputted_role",""),
              data.get("pic",""), inputted_at, _now()))

    return rc_id


def get_root_causes(
    part: str = None, model: str = None, status: str = None,
) -> list[dict]:
    init_db()
    query  = "SELECT * FROM root_causes WHERE 1=1"
    params = []
    if part:
        query += " AND part=?";   params.append(part)
    if model:
        query += " AND model=?";  params.append(model)
    if status:
        query += " AND status=?"; params.append(status)
    query += " ORDER BY updated_at DESC"

    with _conn() as con:
        rows = con.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_root_cause_by_key(key: str) -> dict | None:
    init_db()
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM root_causes WHERE rc_key=?", (key,)
        ).fetchone()
    return dict(row) if row else None


def delete_root_cause(rc_id: str) -> None:
    init_db()
    with _conn() as con:
        con.execute("DELETE FROM root_causes WHERE id=?", (rc_id,))


def get_rc_stats() -> dict:
    init_db()
    with _conn() as con:
        rows = con.execute(
            "SELECT category, ref, shift FROM root_causes WHERE category != ''"
        ).fetchall()

    cat_counts: dict = {}
    ref_cat:    dict = {}
    shift_cat:  dict = {}

    for r in rows:
        cat   = r["category"] or "Lainnya"
        ref   = r["ref"]      or "—"
        shift = r["shift"]    or "—"

        cat_counts[cat] = cat_counts.get(cat, 0) + 1

        ref_cat.setdefault(ref, {})
        ref_cat[ref][cat] = ref_cat[ref].get(cat, 0) + 1

        shift_cat.setdefault(shift, {})
        shift_cat[shift][cat] = shift_cat[shift].get(cat, 0) + 1

    return {
        "category_counts": cat_counts,
        "ref_category":    ref_cat,
        "shift_category":  shift_cat,
    }


# ═══════════════════════════════════════════════════════════════
#  NG NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════

def send_ng_notif(data: dict) -> str:
    init_db()
    nid = str(uuid.uuid4())[:8]
    with _conn() as con:
        con.execute(
            "INSERT INTO ng_notifs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (nid,
             data.get("from_user",""), data.get("from_role",""),
             data.get("to_role","Produksi"),
             data.get("part",""),  data.get("model",""),
             data.get("ref",""),   data.get("parameter",""),
             data.get("sampleno",""),
             data.get("date",""),  data.get("shift",""),
             data.get("deviation",""), data.get("kp","0"),
             data.get("category",""), data.get("description",""),
             data.get("pic",""),   data.get("status","Open"),
             data.get("report_id",""), _now(), "0"),
        )
    return nid


def get_ng_notifs(to_role: str = "Produksi") -> list:
    init_db()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM ng_notifs WHERE to_role=? ORDER BY created_at DESC",
            (to_role,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_ng_notifs_sent(from_user: str) -> list:
    init_db()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM ng_notifs WHERE from_user=? ORDER BY created_at DESC",
            (from_user,),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_ng_notif_read(notif_id: str) -> None:
    init_db()
    with _conn() as con:
        con.execute(
            "UPDATE ng_notifs SET is_read='1' WHERE id=?", (notif_id,)
        )


def get_unread_ng_count(to_role: str = "Produksi") -> int:
    init_db()
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM ng_notifs WHERE to_role=? AND is_read='0'",
            (to_role,),
        ).fetchone()
    return row[0] if row else 0