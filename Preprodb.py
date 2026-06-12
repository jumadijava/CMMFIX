import pandas as pd
import os
import re
import time
import logging
import json
import shutil
import sqlite3
from pathlib import Path
from threading import Thread
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ==========================================
# 1. SETTINGS & LOGGING
# ==========================================

HEADER_COLUMNS = [
    'Date', 'Shift', 'Cycle', 'SampleNo', 'PartName', 'ModelName', 'CMMName',
    'ref', 'ID', 'point', 'Parameter', 'Nominal', 'Uppertol',
    'Lowertol', 'Actual', 'Deviation', 'Judgement', 'KP', 'Category'
]

# ── Path SQLite ────────────────────────────────────────────────────
DB_PATH = r"D:/CMM QUALITY DASHBOARD NEO NOIR/data/cmm.db"

# ── Folder lokal (Central PC) ──────────────────────────────────────
LOCAL_RAW         = "RAW/raw"
LOCAL_PROCESSED   = "RAW/raw_processed"
LOCAL_UNPROCESSED = "RAW/raw_unprocessed"
LOCAL_UNMATCHED   = "RAW/raw_unmatched"
CSV_PROCESSED     = "RAW/csv_processed"

# ── Network share + CMM config ─────────────────────────────────────
# Ganti PC-NAME sesuai hostname aktual masing-masing PC CMM
WATCH_FOLDERS = [
    {"path": r"D:/MESIN CMM/MTY-7106",   "pc_name": "MTY-7106-PC",   "cmm_name": "Mitutoyo 7106"},
    {"path": r"D:/MESIN CMM/MTY-776",    "pc_name": "MTY-776-PC",    "cmm_name": "Mitutoyo 776"},
    {"path": r"D:/MESIN CMM/CONTURA-G2", "pc_name": "CONTURA-G2-PC", "cmm_name": "Zeiss Contura G2"},
    {"path": r"D:/MESIN CMM/CONTURA-G3", "pc_name": "CONTURA-G3-PC", "cmm_name": "Zeiss Contura G3"},
]

# Lookup pc_name → cmm_name (dipakai di _do_process)
PC_CMM_MAP = {e["pc_name"]: e["cmm_name"] for e in WATCH_FOLDERS}

# Interval sync dari network share (detik)
SYNC_INTERVAL = 60

try:
    import colorama
    colorama.init()
    _COLOR_OK = True
except ImportError:
    _COLOR_OK = False


class _ColorFormatter(logging.Formatter):
    """
    Formatter dengan warna ANSI untuk terminal:
    - Hijau  : pesan sukses (Selesai, Copied, DB insert)
    - Kuning : skip / belum lengkap / overflow / no match
    - Merah  : ERROR
    - Abu    : pesan netral (banner, separator, dll)
    """
    RESET  = "\033[0m"
    GREEN  = "\033[32m"
    YELLOW = "\033[33m"
    RED    = "\033[31m"
    GRAY   = "\033[90m"
    CYAN   = "\033[36m"

    SUCCESS_KEYWORDS = ("Selesai", "Copied", "diinsert", "Pipeline Started", "Monitoring")
    SKIP_KEYWORDS    = ("Belum lengkap", "Overflow", "No match", "Kosong", "Leftover")

    def format(self, record):
        msg = super().format(record)
        if not _COLOR_OK:
            return msg

        if record.levelno >= logging.ERROR:
            color = self.RED
        elif record.levelno >= logging.WARNING:
            color = self.YELLOW
        elif any(k in record.getMessage() for k in self.SUCCESS_KEYWORDS):
            color = self.GREEN
        elif any(k in record.getMessage() for k in self.SKIP_KEYWORDS):
            color = self.YELLOW
        elif record.getMessage().startswith(("=", "─")):
            color = self.CYAN
        else:
            color = self.GRAY

        return f"{color}{msg}{self.RESET}"


_file_handler = logging.FileHandler("pipeline_execution.log", encoding="utf-8")
_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_ColorFormatter('%(asctime)s - %(levelname)s - %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    handlers=[_file_handler, _console_handler],
)

# Fix encoding terminal Windows (cp1252) — hindari UnicodeEncodeError untuk
# karakter non-ASCII seperti '→', '✓', '⚠', dll.
import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
for _h in logging.getLogger().handlers:
    if hasattr(_h, "stream") and hasattr(_h.stream, "reconfigure"):
        try:
            _h.stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# Lebar prefix [PC_NAME] disamakan biar log rapi/align
