"""
settings_config.py
──────────────────
Helper baca/tulis data/settings.json.
Semua page import dari sini — tidak hardcode nilai di masing-masing file.

Struktur settings.json:
{
  "target_ok_global": 98.65,
  "target_ok_per_part": {
    "CYL COMP|K1AL": 98.0
  },
  "sample_targets": {
    "CYL COMP|K1AL|0":   10,
    "CRCS L|K1AL L1|1":  6,
    ...
  }
}
"""

import json
from pathlib import Path

# ── Path ────────────────────────────────────────────────────────
_BASE         = Path(__file__).resolve().parent
SETTINGS_PATH = _BASE / "data" / "settings.json"

# ── Default values (fallback kalau settings.json belum ada) ─────
_SAMPLE_TARGETS_DEFAULT: dict[str, int] = {
    "CYL COMP|K1AL|0":          10,
    "CYL COMP|K60|0":            3,
    "CYL COMP|K2SA|0":           8,
    "HOLDER WATER PUMP|K60|0":   4,
    "CYL HEAD GV|K60|0":         2,
    "CYL HEAD CAM|K60|0":        4,
    "CYL HEAD NT|K60|0":         4,
    "CYL HEAD ROUGH|K60|0":      2,
    "CYL HEAD GV|K2SA|0":        2,
    "CYL HEAD CAM|K2SA|0":       6,
    "CYL HEAD NT|K2SA|0":        6,
    "CYL HEAD ROUGH|K2SA|0":     2,
    "CYL HEAD GV|K1AL|0":        3,
    "CYL HEAD CAM|K1AL L2|0":    4,
    "CYL HEAD NT|K1AL L2|0":     4,
    "CYL HEAD CAM|K1AL L3|0":    4,
    "CYL HEAD NT|K1AL L3|0":     4,
    "CYL HEAD ROUGH|K1AL|0":     4,
    "CRCS L|K60|0":              2,
    "CRCS R|K60|0":              2,
    "CRCS L|K1AL L1|1":          6,
    "CRCS L|K1AL L1|2":          5,
    "CRCS L|K1AL L1|3":          5,
    "CRCS R|K1AL L1|1":          6,
    "CRCS R|K1AL L1|2":          5,
    "CRCS R|K1AL L1|3":          5,
    "CRCS L|K1AL L2|0":          2,
    "CRCS L|K1AL L3|0":          2,
    "CRCS R|K1AL L2|0":          4,
    "CRCS R|K1AL L3|0":          4,
    "CRCS L|K2SA|0":             4,
    "CRCS R|K2SA|0":             8,
    "MISSION CASE|K60|0":        2,
}

DEFAULTS: dict = {
    "target_ok_global": 98.65,
    "sample_targets":   _SAMPLE_TARGETS_DEFAULT,
}


# ════════════════════════════════════════════════════════════════
#  BACA / TULIS
# ════════════════════════════════════════════════════════════════

def load_settings() -> dict:
    """Baca settings.json. Fallback ke DEFAULTS kalau file tidak ada."""
    if not SETTINGS_PATH.exists():
        return {k: (v.copy() if isinstance(v, dict) else v)
                for k, v in DEFAULTS.items()}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge: key yang hilang di file → pakai default
        result = {k: (v.copy() if isinstance(v, dict) else v)
                  for k, v in DEFAULTS.items()}
        for k, v in data.items():
            result[k] = v
        # Buang per_part kalau masih ada dari versi lama
        result.pop("target_ok_per_part", None)
        # Pastikan sample_targets punya semua default entries
        for dk, dv in _SAMPLE_TARGETS_DEFAULT.items():
            result["sample_targets"].setdefault(dk, dv)
        return result
    except Exception:
        return {k: (v.copy() if isinstance(v, dict) else v)
                for k, v in DEFAULTS.items()}


def save_settings(data: dict) -> bool:
    """Tulis settings ke JSON. Return True kalau berhasil."""
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════
#  GETTER CONVENIENCE
# ════════════════════════════════════════════════════════════════

def get_target_ok() -> float:
    """Ambil target OK rate global."""
    s = load_settings()
    return float(s.get("target_ok_global", DEFAULTS["target_ok_global"]))


def get_sample_target(part: str, model: str, shift: str = "0") -> int:
    """
    Ambil target sample per shift.
    Cek shift spesifik dulu → fallback ke shift '0' (default).
    """
    s       = load_settings()
    targets = s.get("sample_targets", {})
    key_s   = f"{part}|{model}|{shift}"
    key_def = f"{part}|{model}|0"
    return int(targets.get(key_s) or targets.get(key_def) or 0)