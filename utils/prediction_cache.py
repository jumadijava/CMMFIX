"""
utils/prediction_cache.py
─────────────────────────
Simpan/load hasil prediksi XGBoost & SPC ke data/predictions.json.
Berlaku per cache_key (shift + date) — otomatis invalid saat shift berganti.

Dipakai oleh:
  - xgb_inference.py  → save setelah compute
  - mainloca.py       → load saat login (fast path, tanpa compute)
"""

import json
import threading
import pandas as pd
from pathlib import Path

PRED_PATH = Path("data") / "predictions.json"
_lock     = threading.Lock()


# ── Helpers ───────────────────────────────────────────────────────

def _load_raw() -> dict:
    if not PRED_PATH.exists():
        return {}
    try:
        with open(PRED_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_raw(data: dict) -> None:
    """Tulis JSON secara atomic (write ke .tmp lalu rename).
    Mencegah predictions.json korup kalau proses ke-interrupt (Ctrl+C)
    di tengah json.dump — file korup bikin _load_raw selalu return {}
    dan setiap rerun nyoba compute ulang (memperparah beban CPU)."""
    PRED_PATH.parent.mkdir(exist_ok=True)
    tmp_path = PRED_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    tmp_path.replace(PRED_PATH)


# ── Serialisasi _vbr {int: set} ↔ JSON {str: list} ───────────────

def _vbr_to_json(vbr: dict) -> dict:
    return {str(k): sorted(v) for k, v in vbr.items()}


def _vbr_from_json(vbr_j: dict) -> dict:
    return {int(k): set(v) for k, v in vbr_j.items()}


# ═══════════════════════════════════════════════════════════════
#  XGBoost
# ═══════════════════════════════════════════════════════════════

def save_xgb(cache_key: str, df: pd.DataFrame) -> None:
    """Simpan DataFrame hasil XGBoost ke JSON."""
    with _lock:
        data = _load_raw()
        data["xgb"] = {
            "key":     cache_key,
            "records": df.to_dict(orient="records"),
        }
        _save_raw(data)


def load_xgb(cache_key: str) -> pd.DataFrame | None:
    """Load XGBoost result dari JSON. Return None kalau key tidak cocok."""
    data = _load_raw()
    entry = data.get("xgb")
    if not entry or entry.get("key") != cache_key:
        return None
    try:
        return pd.DataFrame(entry["records"])
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
#  Rule Prediction
# ═══════════════════════════════════════════════════════════════

def save_rules(cache_key: str, rows: list) -> None:
    """Simpan list hasil rule prediction ke JSON."""
    with _lock:
        data = _load_raw()
        serialized = []
        for row in rows:
            r = dict(row)
            if "_vbr" in r:
                r["_vbr"] = _vbr_to_json(r["_vbr"])
            serialized.append(r)
        data["rules"] = {
            "key":  cache_key,
            "rows": serialized,
        }
        _save_raw(data)


def load_rules(cache_key: str) -> list | None:
    """Load rule result dari JSON. Return None kalau key tidak cocok."""
    data = _load_raw()
    entry = data.get("rules")
    if not entry or entry.get("key") != cache_key:
        return None
    try:
        rows = entry["rows"]
        for row in rows:
            if "_vbr" in row:
                row["_vbr"] = _vbr_from_json(row["_vbr"])
        return rows
    except Exception:
        return None