_PC_NAME_WIDTH = max(len(e["pc_name"]) for e in WATCH_FOLDERS)

def _tag(pc_name: str) -> str:
    """Prefix log [PC_NAME] dengan lebar tetap supaya kolom align."""
    return f"[{pc_name:<{_PC_NAME_WIDTH}}]"


# ==========================================
# 2. UTILS
# ==========================================

def safe_float(val, default=0.0):
    try: return float(val)
    except: return default

def wait_for_file(filepath, timeout=30):
    start = time.time()
    while True:
        try:
            os.rename(filepath, filepath)
            return True
        except OSError:
            if time.time() - start > timeout: return False
            time.sleep(1)

MODEL_ALIASES = {
    "K2V":  "K60",
    "K2VJ": "K60",
    "K2S":  "K2SA",
    "K2F":  "K1AL",
    "KOR":  "K2SA"
}

# Keyword yang dikenal, diurutkan panjang descending agar split lebih akurat
KNOWN_KEYWORDS = sorted([
    "MISSION", "ROUGH", "CRCS", "COMP",
    "K2SA", "K1AL", "K60",
    "NT", "CAM", "GV", "HWP", "BD",
    "L1", "L2", "L3", "L", "R"
], key=len, reverse=True)

DIGIT_ALIASES = {'1': 'L1', '2': 'L2', '3': 'L3'}

def split_joined_token(token):
    """Pecah token gabung seperti 'NTK2SA' → ['NT', 'K2SA'].
    Digit tunggal hasil split dari keyword (misal K1AL3→K1AL+3) dikonversi ke L1/L2/L3.
    Digit standalone dari nama file TIDAK dikonversi."""
    results = []
    remaining = token
    found_keyword = False
    while remaining:
        matched = False
        for kw in KNOWN_KEYWORDS:
            if remaining.startswith(kw):
                results.append(kw)
                remaining = remaining[len(kw):]
                matched = True
                found_keyword = True
                break
        if not matched:
            if found_keyword:
                remaining = DIGIT_ALIASES.get(remaining, remaining)
            results.append(remaining)
            break
    return results

def tokenize(filename):
    """Split filename by separators, pecah token gabung, normalisasi alias."""
    name = os.path.splitext(filename)[0]
    raw_tokens = re.split(r'[\s_\-]+', name)
    tokens = set()
    for t in raw_tokens:
        t = t.upper()
        if not t:
            continue
        parts = split_joined_token(t)
        for p in parts:
            tokens.add(MODEL_ALIASES.get(p, p))
    return tokens

def find_job_by_keyword(file_name, config):
    """Match job berdasarkan keyword. Semua keyword harus ada di filename.
    Job dengan keyword terbanyak yang match menang (lebih spesifik = prioritas lebih tinggi)."""
    file_tokens = tokenize(file_name)
    best_job, best_score = None, 0
    for job in config:
        keywords = job.get('keywords', [])
        if not keywords:
            continue
        kw_tokens = set(MODEL_ALIASES.get(k.upper(), k.upper()) for k in keywords)
        if not kw_tokens.issubset(file_tokens):
            continue
        score = len(kw_tokens)
        if score > best_score:
            best_score = score
            best_job = job
    return best_job

def find_job_by_planid(file_path, file_name, config):
    """Fallback: baca planid dari file Zeiss, match ke config.
    Untuk planid yang ambiguous (L2/L3), cek keyword L1/L2/L3 di filename."""
    try:
        for enc in ('utf-8', 'cp1252', 'latin-1'):
            try:
                df = pd.read_csv(file_path, sep='\t', encoding=enc, nrows=1)
                break
            except UnicodeDecodeError:
                continue
        else:
            return None
        if 'planid' not in df.columns:
            return None
        planid = str(df['planid'].iloc[0]).strip()
    except Exception:
        return None

    candidates = [j for j in config if j.get('type') == 'Zeiss' and j.get('planid') == planid]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    # Ambiguous (misal L2 vs L3) — cek token L1/L2/L3 di filename
    file_tokens = tokenize(file_name)
    for variant in ('L1', 'L2', 'L3'):
        if variant in file_tokens:
            for job in candidates:
                if any(k.upper() == variant for k in job.get('keywords', [])):
                    return job
    return None

def find_job_mitutoyo_k1al(file_path, file_name, config):
    """Auto-detect K1AL L1/L3 untuk Mitutoyo tanpa keyword L1/L2/L3.
    Rules:
    - >= 5 siklus → L1 (CRCS L atau R)
    - shift 3 + 2 siklus → L3 CRCS L
    - shift 3 + 4 siklus → L3 CRCS R
    - shift 1/2 + 2/4 siklus → ambiguous, return None
    """
    tokens = tokenize(file_name)

    is_crcs_l = {'CRCS', 'L', 'K1AL'}.issubset(tokens)
    is_crcs_r = {'CRCS', 'R', 'K1AL'}.issubset(tokens)
    if not is_crcs_l and not is_crcs_r:
        return None

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            raw = f.read()
        cycle_count = raw.count('**@101')
    except Exception:
        return None

    dt = datetime.fromtimestamp(os.path.getmtime(file_path))
    shift = "1" if 7 <= dt.hour < 16 else "2" if 16 <= dt.hour <= 23 else "3"

    if cycle_count >= 5:
        variant = 'L1'
    elif shift == '3' and cycle_count == 2 and is_crcs_l:
        variant = 'L3'
    elif shift == '3' and cycle_count == 4 and is_crcs_r:
        variant = 'L3'
    else:
        logging.warning(f"Mitutoyo K1AL ambiguous (shift {shift}, {cycle_count} siklus): {file_name}")
        return None

    part = 'CRCS L' if is_crcs_l else 'CRCS R'
    model = f'K1AL {variant}'
    for job in config:
        if job.get('type') == 'Mitutoyo' and job.get('part') == part and job.get('model') == model:
            logging.debug(f"Job matched via K1AL auto-detect ({variant}, shift {shift}): {file_name}")
            return job
    return None

def find_job(file_name, file_path, config):
    """Cari job matching: keyword → planid (Zeiss) → K1AL auto-detect (Mitutoyo)."""
    job = find_job_by_keyword(file_name, config)
    if job:
        return job
    ext = os.path.splitext(file_name)[1].lower()
    if ext == '.txt':
        job = find_job_by_planid(file_path, file_name, config)
        if job:
            logging.debug(f"Job matched via planid fallback: {file_name}")
    elif ext == '.asc':
        job = find_job_mitutoyo_k1al(file_path, file_name, config)
    return job


# ==========================================
# 2b. FILE VALIDATION
# ==========================================

def get_expected_cycles(job, shift):
    """Hitung expected siklus per shift, handle shift_offset untuk K1AL L1."""
    sample_map   = job.get('sample_map', {})
    shift_offset = job.get('shift_offset')
    total        = len(sample_map)
    if not shift_offset:
        return total
    offsets = sorted(shift_offset.items(), key=lambda x: int(x[0]))
    for i, (s, off) in enumerate(offsets):
        if str(s) == str(shift):
            next_off = int(offsets[i+1][1]) if i+1 < len(offsets) else total
            return next_off - int(off)
    return total

def check_file(file_path, job, shift="1"):
    """Cek status file: 'ok', 'incomplete', 'overflow'."""
    expected = get_expected_cycles(job, shift)
    if expected == 0:
        return 'ok'

    if job['type'] == 'Mitutoyo':
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            raw = f.read()
        count = raw.count('**@101')
        if count < expected:
            logging.warning(f"File incomplete (Mitutoyo): {os.path.basename(file_path)} ({count}/{expected} siklus shift {shift})")
            return 'incomplete'
        if count > expected:
            logging.warning(f"File overflow (Mitutoyo): {os.path.basename(file_path)} ({count}/{expected} siklus shift {shift})")
            return 'overflow'
        return 'ok'

    elif job['type'] == 'Zeiss':
        for enc in ('utf-8', 'cp1252', 'shift_jis', 'latin-1'):
            try:
                df = pd.read_csv(file_path, sep='\t', encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return 'incomplete'
        actual_count = df['partnb'].dropna().nunique()
        if actual_count == 0:
            logging.warning(f"File kosong/tidak ada data: {os.path.basename(file_path)}")
            return 'incomplete'
        if actual_count < expected:
            logging.warning(f"File incomplete (Zeiss): {os.path.basename(file_path)} ({actual_count}/{expected} partnb shift {shift})")
            return 'incomplete'
        if actual_count > expected:
            logging.warning(f"File overflow (Zeiss): {os.path.basename(file_path)} ({actual_count}/{expected} partnb shift {shift})")
            return 'overflow'
        return 'ok'

    return 'ok'


# ==========================================
# 3. PARSING UTILS
# ==========================================

def load_mapping_dict(mapping_file, use_parameter=False):
    if not os.path.exists(mapping_file):
        logging.warning(f"Mapping file tidak ditemukan: {mapping_file}")
        return {}
    if os.path.getsize(mapping_file) == 0:
        logging.warning(f"Mapping file kosong (0 bytes): {mapping_file}")
        return {}
    try:
        for enc in ('utf-8', 'cp1252', 'latin-1', 'utf-8-sig'):
            try:
                df_map = pd.read_csv(mapping_file, encoding=enc).dropna(how='all')
                break
            except UnicodeDecodeError:
                continue
        else:
            logging.error(f"Gagal baca mapping {mapping_file}: tidak ada encoding yang cocok")
            return {}
    except Exception as e:
        logging.error(f"Gagal baca mapping {mapping_file}: {e}")
        return {}

    df_map.columns = [c.strip() for c in df_map.columns]
    mapping_dict = {}

    for _, row in df_map.iterrows():
        f_id = str(row['ID']).strip() if pd.notnull(row['ID']) else ""
        m_data = {
            'NO': row.get('NO', '-'),
            'POINT_PEMERIKSAAN': row.get('POINT_PEMERIKSAAN', '-'),
            'NOM_NEW': row.get('Newnom') if pd.notnull(row.get('Newnom')) else row.get('Nom'),
            'UP_NEW': row.get('Uppertol'),
            'LOW_NEW': row.get('Lowertol'),
            'KP': int(row['KP']) if pd.notnull(row.get('KP')) else 0
        }

        if use_parameter and 'PARAMETER' in df_map.columns:
            param = re.sub(r'\s+\d+$', '', str(row['PARAMETER']).strip())
            try: nom_key = str(float(row['NOMINAL'])) if pd.notnull(row.get('NOMINAL')) else ""
            except: nom_key = str(row.get('NOMINAL', "")).strip()
            key = (f_id, param, nom_key)
        else:
            key = f_id
            try: nom_key = str(float(row['NOMINAL'])) if pd.notnull(row.get('NOMINAL')) else ""
            except: nom_key = ""
            if nom_key:
                key2 = (f_id, nom_key)
                if key2 not in mapping_dict:
                    mapping_dict[key2] = []
                mapping_dict[key2].append(m_data)

        if key not in mapping_dict:
            mapping_dict[key] = []
        mapping_dict[key].append(m_data)

    return mapping_dict

def get_sample_no(cycle, sample_map, shift="1", shift_offset=None):
    try:
        c = int(cycle)
    except:
        return str(cycle)
    if shift_offset:
        c = c + int(shift_offset.get(str(shift), 0))
    return sample_map.get(str(c), str(c))

def hms_to_decimal(hms_str):
    """Konversi 'HH:MM:SS' atau '-HH:MM:SS' ke derajat desimal."""
    hms_str = hms_str.strip()
    negative = hms_str.startswith('-')
    parts = hms_str.lstrip('-').split(':')
    try:
        h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
        val = h + m / 60 + s / 3600
        return round(-val if negative else val, 3)
    except:
        return 0.0

def is_hms_format(text):
    """Cek apakah string mengandung format HH:MM:SS."""
    return bool(re.search(r'\d+:\d{2}:\d{2}', text))

def build_rows(matches, file_date, shift, current_cycle, sample_no, job,
               cmm_name, current_id, param_desc,
               final_nom, final_up, final_low, actual, dev):
    """Loop semua entri mapping dan return list of rows."""
    rows = []
    for m in matches:
        p_pemeriksaan = m.get('POINT_PEMERIKSAAN', '-')
        f_nom  = m.get('NOM_NEW') if pd.notnull(m.get('NOM_NEW')) else final_nom
        f_up   = m.get('UP_NEW')  if pd.notnull(m.get('UP_NEW'))  else final_up
        f_low  = m.get('LOW_NEW') if pd.notnull(m.get('LOW_NEW')) else final_low
        kp_val = m.get('KP', 0)

        judgement = "OK"
        if safe_float(dev) > safe_float(f_up) or safe_float(dev) < safe_float(f_low):
            judgement = "NG"

        rows.append([
            file_date, shift, current_cycle, sample_no,
            job['part'], job['model'], cmm_name,
            m.get('NO', '-'), current_id, p_pemeriksaan, param_desc,
            abs(safe_float(f_nom)), f_up, f_low,
            round(abs(safe_float(actual)), 2), round(safe_float(dev), 2), judgement, kp_val,
            "Produksi" if p_pemeriksaan != "-" else "QIS"
        ])
    return rows


# ==========================================
# 3b. ENGINES
# ==========================================

def run_mitutoyo(input_path, job, cmm_name="Mitutoyo"):
    mapping_dict = load_mapping_dict(job['map'], use_parameter=True)
    file_stats = os.stat(input_path)
    dt_modified = datetime.fromtimestamp(file_stats.st_mtime)
    file_date = dt_modified.strftime('%Y-%m-%d %H:%M:%S')
    shift = "1" if 7 <= dt_modified.hour < 16 else "2" if 16 <= dt_modified.hour <= 23 else "3"

    with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    results = []
    current_cycle, current_id = 1, "-"
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip(): i += 1; continue
        if '**@101' in line: current_cycle += 1; i += 1; continue

        clean_line = re.sub(r'[\-\+\*<>]{5,}.*$', '', line).strip()
        id_match = re.match(r'^\d+\s+([A-Z]\d+)\s+(.*)$', clean_line)
        if id_match:
            current_id = id_match.group(1).strip()
            rest_text = id_match.group(2).strip()
        else:
            rest_text = clean_line

        sub_match = re.match(r'^([XYZ])\s+(.*)$', rest_text)
        if sub_match:
            param_desc, data_text = sub_match.group(1), sub_match.group(2)
        else:
            f_match = re.search(r'-?\d+\.\d+', rest_text)
            if f_match:
                param_desc, data_text = rest_text[:f_match.start()].strip(), rest_text[f_match.start():]
            else:
                param_desc, data_text = rest_text.strip(), lines[i+1].strip() if i+1 < len(lines) else ""

        combined_text = rest_text + " " + data_text

        # --- PENANGANAN FORMAT ANGLE (HH:MM:SS) ---
        if is_hms_format(combined_text):
            all_hms = re.findall(r'-?\d+:\d{2}:\d{2}', combined_text)
            if len(all_hms) >= 3:
                hms_start = re.search(r'-?\d+:\d{2}:\d{2}', rest_text)
                param_desc = rest_text[:hms_start.start()].strip() if hms_start else param_desc

                nom_raw = str(hms_to_decimal(all_hms[0]))
                up_raw  = str(hms_to_decimal(all_hms[1]))
                actual  = str(hms_to_decimal(all_hms[2]))
                dev     = str(hms_to_decimal(all_hms[3])) if len(all_hms) >= 4 else "0.0"
                low_raw = str(round(-hms_to_decimal(all_hms[1]), 3))

                if param_desc and current_id != "-":
                    param_norm = re.sub(r'\s+\d+$', '', param_desc).strip()
                    try: nom_key = str(float(nom_raw))
                    except: nom_key = str(nom_raw).strip()
                    matches = (mapping_dict.get((current_id, param_norm, nom_key))
                               or mapping_dict.get((current_id, param_norm, ""))
                               or [{'NO': '-', 'POINT_PEMERIKSAAN': '-', 'NOM_NEW': None,
                                    'UP_NEW': None, 'LOW_NEW': None, 'KP': 0}])
                    sample_no = get_sample_no(current_cycle, job.get('sample_map', {}),
                                              shift, job.get('shift_offset'))
                    results += build_rows(matches, file_date, shift, current_cycle,
                                          sample_no, job, cmm_name, current_id, param_desc,
                                          nom_raw, up_raw, low_raw, actual, dev)
            i += 1
            continue
        # --- END PENANGANAN ANGLE ---

        nums = re.findall(r'-?\d+\.\d+', data_text)
        if len(nums) >= 2:
            nom_raw, up_raw, low_raw, actual, dev = "0.000", "0.000", "0.000", "0.000", "0.000"
            if any(x in param_desc.lower() for x in ['flatness', 'rectang', 'concentr']):
                if len(nums) >= 4:
                    nom_raw, up_raw, actual, dev = "0.000", nums[1], nums[3], nums[3]
                else:
                    nom_raw, up_raw, actual, dev = "0.000", nums[0], nums[1], nums[1]
            elif len(nums) >= 4:
                nom_raw, up_raw, actual, dev = nums[0], nums[1], nums[2], nums[3]
                if i+1 < len(lines) and lines[i+1].strip().startswith('-'):
                    low_nums = re.findall(r'-?\d+\.\d+', lines[i+1])
                    if low_nums: low_raw = low_nums[0]

            if param_desc and current_id != "-":
                param_norm = re.sub(r'\s+\d+$', '', param_desc).strip()
                try: nom_key = str(float(nom_raw))
                except: nom_key = str(nom_raw).strip()
                matches = (mapping_dict.get((current_id, param_norm, nom_key))
                           or mapping_dict.get((current_id, param_norm, ""))
                           or [{'NO': '-', 'POINT_PEMERIKSAAN': '-', 'NOM_NEW': None,
                                'UP_NEW': None, 'LOW_NEW': None, 'KP': 0}])
                sample_no = get_sample_no(current_cycle, job.get('sample_map', {}),
                                          shift, job.get('shift_offset'))
                results += build_rows(matches, file_date, shift, current_cycle,
                                      sample_no, job, cmm_name, current_id, param_desc,
                                      nom_raw, up_raw, low_raw, actual, dev)
        i += 1
    return results


def run_zeiss(input_path, job, cmm_name="Zeiss"):
    mapping_dict = load_mapping_dict(job['map'], use_parameter=False)
    file_stats = os.stat(input_path)
    dt_modified = datetime.fromtimestamp(file_stats.st_mtime)
    file_date = dt_modified.strftime('%Y-%m-%d %H:%M:%S')
    shift = "1" if 7 <= dt_modified.hour < 16 else "2" if 16 <= dt_modified.hour <= 23 else "3"

    for enc in ('utf-8', 'cp1252', 'shift_jis', 'latin-1'):
        try:
            df_raw = pd.read_csv(input_path, sep='\t', encoding=enc)
            logging.debug(f"File dibaca dengan encoding: {enc}")
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"Tidak bisa baca file dengan encoding apapun: {input_path}")

    # Reindex partnb berdasarkan urutan kemunculan (bukan nilai asli), skip NaN
    partnb_order = {}
    for pb in df_raw['partnb'].dropna():
        if pb not in partnb_order:
            partnb_order[pb] = len(partnb_order) + 1

    results = []
    for _, row in df_raw.iterrows():
        pb = row.get('partnb')
        if pb not in partnb_order:
            continue
        f_id = str(row['id']).strip()
        dev    = row.get('deviation', 0)
        nom    = row.get('nominal', 0)
        up     = row.get('uppertol', 0)
        low    = row.get('lowertol', 0)
        actual = row['actual']
        current_cycle = partnb_order[pb]
        sample_no = get_sample_no(current_cycle, job.get('sample_map', {}),
                                   shift, job.get('shift_offset'))

        matches = (mapping_dict.get(f_id)
                   or [{'NO': '-', 'POINT_PEMERIKSAAN': '-', 'NOM_NEW': None,
                        'UP_NEW': None, 'LOW_NEW': None, 'KP': 0}])

        results += build_rows(matches, file_date, shift, current_cycle,
                               sample_no, job, cmm_name, f_id, row['type'],
                               nom, up, low, actual, dev)
    return results


# ==========================================
# 3c. DATABASE INSERT
# ==========================================

def insert_to_db(rows: list) -> None:
    """
    INSERT hasil parse ke tabel measurements di SQLite.
    Raise RuntimeError kalau gagal — supaya _do_process tidak
    memindahkan file ke archive saat data belum masuk DB.
    """
    if not rows:
        return
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    try:
        placeholders = ",".join(["?"] * len(HEADER_COLUMNS))
        cur = con.cursor()
        cur.executemany(
            f"INSERT OR IGNORE INTO measurements ({','.join(HEADER_COLUMNS)}) VALUES ({placeholders})",
            rows,
        )
        con.commit()
        skipped = len(rows) - cur.rowcount
        logging.info(f"DB     : {cur.rowcount}/{len(rows)} baris diinsert ({skipped} duplikat di-skip)")
    except Exception as e:
        con.rollback()
        raise RuntimeError(f"Gagal insert ke DB: {e}") from e
    finally:
        con.close()


# ==========================================
# 4. SYNC & WATCHDOG
# ==========================================

_processing = set()


def _load_config():
    try:
        with open('Mapping/config_model.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Gagal baca config_model.json: {e}")
        return None


def sync_from_shares():
    """
    Thread yang berjalan setiap SYNC_INTERVAL detik.
    Scan semua network share → cek kelengkapan file di source →
    copy2 (preserve mtime) ke raw\\PC-NAME\\ kalau sudah ok.
    File incomplete dibiarkan di source, akan di-retry next interval.
    """
    logging.info("--- Sync thread started ---")
    while True:
        config = _load_config()
        cycle_started = False  # separator hanya dicetak kalau ada aktivitas

        if config:
            for entry in WATCH_FOLDERS:
                src_folder = entry["path"]
                pc_name    = entry["pc_name"]
                dst_folder = os.path.join(LOCAL_RAW, pc_name)
                os.makedirs(dst_folder, exist_ok=True)

                try:
                    files = os.listdir(src_folder)
                except Exception as e:
                    if not cycle_started:
                        logging.info("─" * 60)
                        cycle_started = True
                    logging.warning(f"{_tag(pc_name)} Tidak bisa akses {src_folder}: {e}")
                    continue

                for fname in files:
                    src_path = os.path.join(src_folder, fname)
                    dst_path = os.path.join(dst_folder, fname)

                    if not os.path.isfile(src_path):
                        continue

                    # Skip kalau sudah ada di local (sedang diproses atau retry)
                    if os.path.exists(dst_path):
                        continue

                    job = find_job(fname, src_path, config)
                    if not job:
                        if not cycle_started:
                            logging.info("─" * 60)
                            cycle_started = True
                        logging.warning(f"{_tag(pc_name)} No match : {fname}")
                        continue

                    # Hitung shift dari mtime file di source
                    dt_src = datetime.fromtimestamp(os.path.getmtime(src_path))
                    shift  = "1" if 7 <= dt_src.hour < 16 else "2" if 16 <= dt_src.hour <= 23 else "3"

                    status = check_file(src_path, job, shift)
                    if status == 'incomplete':
                        if not cycle_started:
                            logging.info("─" * 60)
                            cycle_started = True
                        logging.info(f"{_tag(pc_name)} Belum lengkap, ditunggu: {fname}")
                        continue
                    if status == 'overflow':
                        if not cycle_started:
                            logging.info("─" * 60)
                            cycle_started = True
                        logging.warning(f"{_tag(pc_name)} Overflow  : {fname} (di source, skip)")
                        continue

                    if not cycle_started:
                        logging.info("─" * 60)
                        cycle_started = True
                    try:
                        shutil.copy2(src_path, dst_path)
                        logging.info(f"{_tag(pc_name)} Copied  : {fname}")
                    except Exception as e:
                        logging.error(f"{_tag(pc_name)} Gagal copy {fname}: {e}")

        time.sleep(SYNC_INTERVAL)


class CMMHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory: return
        Thread(target=self._process, args=(event.src_path,), daemon=True).start()

    def on_moved(self, event):
        if event.is_directory: return
        Thread(target=self._process, args=(event.dest_path,), daemon=True).start()

    def _process(self, file_path):
        if file_path in _processing:
            return
        _processing.add(file_path)
        try:
            self._do_process(file_path, os.path.basename(file_path))
        finally:
            _processing.discard(file_path)

    def _do_process(self, file_path, file_name):
        time.sleep(0.5)
        if not wait_for_file(file_path):
            logging.warning(f"File terkunci terlalu lama, skip: {file_name}")
            return

        # Derive pc_name dari subfolder → lookup cmm_name
        pc_name  = Path(file_path).parent.name
        cmm_name = PC_CMM_MAP.get(pc_name, pc_name)

        config = _load_config()
        if not config:
            return

        job = find_job(file_name, file_path, config)
        if not job:
            logging.warning(f"{_tag(pc_name)} No match : {file_name} (local)")
            unmatched_dir = os.path.join(LOCAL_UNMATCHED, pc_name)
            os.makedirs(unmatched_dir, exist_ok=True)
            shutil.move(file_path, os.path.join(unmatched_dir, file_name))
            logging.info(f"{_tag(pc_name)}  -> raw_unmatched/{pc_name}/{file_name}")
            return

        if not os.path.exists(job['map']):
            logging.error(f"Mapping file tidak ditemukan: {job['map']}")
            return
        if os.path.getsize(job['map']) == 0:
            logging.error(f"Mapping file kosong: {job['map']}")
            return

        dt_file = datetime.fromtimestamp(os.path.getmtime(file_path))
        shift   = "1" if 7 <= dt_file.hour < 16 else "2" if 16 <= dt_file.hour <= 23 else "3"
        shift_folder = f"Shift-{shift}"

        # Cek ulang status (jaga-jaga file korup saat transit copy)
        status = check_file(file_path, job, shift)
        if status == 'overflow':
            unprocessed_dir = os.path.join(LOCAL_UNPROCESSED, pc_name)
            os.makedirs(unprocessed_dir, exist_ok=True)
            shutil.move(file_path, os.path.join(unprocessed_dir, file_name))
            logging.warning(f"{_tag(pc_name)} Overflow  : {file_name} (local) -> raw_unprocessed/{pc_name}/{file_name}")
            return
        if status == 'incomplete':
            # Tidak seharusnya terjadi (sync thread sudah filter), log saja
            logging.warning(f"{_tag(pc_name)} Belum lengkap (unexpected, local): {file_name}")
            return

        try:
            if job['type'] == 'Zeiss':
                data = run_zeiss(file_path, job, cmm_name)
            else:
                data = run_mitutoyo(file_path, job, cmm_name)

            if data:
                raw_date_str = data[0][0]
                dt_obj       = datetime.strptime(raw_date_str, '%Y-%m-%d %H:%M:%S')
                folder_date  = dt_obj.strftime("%Y-%m-%d")

                # Insert ke DB
                insert_to_db(data)

                # Simpan CSV arsip
                csv_dir = os.path.join(CSV_PROCESSED, pc_name, folder_date, shift_folder)
                os.makedirs(csv_dir, exist_ok=True)
                csv_name = os.path.splitext(file_name)[0] + ".csv"
                pd.DataFrame(data, columns=HEADER_COLUMNS).to_csv(
                    os.path.join(csv_dir, csv_name), index=False
                )

                # Archive file raw
                archive_dir = os.path.join(LOCAL_PROCESSED, pc_name, folder_date, shift_folder)
                os.makedirs(archive_dir, exist_ok=True)
                shutil.move(file_path, os.path.join(archive_dir, file_name))

                logging.info(f"{_tag(pc_name)} Selesai : {file_name}  ->  {folder_date}/{shift_folder}")
            else:
                logging.warning(f"{_tag(pc_name)} Kosong  : {file_name} (tidak ada data hasil parse)")

        except Exception as e:
            logging.error(f"{_tag(pc_name)} ERROR   : {file_name} -> {e}", exc_info=True)


# ==========================================
# 5. MAIN
# ==========================================

if __name__ == "__main__":
    logging.info("=" * 60)
    logging.info("  CMM PREPRODB - Pipeline Started")
    logging.info(f"  DB target   : {DB_PATH}")
    logging.info(f"  Sync setiap : {SYNC_INTERVAL}s")
    for entry in WATCH_FOLDERS:
        logging.info(f"  {_tag(entry['pc_name'])} {entry['cmm_name']:<18} <- {entry['path']}")
    logging.info("=" * 60)

    # Buat semua subfolder lokal
    for entry in WATCH_FOLDERS:
        os.makedirs(os.path.join(LOCAL_RAW, entry["pc_name"]), exist_ok=True)

    # Startup scan — proses file leftover di raw\PC-NAME\ (dari sesi sebelumnya)
    handler = CMMHandler()
    startup_found = False
    for entry in WATCH_FOLDERS:
        local_folder = os.path.join(LOCAL_RAW, entry["pc_name"])
        for fname in os.listdir(local_folder):
            fpath = os.path.join(local_folder, fname)
            if os.path.isfile(fpath):
                if not startup_found:
                    logging.info("─" * 60)
                    logging.info("Startup scan: file leftover ditemukan, diproses ulang")
                    startup_found = True
                logging.info(f"{_tag(entry['pc_name'])} Leftover: {fname}")
                Thread(target=handler._process, args=(fpath,), daemon=True).start()

    # Sync thread — copy dari network share setiap SYNC_INTERVAL detik
    Thread(target=sync_from_shares, daemon=True).start()

    # Single watchdog pada raw/ lokal (recursive mencakup semua subfolder PC)
    observer = Observer()
    observer.schedule(handler, LOCAL_RAW, recursive=True)
    observer.start()
    logging.info(f"Monitoring {LOCAL_RAW}/ (recursive) ...")
    logging.info("─" * 60)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()