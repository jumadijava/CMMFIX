"""
pages/descriptive.py
────────────────────
Descriptive Analytics — 2 mode:
  ⚡ Quick           → drill-down pareto, terhubung ke Dashboard
  🔍 Deep Investigation → analisis mendalam dengan filter penuh
"""

import re
import streamlit as st
import streamlit.components.v1 as components
from streamlit_echarts import st_echarts, JsCode
import pandas as pd
import numpy as np
from datetime import datetime
import streamlit_antd_components as sac

from utils.filters import build_filters, build_filters_quick, apply_filters, TIMEZONE



# ─────────────────────────────────────────────────────────────────────
#  Helper: load ilustrasi lokal sebagai base64
# ─────────────────────────────────────────────────────────────────────
import base64 as _b64
from pathlib import Path as _IPath

_ILUSTRASI_DIR = _IPath("assets/ilustrasi")
_SPC_RULE_IMG_DIR  = _IPath("assets/ilustrasi/rule")
_RULE_IMG_FILES_DS = {
    1: "spc_rule_1.png",
    2: "spc_rule_2.png",
    3: "spc_rule_3.png",
    4: "spc_rule_4.png",
    5: "spc_rule_5.png",
    6: "spc_rule_6.png",
    7: "spc_rule_7.png",
}
_RULE_IMG_CACHE_DS: dict = {}

def _get_rule_img_html_ds(r_num: int, border_clr: str) -> str:
    """Return <img> base64 atau placeholder teks kalau file tidak ada."""
    if r_num in _RULE_IMG_CACHE_DS:
        return _RULE_IMG_CACHE_DS[r_num]
    fname = _RULE_IMG_FILES_DS.get(r_num, "")
    path  = _SPC_RULE_IMG_DIR / fname if fname else None
    if path and path.exists():
        ext  = path.suffix.lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        b64  = _b64.b64encode(path.read_bytes()).decode()
        html = (f'<img src="data:{mime};base64,{b64}" '
                f'style="max-width:100%;max-height:78px;object-fit:contain;" '
                f'alt="Rule {r_num}"/>')
    else:
        html = (f'<span style="font-size:10px;color:#CBD5E1;">'
                f'📷 Rule {r_num} — tempatkan <b>{fname}</b> di assets/ilustrasi/rule/</span>')
    _RULE_IMG_CACHE_DS[r_num] = html
    return html

_IMG_MAP = {
    "K2VJ_CYL_COMP":        "K2VJ.png",
    "K60_CYL_COMP":         "K2V.png",
    "K60_CRCS_L":           "K60.png",
    "K2SA_CYL_COMP":        "K2SA_CYLCOMP.jpg",
    "K1AL_L1_CRCS_L":       "K1AL_L1.jpg",
    "K1AL_L1_CRCS_R":       "K1AL_L1_R.jpg",
    "K1AL_L2_CRCS_L":       "K1AL_L2.jpg",
    "K1AL_L2_CRCS_R":       "K1AL_L2_R.jpg",
    "K1AL_L3_CRCS_L":       "K1AL_L3.jpg",
    "K1AL_L3_CRCS_R":       "K1AL_L3_R.jpg",
    "K2SA_CRCS_L":          "K2SA_CRCS_L.jpg",
    "K2SA_CRCS_R":          "K2SA_CRCS_R.jpg",
    "K60_CRCS_R":           "K60_R.jpg",
    "K60_MISSION":          "K60_MISSION.jpg",

    # CYL COMP
    "K1AL_CYL_COMP":        "K1AL_CYLCOMP.jpg",
    # CYL HEAD GV
    "K60_GV":               "K60_GV.jpg",
    "K2SA_GV":              "K2SA_GV.jpg",
    "K1AL_GV":              "K1AL_GV.jpg",

    # CYL HEAD CAM
    "K60_CAM":              "K60_CAM.jpg",
    "K2SA_CAM":             "K2SA_CAM.jpg",
    "K1AL_L2_CAM":          "K1AL_CAM.jpg",
    "K1AL_L3_CAM":          "K1AL_CAM.jpg",

    # CYL HEAD NT
    "K60_NT":               "K60_NT.jpg",
    "K2SA_NT":              "K2SA_NT.jpg",
    "K1AL_L2_NT":           "K1AL_NT.jpg",
    "K1AL_L3_NT":           "K1AL_NT.jpg",

    # CYL HEAD ROUGH
    "K60_ROUGH":            "K60_ROUGH.jpg",
    "K2SA_ROUGH":           "K2SA_ROUGH.jpg",
    "K1AL_ROUGH":           "K1AL_ROUGH.jpg",

    # HOLDER WATER PUMP
    "K60_HWP":              "K60_WP.jpg",
}

@st.cache_data(show_spinner=False)
def _get_image_b64(active_key: str) -> str | None:
    """Load gambar ilustrasi lokal, return data URL base64 atau None."""
    fname = _IMG_MAP.get(active_key)
    if not fname:
        return None
    path = _ILUSTRASI_DIR / fname
    if not path.exists():
        return None
    with open(path, "rb") as f:
        return "data:image/png;base64," + _b64.b64encode(f.read()).decode()

@st.cache_data(show_spinner=False)
def _get_image_path(active_key: str):
    """Return Path ke file ilustrasi lokal, atau None kalau tidak ada."""
    fname = _IMG_MAP.get(active_key)
    if not fname:
        return None
    path = _ILUSTRASI_DIR / fname
    return path if path.exists() else None

@st.cache_data(show_spinner=False)
def _detect_active_key(part: str, model: str) -> str:
    """Deteksi active_key berdasarkan Part + Model."""
    p, m = part.lower(), model.lower()

    # CRCS
    if "k2vj" in m and "cyl comp" in p:        return "K2VJ_CYL_COMP"
    if "k60"  in m and "crcs l" in p:          return "K60_CRCS_L"
    if "k60"  in m and "crcs r" in p:          return "K60_CRCS_R"
    if "k60"  in m and "mission" in p:         return "K60_MISSION"
    if "k2sa" in m and "crcs l" in p:          return "K2SA_CRCS_L"
    if "k2sa" in m and "crcs r" in p:          return "K2SA_CRCS_R"
    if "k1al l1" in m and "crcs l" in p:       return "K1AL_L1_CRCS_L"
    if "k1al l1" in m and "crcs r" in p:       return "K1AL_L1_CRCS_R"
    if "k1al l2" in m and "crcs l" in p:       return "K1AL_L2_CRCS_L"
    if "k1al l2" in m and "crcs r" in p:       return "K1AL_L2_CRCS_R"
    if "k1al l3" in m and "crcs l" in p:       return "K1AL_L3_CRCS_L"
    if "k1al l3" in m and "crcs r" in p:       return "K1AL_L3_CRCS_R"

    # CYL COMP
    if "k2sa" in m and "cyl comp" in p:        return "K2SA_CYL_COMP"
    if "k1al" in m and "cyl comp" in p:        return "K1AL_CYL_COMP"
    if "k60"  in m and "cyl comp" in p:        return "K60_CYL_COMP"

    # CYL HEAD GV
    if "k60"  in m and "gv" in p:             return "K60_GV"
    if "k2sa" in m and "gv" in p:             return "K2SA_GV"
    if "k1al" in m and "gv" in p:             return "K1AL_GV"

    # CYL HEAD CAM
    if "k60"    in m and "cam" in p:           return "K60_CAM"
    if "k2sa"   in m and "cam" in p:           return "K2SA_CAM"
    if "k1al l2" in m and "cam" in p:          return "K1AL_L2_CAM"
    if "k1al l3" in m and "cam" in p:          return "K1AL_L3_CAM"

    # CYL HEAD NT
    if "k60"    in m and "nt" in p:            return "K60_NT"
    if "k2sa"   in m and "nt" in p:            return "K2SA_NT"
    if "k1al l2" in m and "nt" in p:           return "K1AL_L2_NT"
    if "k1al l3" in m and "nt" in p:           return "K1AL_L3_NT"

    # CYL HEAD ROUGH
    if "k60"  in m and "rough" in p:           return "K60_ROUGH"
    if "k2sa" in m and "rough" in p:           return "K2SA_ROUGH"
    if "k1al" in m and "rough" in p:           return "K1AL_ROUGH"

    # HOLDER WATER PUMP
    if "k60"  in m and "water pump" in p:      return "K60_HWP"

    return ""

@st.cache_data(show_spinner=False)
def _calc_cpk_cached(vals_tuple: tuple, usl: float, lsl: float) -> dict | None:
    """Hitung Cp/Cpk dari tuple nilai — di-cache agar tidak hitung ulang tiap rerun."""
    import numpy as np
    vals = np.array(vals_tuple, dtype=float)
    n = len(vals)
    if n < 2:
        return None
    mean  = float(vals.mean())
    sigma = float(vals.std(ddof=1))
    if sigma == 0:
        return None
    tol_range = usl - lsl
    cp  = round(tol_range / (6 * sigma), 3)
    cpu = round((usl - mean) / (3 * sigma), 3)
    cpl = round((mean - lsl) / (3 * sigma), 3)
    cpk = round(min(cpu, cpl), 3)
    return {"cp": cp, "cpk": cpk, "cpu": cpu, "cpl": cpl,
            "mean": round(mean, 5), "sigma": round(sigma, 5), "n": n}

# ═════════════════════════════════════════════════════════════════════
#  COORD DB — gambar skematik part (dipakai di Deep Investigation)
# ═════════════════════════════════════════════════════════════════════
ORIG_H_MAP = {
    "K2VJ_CYL_COMP":  400,
    "K60_CRCS_L":     400,
}
# Semua key lain default 500

COORD_DB = {
    "K2VJ_CYL_COMP": [
        {"name": "J000", "value": [35, 101]},
        {"name": "L000", "value": [224, 170]},
        {"name": "J163", "value": [275, 64]},
        {"name": "J151", "value": [394, 171]},
        {"name": "J152", "value": [444, 174]},
        {"name": "L152", "value": [468, 178]},
        {"name": "J164", "value": [455, 66]},
        {"name": "L164", "value": [490, 61]},
        {"name": "L154", "value": [534, 262]},
        {"name": "L153", "value": [641, 262]},
        {"name": "L151", "value": [647, 167]},
        {"name": "K300", "value": [940, 54]},
        {"name": "K301", "value": [875, 119]},
        {"name": "K303", "value": [937, 119]},
        {"name": "K302", "value": [994, 119]},
        {"name": "K305", "value": [776, 227]},
        {"name": "K304", "value": [900, 278]},
        {"name": "K402", "value": [1123, 215]},
        {"name": "K403", "value": [1213, 210]},
        {"name": "K401", "value": [1125, 347]},
        {"name": "L163", "value": [651, 65]},
    ],
    "K60_CRCS_L": [
        {"name": "A008", "value": [23, 171]},
        {"name": "A004", "value": [26, 122]},
        {"name": "A153", "value": [48, 78]},
        {"name": "A154", "value": [91, 77]},
        {"name": "A022", "value": [122, 63]},
        {"name": "A038", "value": [149, 74]},
        {"name": "A039", "value": [181, 61]},
        {"name": "A006", "value": [206, 81]},
        {"name": "A020", "value": [228, 102]},
        {"name": "A071", "value": [273, 92]},
        {"name": "A040", "value": [297, 68]},
        {"name": "A002", "value": [339, 90]},
        {"name": "A045", "value": [378, 94]},
        {"name": "A046", "value": [465, 154]},
        {"name": "A005", "value": [468, 182]},
        {"name": "A047", "value": [471, 207]},
        {"name": "A041", "value": [469, 236]},
        {"name": "A019", "value": [493, 266]},
        {"name": "A021", "value": [464, 336]},
        {"name": "A001", "value": [422, 342]},
        {"name": "A042", "value": [380, 342]},
        {"name": "A026", "value": [341, 342]},
        {"name": "A043", "value": [309, 343]},
        {"name": "A023", "value": [276, 316]},
        {"name": "A044", "value": [245, 343]},
        {"name": "A048", "value": [205, 335]},
        {"name": "A024", "value": [185, 303]},
        {"name": "A003", "value": [164, 343]},
        {"name": "A007", "value": [127, 334]},
        {"name": "A049", "value": [80, 261]},
        {"name": "A050", "value": [35, 234]},
        {"name": "B073", "value": [531, 185]},
        {"name": "B012", "value": [530, 159]},
        {"name": "B049", "value": [582, 139]},
        {"name": "B055", "value": [635, 98]},
        {"name": "B006", "value": [685, 98]},
        {"name": "B054", "value": [733, 95]},
        {"name": "B023", "value": [779, 93]},
        {"name": "B053", "value": [821, 90]},
        {"name": "B026", "value": [854, 64]},
        {"name": "B025", "value": [881, 91]},
        {"name": "B021", "value": [956, 94]},
        {"name": "B052", "value": [932, 146]},
        {"name": "B011", "value": [945, 169]},
        {"name": "B005", "value": [962, 212]},
        {"name": "B065", "value": [946, 238]},
        {"name": "B064", "value": [910, 277]},
        {"name": "B051", "value": [871, 311]},
        {"name": "B058", "value": [832, 335]},
        {"name": "B060", "value": [787, 335]},
        {"name": "B061", "value": [746, 335]},
        {"name": "B057", "value": [698, 335]},
        {"name": "B062", "value": [653, 335]},
        {"name": "B056", "value": [609, 335]},
        {"name": "B063", "value": [524, 332]},
        {"name": "B022", "value": [534, 292]},
        {"name": "A151", "value": [1057, 114]},
        {"name": "A152", "value": [1115, 100]},
        {"name": "A111", "value": [1121, 303]},
    ],
    "K2SA_CYL_COMP":   [],
    "K1AL_L1_CRCS_L": [
        {"name": "B078", "value": [69,  425]},
        {"name": "B056", "value": [87,  380]},
        {"name": "B077", "value": [88,  277]},
        {"name": "B055", "value": [107, 279]},
        {"name": "B081", "value": [112, 359]},
        {"name": "B028", "value": [115, 439]},
        {"name": "B082", "value": [127, 332]},
        {"name": "B017", "value": [135, 365]},
        {"name": "B010", "value": [150, 373]},
        {"name": "B027", "value": [160, 345]},    
        {"name": "B025", "value": [160, 295]},
        {"name": "B021", "value": [137, 245]},
        {"name": "B018", "value": [164, 389]},
        {"name": "B011", "value": [179, 261]},
        {"name": "B057", "value": [180, 415]},
        {"name": "B080", "value": [210, 354]},
        {"name": "B023", "value": [224, 439]},
        {"name": "B076", "value": [231, 246]},
        {"name": "B054", "value": [252, 259]},
        {"name": "B075", "value": [283, 248]},
        {"name": "B058", "value": [284, 416]},
        {"name": "B051", "value": [340, 256]},
        {"name": "B059", "value": [353, 416]},
        {"name": "B061", "value": [363, 332]},
        {"name": "B074", "value": [443, 242]},
        {"name": "B024", "value": [449, 420]},
        {"name": "B052", "value": [465, 253]},
        {"name": "B006", "value": [465, 332]},
        {"name": "B071", "value": [552, 387]},
        {"name": "B022", "value": [556, 248]},
        {"name": "B060", "value": [565, 332]},
        {"name": "B053", "value": [570, 286]},
        {"name": "B073", "value": [605, 266]},
        {"name": "B072", "value": [627, 345]},
        {"name": "A008", "value": [650,  112]},
        {"name": "A003", "value": [629,  76]},
        {"name": "A004", "value": [693, 165]},
        {"name": "A049", "value": [737, 105]},
        {"name": "A007", "value": [713, 125]},
        {"name": "A006", "value": [770, 125]},
        {"name": "A048", "value": [751, 141]},
        {"name": "A156", "value": [949, 339]},
        {"name": "A151", "value": [969, 422]},
        {"name": "A044", "value": [1014, 193]},
        {"name": "A045", "value": [1015, 148]},
        {"name": "A001", "value": [1017,  90]},
        {"name": "A155", "value": [1048, 339]},
        {"name": "A152", "value": [1051, 422]},
        {"name": "A046", "value": [1081,  67]},
        {"name": "A005", "value": [1081,  120]},
        {"name": "A043", "value": [1083, 215]},
        {"name": "A030", "value": [1100, 170]},
        {"name": "A154", "value": [1108, 340]},
        {"name": "A047", "value": [1156,  74]},
        {"name": "A042", "value": [1158, 207]},
        {"name": "A041", "value": [1178, 157]},
        {"name": "A002", "value": [1183, 181]},

    ],
    "K1AL_L1_CRCS_R": [
        {"name": "D093", "value": [150, 220]},
        {"name": "D094", "value": [195, 160]},
        {"name": "D046", "value": [195, 179]},
        {"name": "D021", "value": [173,  140]},
        {"name": "D092", "value": [187, 283]},
        {"name": "D047", "value": [214,  95]},
        {"name": "D095", "value": [241,  99]},
        {"name": "D015", "value": [281, 180]},
        {"name": "D014", "value": [320, 140]},
        {"name": "D013", "value": [344, 180]},
        {"name": "D087", "value": [354, 286]},
        {"name": "D005", "value": [310, 193]},
        {"name": "D096", "value": [402, 110]},
        {"name": "D041", "value": [399,  72]},
        {"name": "D090", "value": [435,  45]},
        {"name": "D098", "value": [449, 218]},
        {"name": "D023", "value": [520, 236]},
        {"name": "D091", "value": [510, 280]},
        {"name": "D033", "value": [485, 144]},
        {"name": "D032", "value": [512, 135]},
        {"name": "D042", "value": [514,  94]},
        {"name": "D097", "value": [524, 115]},
        {"name": "D043", "value": [533, 172]},
        {"name": "C163", "value": [755, 400]},
        {"name": "C162", "value": [742, 390]},
        {"name": "C164", "value": [700, 400]},
        {"name": "C111", "value": [725, 390]},
        {"name": "C005", "value": [1008, 183]},
        {"name": "C019", "value": [867,  68]},
        {"name": "C158", "value": [893, 143]},
        {"name": "D044", "value": [485,  244]},
        {"name": "C002", "value": [945,  86]},
        {"name": "C030", "value": [991,  96]},
        {"name": "C159", "value": [1008, 101]},
        {"name": "C016", "value": [1050, 139]},
        {"name": "C001", "value": [1075, 219]},
        {"name": "C020", "value": [1105, 212]},
    ],
    "K1AL_L2_CRCS_L": [
        {"name": "B078", "value": [69,  425]},
        {"name": "B056", "value": [87,  380]},
        {"name": "B077", "value": [88,  277]},
        {"name": "B055", "value": [107, 279]},
        {"name": "B081", "value": [112, 359]},
        {"name": "B028", "value": [115, 439]},
        {"name": "B082", "value": [127, 332]},
        {"name": "B017", "value": [135, 365]},
        {"name": "B010", "value": [150, 373]},
        {"name": "B027", "value": [160, 345]},    
        {"name": "B025", "value": [160, 295]},
        {"name": "B021", "value": [137, 245]},
        {"name": "B018", "value": [164, 389]},
        {"name": "B011", "value": [179, 261]},
        {"name": "B057", "value": [180, 415]},
        {"name": "B080", "value": [210, 354]},
        {"name": "B023", "value": [224, 439]},
        {"name": "B076", "value": [231, 246]},
        {"name": "B054", "value": [252, 259]},
        {"name": "B075", "value": [283, 248]},
        {"name": "B058", "value": [284, 416]},
        {"name": "B051", "value": [340, 256]},
        {"name": "B059", "value": [353, 416]},
        {"name": "B061", "value": [363, 332]},
        {"name": "B074", "value": [443, 242]},
        {"name": "B024", "value": [449, 420]},
        {"name": "B052", "value": [465, 253]},
        {"name": "B006", "value": [465, 332]},
        {"name": "B071", "value": [552, 387]},
        {"name": "B022", "value": [556, 248]},
        {"name": "B060", "value": [565, 332]},
        {"name": "B053", "value": [570, 286]},
        {"name": "B073", "value": [605, 266]},
        {"name": "B072", "value": [627, 345]},
        {"name": "A008", "value": [650,  112]},
        {"name": "A003", "value": [629,  76]},
        {"name": "A004", "value": [693, 165]},
        {"name": "A049", "value": [737, 105]},
        {"name": "A007", "value": [713, 125]},
        {"name": "A006", "value": [770, 125]},
        {"name": "A048", "value": [751, 141]},
        {"name": "A156", "value": [949, 339]},
        {"name": "A151", "value": [969, 422]},
        {"name": "A044", "value": [1014, 193]},
        {"name": "A045", "value": [1015, 148]},
        {"name": "A001", "value": [1017,  90]},
        {"name": "A155", "value": [1048, 339]},
        {"name": "A152", "value": [1051, 422]},
        {"name": "A046", "value": [1081,  67]},
        {"name": "A005", "value": [1081,  120]},
        {"name": "A043", "value": [1083, 215]},
        {"name": "A030", "value": [1100, 170]},
        {"name": "A154", "value": [1108, 340]},
        {"name": "A047", "value": [1156,  74]},
        {"name": "A042", "value": [1158, 207]},
        {"name": "A041", "value": [1178, 157]},
        {"name": "A002", "value": [1183, 181]},
    ],
    "K1AL_L2_CRCS_R": [
        {"name": "D093", "value": [150, 220]},
        {"name": "D094", "value": [195, 160]},
        {"name": "D046", "value": [195, 179]},
        {"name": "D021", "value": [173,  140]},
        {"name": "D092", "value": [187, 283]},
        {"name": "D047", "value": [214,  95]},
        {"name": "D095", "value": [241,  99]},
        {"name": "D015", "value": [281, 180]},
        {"name": "D014", "value": [320, 140]},
        {"name": "D013", "value": [344, 180]},
        {"name": "D087", "value": [354, 286]},
        {"name": "D005", "value": [310, 193]},
        {"name": "D096", "value": [402, 110]},
        {"name": "D041", "value": [399,  72]},
        {"name": "D090", "value": [435,  45]},
        {"name": "D098", "value": [449, 218]},
        {"name": "D023", "value": [520, 236]},
        {"name": "D091", "value": [510, 280]},
        {"name": "D033", "value": [485, 144]},
        {"name": "D032", "value": [512, 135]},
        {"name": "D042", "value": [514,  94]},
        {"name": "D097", "value": [524, 115]},
        {"name": "D043", "value": [533, 172]},
        {"name": "C163", "value": [755, 400]},
        {"name": "C162", "value": [742, 390]},
        {"name": "C164", "value": [700, 400]},
        {"name": "C111", "value": [725, 390]},
        {"name": "C005", "value": [1008, 183]},
        {"name": "C019", "value": [867,  68]},
        {"name": "C158", "value": [893, 143]},
        {"name": "D044", "value": [485,  244]},
        {"name": "C002", "value": [945,  86]},
        {"name": "C030", "value": [991,  96]},
        {"name": "C159", "value": [1008, 101]},
        {"name": "C016", "value": [1050, 139]},
        {"name": "C001", "value": [1075, 219]},
        {"name": "C020", "value": [1105, 212]},
    ],
    "K1AL_L3_CRCS_L": [
        {"name": "B078", "value": [69,  425]},
        {"name": "B056", "value": [87,  380]},
        {"name": "B077", "value": [88,  277]},
        {"name": "B055", "value": [107, 279]},
        {"name": "B081", "value": [112, 359]},
        {"name": "B028", "value": [115, 439]},
        {"name": "B082", "value": [127, 332]},
        {"name": "B017", "value": [135, 365]},
        {"name": "B010", "value": [150, 373]},
        {"name": "B027", "value": [160, 345]},    
        {"name": "B025", "value": [160, 295]},
        {"name": "B021", "value": [137, 245]},
        {"name": "B018", "value": [164, 389]},
        {"name": "B011", "value": [179, 261]},
        {"name": "B057", "value": [180, 415]},
        {"name": "B080", "value": [210, 354]},
        {"name": "B023", "value": [224, 439]},
        {"name": "B076", "value": [231, 246]},
        {"name": "B054", "value": [252, 259]},
        {"name": "B075", "value": [283, 248]},
        {"name": "B058", "value": [284, 416]},
        {"name": "B051", "value": [340, 256]},
        {"name": "B059", "value": [353, 416]},
        {"name": "B061", "value": [363, 332]},
        {"name": "B074", "value": [443, 242]},
        {"name": "B024", "value": [449, 420]},
        {"name": "B052", "value": [465, 253]},
        {"name": "B006", "value": [465, 332]},
        {"name": "B071", "value": [552, 387]},
        {"name": "B022", "value": [556, 248]},
        {"name": "B060", "value": [565, 332]},
        {"name": "B053", "value": [570, 286]},
        {"name": "B073", "value": [605, 266]},
        {"name": "B072", "value": [627, 345]},
        {"name": "A008", "value": [650,  112]},
        {"name": "A003", "value": [629,  76]},
        {"name": "A004", "value": [693, 165]},
        {"name": "A049", "value": [737, 105]},
        {"name": "A007", "value": [713, 125]},
        {"name": "A006", "value": [770, 125]},
        {"name": "A048", "value": [751, 141]},
        {"name": "A156", "value": [949, 339]},
        {"name": "A151", "value": [969, 422]},
        {"name": "A044", "value": [1014, 193]},
        {"name": "A045", "value": [1015, 148]},
        {"name": "A001", "value": [1017,  90]},
        {"name": "A155", "value": [1048, 339]},
        {"name": "A152", "value": [1051, 422]},
        {"name": "A046", "value": [1081,  67]},
        {"name": "A005", "value": [1081,  120]},
        {"name": "A043", "value": [1083, 215]},
        {"name": "A030", "value": [1100, 170]},
        {"name": "A154", "value": [1108, 340]},
        {"name": "A047", "value": [1156,  74]},
        {"name": "A042", "value": [1158, 207]},
        {"name": "A041", "value": [1178, 157]},
        {"name": "A002", "value": [1183, 181]},
    ],
    "K1AL_L3_CRCS_R": [
        {"name": "D093", "value": [150, 220]},
        {"name": "D094", "value": [195, 160]},
        {"name": "D046", "value": [195, 179]},
        {"name": "D021", "value": [173,  140]},
        {"name": "D092", "value": [187, 283]},
        {"name": "D047", "value": [214,  95]},
        {"name": "D095", "value": [241,  99]},
        {"name": "D015", "value": [281, 180]},
        {"name": "D014", "value": [320, 140]},
        {"name": "D013", "value": [344, 180]},
        {"name": "D087", "value": [354, 286]},
        {"name": "D005", "value": [310, 193]},
        {"name": "D096", "value": [402, 110]},
        {"name": "D041", "value": [399,  72]},
        {"name": "D090", "value": [435,  45]},
        {"name": "D098", "value": [449, 218]},
        {"name": "D023", "value": [520, 236]},
        {"name": "D091", "value": [510, 280]},
        {"name": "D033", "value": [485, 144]},
        {"name": "D032", "value": [512, 135]},
        {"name": "D042", "value": [514,  94]},
        {"name": "D097", "value": [524, 115]},
        {"name": "D043", "value": [533, 172]},
        {"name": "C163", "value": [755, 400]},
        {"name": "C162", "value": [742, 390]},
        {"name": "C164", "value": [700, 400]},
        {"name": "C111", "value": [725, 390]},
        {"name": "C005", "value": [1008, 183]},
        {"name": "C019", "value": [867,  68]},
        {"name": "C158", "value": [893, 143]},
        {"name": "D044", "value": [485,  244]},
        {"name": "C002", "value": [945,  86]},
        {"name": "C030", "value": [991,  96]},
        {"name": "C159", "value": [1008, 101]},
        {"name": "C016", "value": [1050, 139]},
        {"name": "C001", "value": [1075, 219]},
        {"name": "C020", "value": [1105, 212]},

    ],
    "K2SA_CRCS_L": [
        {"name": "A065", "value": [42,  137]},
        {"name": "A041", "value": [49,   90]},
        {"name": "A042", "value": [49,   69]},
        {"name": "A002", "value": [55,   44]},
        {"name": "A043", "value": [110,   50]},
        {"name": "A046", "value": [62,  206]},
        {"name": "A064", "value": [64,  159]},
        {"name": "A026", "value": [76,   99]},
        {"name": "A005", "value": [137, 163]},
        {"name": "A047", "value": [144,  84]},
        {"name": "A044", "value": [228, 60]},
        {"name": "A002", "value": [189,  33]},
        {"name": "B056", "value": [1000,  70]},
        {"name": "A066", "value": [209, 104]},
        {"name": "A045", "value": [218, 191]},
        {"name": "A067", "value": [224, 132]},
        {"name": "A023", "value": [228,  40]},
        {"name": "A040", "value": [237, 160]},
        {"name": "A0071", "value": [269, 257]},
        {"name": "A020", "value": [328, 198]},
        {"name": "A04", "value": [337, 159]},
        {"name": "A039", "value": [359, 241]},
        {"name": "A006", "value": [379, 160]},
        {"name": "A003", "value": [382, 103]},
        {"name": "A024", "value": [391,  74]},
        {"name": "A007", "value": [426, 160]},
        {"name": "A049", "value": [450,  95]},
        {"name": "A008", "value": [469, 176]},
        {"name": "B022", "value": [512, 245]},
        {"name": "A038", "value": [429, 245]},
        {"name": "A004", "value": [512, 220]},
        {"name": "A050", "value": [512, 140]},
        {"name": "A15", "value": [428, 371]},
        {"name": "A11", "value": [472, 383]},
        {"name": "A15", "value": [512, 371]},
        {"name": "B011", "value": [600, 185]},
        {"name": "B051", "value": [619, 130]},
        {"name": "B052", "value": [620, 210]},
        {"name": "A158", "value": [662, 271]},
        {"name": "B060", "value": [840, 96]},
        {"name": "B021", "value": [688, 105]},
        {"name": "A001", "value": [137, 220]},
        {"name": "B054", "value": [880, 240]},
        {"name": "B025", "value": [737, 242]},
        {"name": "B055", "value": [1000, 240]},
        {"name": "B058", "value": [815,  96]},
        {"name": "B053", "value": [816, 209]},
        {"name": "A153", "value": [826, 344]},
        {"name": "B073", "value": [1180, 175]},
        {"name": "A155", "value": [869, 401]},
        {"name": "B049", "value": [1150, 200]},
        {"name": "A154", "value": [920, 362]},
        {"name": "B061", "value": [925, 172]},
        {"name": "B057", "value": [926,  65]},
        {"name": "B062", "value": [1051,  85]},
        {"name": "B012", "value": [1080, 184]},
        {"name": "B066", "value": [1175,  80]},
    ],
    "K2SA_CRCS_R": [
        {"name": "C002", "value": [86,  260]},
        {"name": "C047", "value": [112, 226]},
        {"name": "C044", "value": [158, 321]},
        {"name": "C026", "value": [210, 136]},
        {"name": "C016", "value": [237, 182]},
        {"name": "C005", "value": [260, 205]},        {"name": "C046", "value": [363, 122]},
        {"name": "C001", "value": [380, 203]},
        {"name": "C021", "value": [420, 127]},
        {"name": "C166", "value": [565, 307]},
        {"name": "C164", "value": [591, 461]},
        {"name": "C162", "value": [550, 461]},
        {"name": "C160", "value": [640, 452]},
        {"name": "C111", "value": [650, 400]},
        {"name": "C163", "value": [729, 465]},
        {"name": "C165", "value": [738, 315]},
        {"name": "D000", "value": [929,  33]},
        {"name": "D021", "value": [903, 118]},
        {"name": "D080", "value": [968, 245]},
        {"name": "D070", "value": [1175, 92]},
        {"name": "D071", "value": [1160, 158]},
        {"name": "D074", "value": [876, 160]},
        {"name": "D083", "value": [846, 125]},
        {"name": "D017", "value": [1045, 146]},
        {"name": "D013", "value": [1106, 123]},
        {"name": "D084", "value": [1067, 123]},
        {"name": "D015", "value": [1142, 188]},
        {"name": "D073", "value": [861, 258]},
        {"name": "D018", "value": [1085, 217]},
        {"name": "D085", "value": [1124, 258]},
        {"name": "D082", "value": [916, 233]},
        {"name": "D092", "value": [882, 322]},
        {"name": "D014", "value": [1008, 287]},
        {"name": "D023", "value": [1191, 300]},
        {"name": "D075", "value": [935, 315]},
        {"name": "D092", "value": [844, 329]},
        {"name": "D087", "value": [992, 341]},
        {"name": "D091", "value": [1154, 342]},
    ],
    "K60_CRCS_R": [
        {"name": "C161", "value": [111, 245]},
        {"name": "C001", "value": [132, 144]},
        {"name": "C026", "value": [146, 247]},
        {"name": "C019", "value": [170, 128]},
        {"name": "C000", "value": [285, 359]},
        {"name": "C016", "value": [247, 244]},
        {"name": "C020", "value": [258, 359]},
        {"name": "C005", "value": [274, 281]},
        {"name": "C002", "value": [336, 342]},
        {"name": "C162", "value": [542, 303]},
        {"name": "C164", "value": [557, 303]},
        {"name": "C166", "value": [562, 226]},
        {"name": "C160", "value": [586, 298]},
        {"name": "C111", "value": [615, 298]},
        {"name": "C165", "value": [660, 227]},
        {"name": "C163", "value": [673, 303]},
        {"name": "D072", "value": [879, 353]},
        {"name": "D073", "value": [898, 336]},
        {"name": "D074", "value": [899, 232]},
        {"name": "D092", "value": [903, 372]},
        {"name": "D081", "value": [947, 301]},
        {"name": "D083", "value": [954, 217]},
        {"name": "D080", "value": [976, 301]},
        {"name": "D086", "value": [990, 305]},
        {"name": "D082", "value": [1002, 352]},
        {"name": "D087", "value": [1027, 404]},
        {"name": "D084", "value": [1054, 192]},
        {"name": "D000", "value": [1054, 97]},
        {"name": "D085", "value": [1074, 318]},
        {"name": "D013", "value": [1089, 195]},
        {"name": "D071", "value": [1117, 324]},
        {"name": "D091", "value": [1117, 395]},
        {"name": "D070", "value": [1118, 203]},
        {"name": "D017", "value": [1118, 240]},
        {"name": "D023", "value": [1143, 358]},
        {"name": "C090", "value": [1170, 260]},
        {"name": "D021", "value": [1155,  97]},
    ],
    "K60_MISSION": [
        {"name": "C048", "value": [57,  167]},
        {"name": "C033", "value": [92,   98]},
        {"name": "C031", "value": [128,  75]},
        {"name": "C050", "value": [153, 233]},
        {"name": "C039", "value": [186,  42]},
        {"name": "C032", "value": [193, 115]},
        {"name": "C03R", "value": [219,  46]},
        {"name": "C049", "value": [276, 231]},
        {"name": "C004", "value": [278, 133]},
        {"name": "C008", "value": [337,  77]},
        {"name": "C004b","value": [356, 171]},
        {"name": "C222", "value": [371, 150]},
        {"name": "D031", "value": [554, 327]},
        {"name": "C001", "value": [731, 121]},
        {"name": "C004c","value": [795, 429]},
        {"name": "C030", "value": [852,  91]},
        {"name": "C003", "value": [925, 296]},
        {"name": "C006", "value": [1028, 130]},
        {"name": "C007", "value": [1077, 128]},
        {"name": "C222b","value": [1128, 101]},
    ],

    # ── CYL COMP ─────────────────────────────────────────────────────
    "K1AL_CYL_COMP": [
        {"name": "K300",  "value": [119, 262]},
        {"name": "L000",  "value": [150, 351]},
        {"name": "K401",  "value": [180, 179]},
        {"name": "K301",  "value": [183, 279]},
        {"name": "K302",  "value": [171, 408]},
        {"name": "J000",  "value": [236, 170]},
        {"name": "L100",  "value": [338, 240]},
        {"name": "J151",  "value": [550, 176]},
        {"name": "J152",  "value": [677, 175]},
        {"name": "L164",  "value": [947,  54]},
        {"name": "L151",  "value": [1010, 290]},
        {"name": "L153",  "value": [1028, 240]},
        {"name": "L100b", "value": [843, 403]},
        {"name": "L151b", "value": [1168, 405]},
        {"name": "L153b", "value": [1122, 176]},
    ],
    "K2SA_CYL_COMP": [
        {"name": "J151",  "value": [ 90, 216]},
        {"name": "J163",  "value": [ 93, 100]},
        {"name": "J152",  "value": [228, 218]},
        {"name": "J164",  "value": [229,  98]},
        {"name": "L155",  "value": [367, 195]},
        {"name": "L164",  "value": [386, 105]},
        {"name": "L152",  "value": [387, 295]},
        {"name": "L154",  "value": [395, 217]},
        {"name": "L151",  "value": [561, 107]},
        {"name": "L153",  "value": [562, 220]},
        {"name": "L163",  "value": [567, 295]},
        {"name": "K402",  "value": [726, 392]},
        {"name": "K304",  "value": [783,  98]},
        {"name": "K306",  "value": [1120, 352]},
        {"name": "K301",  "value": [1127, 334]},
        {"name": "K303",  "value": [1143, 331]},
        {"name": "K501",  "value": [1146,  90]},
        {"name": "K302",  "value": [1162, 370]},
    ],
    "K60_CYL_COMP": [
        {"name": "J000", "value": [35, 101]},
        {"name": "L000", "value": [224, 170]},
        {"name": "J163", "value": [275, 64]},
        {"name": "J151", "value": [394, 171]},
        {"name": "J152", "value": [444, 174]},
        {"name": "L152", "value": [468, 178]},
        {"name": "J164", "value": [455, 66]},
        {"name": "L164", "value": [490, 61]},
        {"name": "L154", "value": [534, 262]},
        {"name": "L153", "value": [641, 262]},
        {"name": "L151", "value": [647, 167]},
        {"name": "K300", "value": [940, 54]},
        {"name": "K301", "value": [875, 119]},
        {"name": "K303", "value": [937, 119]},
        {"name": "K302", "value": [994, 119]},
        {"name": "K305", "value": [776, 227]},
        {"name": "K304", "value": [900, 278]},
        {"name": "K402", "value": [1123, 215]},
        {"name": "K403", "value": [1213, 210]},
        {"name": "K401", "value": [1125, 347]},
        {"name": "L163", "value": [651, 65]},
    ],

    # ── CYL HEAD GV ──────────────────────────────────────────────────
    "K2SA_GV": [
        {"name": "P201",  "value": [609, 322]},
        {"name": "P202",  "value": [626, 160]},
        {"name": "P203",  "value": [659, 319]},
        {"name": "P204",  "value": [640, 196]},
    ],
    "K60_GV": [
        {"name": "M202", "value": [638, 165]},
        {"name": "M201", "value": [445, 285]},
        {"name": "N702", "value": [338, 420]},
        {"name": "N700", "value": [495, 420]},
        {"name": "N701", "value": [642, 420]},
        {"name": "N703", "value": [795, 420]},
    ],
    "K1AL_GV": [
        {"name": "S064", "value": [335, 112]},
        {"name": "L104", "value": [468, 118]},
        {"name": "L105", "value": [598, 118]},
        {"name": "S063", "value": [722, 112]},
        {"name": "P101", "value": [793, 143]},
        {"name": "P201", "value": [326, 202]},
        {"name": "S003", "value": [784, 210]},
        {"name": "P202", "value": [784, 256]},
        {"name": "S002", "value": [321, 298]},
        {"name": "S001", "value": [784, 320]},
        {"name": "S052", "value": [302, 373]},
        {"name": "S051", "value": [763, 378]},
        {"name": "P000", "value": [387, 415]},
        {"name": "P001", "value": [573, 415]},
    ],

    # ── CYL HEAD CAM ─────────────────────────────────────────────────
    "K2SA_CAM": [
        {"name": "S000",  "value": [402, 118]},
        {"name": "N504",  "value": [467, 263]},
        {"name": "L103",  "value": [510, 205]},
        {"name": "N501",  "value": [546, 438]},
        {"name": "L102",  "value": [611, 252]},
        {"name": "N503",  "value": [636,  72]},
        {"name": "N502",  "value": [657, 139]},
        {"name": "L100",  "value": [730, 172]},
        {"name": "N505",  "value": [730, 335]},
        {"name": "N500",  "value": [731, 205]},
        {"name": "L101",  "value": [794,  55]},
        {"name": "N506",  "value": [843, 336]},
        {"name": "N507",  "value": [913, 336]},
    ],
    "K60_CAM": [
        {"name": "L101", "value": [508, 112]},
        {"name": "L103", "value": [600, 122]},
        {"name": "L102", "value": [682, 122]},
        {"name": "L100", "value": [963, 138]},
        {"name": "N504", "value": [243, 232]},
        {"name": "N505", "value": [343, 222]},
        {"name": "N507", "value": [1032, 222]},
        {"name": "N503", "value": [197, 295]},
        {"name": "N501", "value": [277, 382]},
        {"name": "N502", "value": [378, 412]},
        {"name": "N506", "value": [648, 382]},
    ],
    "K1AL_L2_CAM": [
        # V1 — top face
        {"name": "S064", "value": [121,  47]},
        {"name": "L104", "value": [175,  47]},
        {"name": "L105", "value": [215,  47]},
        {"name": "S063", "value": [260,  43]},
        {"name": "P101", "value": [295,  70]},
        {"name": "P201", "value": [ 93, 113]},
        {"name": "S003", "value": [267, 113]},
        {"name": "P202", "value": [265, 140]},
        {"name": "S002", "value": [ 93, 167]},
        {"name": "S001", "value": [262, 170]},
        {"name": "S052", "value": [ 97, 215]},
        {"name": "S051", "value": [265, 210]},
        {"name": "P000", "value": [140, 233]},
        {"name": "P001", "value": [210, 233]},
        # V2 — face 2
        {"name": "M063", "value": [500,  35]},
        {"name": "M202", "value": [495, 110]},
        {"name": "M051", "value": [490, 183]},
        # V3 — dua side view
        {"name": "M064", "value": [668,  33]},
        {"name": "M201", "value": [672, 117]},
        {"name": "M052", "value": [672, 203]},
        {"name": "N702", "value": [860,  73]},
        {"name": "M204", "value": [810, 123]},
        {"name": "N701", "value": [858, 220]},
        # V4
        {"name": "N700", "value": [1020, 115]},
        {"name": "N703", "value": [1005, 200]},
        # V5 — bottom face
        {"name": "L101", "value": [ 97, 283]},
        {"name": "L103", "value": [163, 287]},
        {"name": "L102", "value": [225, 287]},
        {"name": "L100", "value": [143, 460]},
        # V6
        {"name": "S000", "value": [450, 260]},
        {"name": "M000", "value": [418, 490]},
        # V7 — KOJA face
        {"name": "M205", "value": [635, 360]},
        {"name": "N802", "value": [682, 455]},
        {"name": "N800", "value": [762, 453]},
        {"name": "N801", "value": [825, 453]},
        # V8
        {"name": "N005", "value": [965, 310]},
        {"name": "N004", "value": [965, 395]},
    ],
    "K1AL_L3_CAM": [
        # V1 — top face
        {"name": "S064", "value": [121,  47]},
        {"name": "L104", "value": [175,  47]},
        {"name": "L105", "value": [215,  47]},
        {"name": "S063", "value": [260,  43]},
        {"name": "P101", "value": [295,  70]},
        {"name": "P201", "value": [ 93, 113]},
        {"name": "S003", "value": [267, 113]},
        {"name": "P202", "value": [265, 140]},
        {"name": "S002", "value": [ 93, 167]},
        {"name": "S001", "value": [262, 170]},
        {"name": "S052", "value": [ 97, 215]},
        {"name": "S051", "value": [265, 210]},
        {"name": "P000", "value": [140, 233]},
        {"name": "P001", "value": [210, 233]},
        # V2 — face 2
        {"name": "M063", "value": [500,  35]},
        {"name": "M202", "value": [495, 110]},
        {"name": "M051", "value": [490, 183]},
        # V3
        {"name": "M064", "value": [668,  33]},
        {"name": "M201", "value": [672, 117]},
        {"name": "M052", "value": [672, 203]},
        {"name": "N702", "value": [860,  73]},
        {"name": "M204", "value": [810, 123]},
        {"name": "N701", "value": [858, 220]},
        # V4
        {"name": "N700", "value": [1020, 115]},
        {"name": "N703", "value": [1005, 200]},
        # V5
        {"name": "L101", "value": [ 97, 283]},
        {"name": "L103", "value": [163, 287]},
        {"name": "L102", "value": [225, 287]},
        {"name": "L100", "value": [143, 460]},
        # V6
        {"name": "S000", "value": [450, 260]},
        {"name": "M000", "value": [418, 490]},
        # V7
        {"name": "M205", "value": [635, 360]},
        {"name": "N802", "value": [682, 455]},
        {"name": "N800", "value": [762, 453]},
        {"name": "N801", "value": [825, 453]},
        # V8
        {"name": "N005", "value": [965, 310]},
        {"name": "N004", "value": [965, 395]},
    ],

    # ── CYL HEAD NT ──────────────────────────────────────────────────
    "K2SA_NT": [
        {"name": "N702",  "value": [176, 290]},
        {"name": "N800",  "value": [182, 183]},
        {"name": "N802",  "value": [195, 100]},
        {"name": "N702",  "value": [250, 133]},
        {"name": "N700",  "value": [322, 271]},
        {"name": "M064",  "value": [505,  33]},
        {"name": "M052",  "value": [506,  98]},
        {"name": "M203",  "value": [534, 267]},
        {"name": "M204",  "value": [542, 199]},
        {"name": "M205",  "value": [604, 434]},
        {"name": "M202",  "value": [639, 197]},
        {"name": "M201",  "value": [642,  99]},
        {"name": "M063",  "value": [663,  32]},
        {"name": "M051",  "value": [666, 266]},
        {"name": "P202",  "value": [776, 332]},
        {"name": "P106",  "value": [830, 278]},
        {"name": "P101",  "value": [831, 205]},
        {"name": "P002",  "value": [833, 181]},
        {"name": "S063",  "value": [833, 370]},
        {"name": "L104",  "value": [834, 143]},
        {"name": "S002",  "value": [834, 312]},
        {"name": "P204",  "value": [847, 248]},
        {"name": "P105",  "value": [881, 221]},
        {"name": "P003",  "value": [893, 323]},
        {"name": "P104",  "value": [900, 113]},
        {"name": "S051",  "value": [923, 424]},
        {"name": "P102",  "value": [944,  71]},
        {"name": "S001",  "value": [980, 397]},
        {"name": "P001",  "value": [996, 302]},
        {"name": "P103",  "value": [997, 233]},
        {"name": "P201",  "value": [998, 104]},
        {"name": "L105",  "value": [1036, 424]},
        {"name": "P203",  "value": [1064,  72]},
    ],
    "K60_NT": [
        # R1V1 — top face
        {"name": "S052", "value": [120,  43]},
        {"name": "S054", "value": [185,  43]},
        {"name": "P000", "value": [ 70, 203]},
        {"name": "S051", "value": [140, 203]},
        {"name": "S063", "value": [210, 203]},
        # R1V2 — face 2
        {"name": "M051", "value": [420,  70]},
        {"name": "M052", "value": [325, 180]},
        {"name": "M064", "value": [525, 205]},
        # R1V3 — dua side view
        {"name": "M063", "value": [600,  65]},
        {"name": "N005", "value": [740,  53]},
        {"name": "N002", "value": [740, 115]},
        {"name": "N003", "value": [800, 120]},
        {"name": "N030", "value": [750, 163]},
        {"name": "N001", "value": [727, 205]},
        # R1V4
        {"name": "N804", "value": [895,  60]},
        # R2V5 — complex side view
        {"name": "P104", "value": [175, 285]},
        {"name": "P101", "value": [230, 285]},
        {"name": "P202", "value": [278, 285]},
        {"name": "P004", "value": [102, 315]},
        {"name": "P006", "value": [ 80, 345]},
        {"name": "P001", "value": [ 75, 370]},
        {"name": "P105", "value": [300, 318]},
        {"name": "L104", "value": [165, 365]},
        {"name": "P003", "value": [302, 362]},
        {"name": "P007", "value": [ 75, 395]},
        {"name": "L105", "value": [172, 418]},
        {"name": "P002", "value": [ 72, 428]},
        {"name": "P005", "value": [ 70, 460]},
        {"name": "P201", "value": [170, 455]},
        {"name": "P103", "value": [138, 472]},
        {"name": "P162", "value": [298, 468]},
        {"name": "S002", "value": [300, 388]},
        {"name": "S001", "value": [322, 425]},
        # R2V6 — CAM face
        {"name": "L101", "value": [570, 298]},
        {"name": "L103", "value": [603, 298]},
        {"name": "L102", "value": [635, 298]},
        {"name": "N504", "value": [465, 328]},
        {"name": "N505", "value": [493, 340]},
        {"name": "N503", "value": [455, 378]},
        {"name": "N501", "value": [475, 440]},
        {"name": "N502", "value": [530, 465]},
        {"name": "N506", "value": [653, 455]},
        # R2V7 — dua view
        {"name": "L100", "value": [735, 310]},
        {"name": "N507", "value": [738, 350]},
        {"name": "M202", "value": [890, 305]},
        {"name": "M201", "value": [858, 382]},
        {"name": "N702", "value": [842, 455]},
        {"name": "N700", "value": [882, 455]},
        {"name": "N701", "value": [905, 455]},
    ],
    "K1AL_L2_NT": [
        # V1 — top face
        {"name": "S064", "value": [121,  47]},
        {"name": "L104", "value": [175,  47]},
        {"name": "L105", "value": [215,  47]},
        {"name": "S063", "value": [260,  43]},
        {"name": "P101", "value": [295,  70]},
        {"name": "P201", "value": [ 93, 113]},
        {"name": "S003", "value": [267, 113]},
        {"name": "P202", "value": [265, 140]},
        {"name": "S002", "value": [ 93, 167]},
        {"name": "S001", "value": [262, 170]},
        {"name": "S052", "value": [ 97, 215]},
        {"name": "S051", "value": [265, 210]},
        {"name": "P000", "value": [140, 233]},
        {"name": "P001", "value": [210, 233]},
        # V2
        {"name": "M063", "value": [500,  35]},
        {"name": "M202", "value": [495, 110]},
        {"name": "M051", "value": [490, 183]},
        # V3
        {"name": "M064", "value": [668,  33]},
        {"name": "M201", "value": [672, 117]},
        {"name": "M052", "value": [672, 203]},
        {"name": "N702", "value": [860,  73]},
        {"name": "M204", "value": [810, 123]},
        {"name": "N701", "value": [858, 220]},
        # V4
        {"name": "N700", "value": [1020, 115]},
        {"name": "N703", "value": [1005, 200]},
        # V5
        {"name": "L101", "value": [ 97, 283]},
        {"name": "L103", "value": [163, 287]},
        {"name": "L102", "value": [225, 287]},
        {"name": "L100", "value": [143, 460]},
        # V6
        {"name": "S000", "value": [450, 260]},
        {"name": "M000", "value": [418, 490]},
        # V7 — KOJA face (N801 di V8 untuk NT)
        {"name": "M205", "value": [635, 360]},
        {"name": "N802", "value": [682, 455]},
        {"name": "N800", "value": [762, 453]},
        # V8
        {"name": "N801", "value": [912, 465]},
        {"name": "N005", "value": [1000, 310]},
        {"name": "N004", "value": [1000, 395]},
    ],
    "K1AL_L3_NT": [
        # V1 — top face
        {"name": "S064", "value": [121,  47]},
        {"name": "L104", "value": [175,  47]},
        {"name": "L105", "value": [215,  47]},
        {"name": "S063", "value": [260,  43]},
        {"name": "P101", "value": [295,  70]},
        {"name": "P201", "value": [ 93, 113]},
        {"name": "S003", "value": [267, 113]},
        {"name": "P202", "value": [265, 140]},
        {"name": "S002", "value": [ 93, 167]},
        {"name": "S001", "value": [262, 170]},
        {"name": "S052", "value": [ 97, 215]},
        {"name": "S051", "value": [265, 210]},
        {"name": "P000", "value": [140, 233]},
        {"name": "P001", "value": [210, 233]},
        # V2
        {"name": "M063", "value": [500,  35]},
        {"name": "M202", "value": [495, 110]},
        {"name": "M051", "value": [490, 183]},
        # V3
        {"name": "M064", "value": [668,  33]},
        {"name": "M201", "value": [672, 117]},
        {"name": "M052", "value": [672, 203]},
        {"name": "N702", "value": [860,  73]},
        {"name": "M204", "value": [810, 123]},
        {"name": "N701", "value": [858, 220]},
        # V4
        {"name": "N700", "value": [1020, 115]},
        {"name": "N703", "value": [1005, 200]},
        # V5
        {"name": "L101", "value": [ 97, 283]},
        {"name": "L103", "value": [163, 287]},
        {"name": "L102", "value": [225, 287]},
        {"name": "L100", "value": [143, 460]},
        # V6
        {"name": "S000", "value": [450, 260]},
        {"name": "M000", "value": [418, 490]},
        # V7
        {"name": "M205", "value": [635, 360]},
        {"name": "N802", "value": [682, 455]},
        {"name": "N800", "value": [762, 453]},
        # V8
        {"name": "N801", "value": [912, 465]},
        {"name": "N005", "value": [1000, 310]},
        {"name": "N004", "value": [1000, 395]},
    ],

    # ── CYL HEAD ROUGH ───────────────────────────────────────────────
    "K2SA_ROUGH": [
        {"name": "M064",  "value": [525, 456]},
        {"name": "M052",  "value": [532,  52]},
        {"name": "M063",  "value": [738, 482]},
        {"name": "M051",  "value": [739,  55]},
    ],
    "K60_ROUGH":    [],
    "K1AL_ROUGH": [
        # V1 — top face
        {"name": "S064", "value": [121,  47]},
        {"name": "L104", "value": [175,  47]},
        {"name": "L105", "value": [215,  47]},
        {"name": "P201", "value": [ 93, 113]},
        {"name": "S002", "value": [ 93, 167]},
        {"name": "S052", "value": [ 97, 215]},
        {"name": "P000", "value": [140, 233]},
        {"name": "P001", "value": [210, 233]},
        # V2
        {"name": "M063", "value": [500,  35]},
        {"name": "M202", "value": [495, 110]},
        {"name": "M051", "value": [490, 183]},
        # V3
        {"name": "M064", "value": [668,  33]},
        {"name": "M201", "value": [672, 117]},
        {"name": "M052", "value": [672, 203]},
        {"name": "N702", "value": [860,  73]},
        {"name": "M204", "value": [810, 123]},
        {"name": "N701", "value": [858, 220]},
        # V4
        {"name": "N700", "value": [1020, 115]},
        {"name": "N703", "value": [1005, 200]},
        # V5
        {"name": "L101", "value": [ 97, 283]},
        {"name": "L103", "value": [163, 287]},
        {"name": "L102", "value": [225, 287]},
        {"name": "L100", "value": [143, 460]},
        # V6
        {"name": "S000", "value": [450, 260]},
        {"name": "M000", "value": [418, 490]},
        # V7
        {"name": "N005", "value": [635, 275]},
        {"name": "M203", "value": [775, 355]},
        # V8
        {"name": "N800", "value": [950, 450]},
        {"name": "N801", "value": [990, 450]},
        {"name": "N805", "value": [1110, 350]},
        {"name": "N804", "value": [1120, 415]},
    ],

    # ── HOLDER WATER PUMP ────────────────────────────────────────────
    "K60_HWP": [
        {"name": "N004", "value": [113, 373]},
        {"name": "N007", "value": [196, 368]},
        {"name": "N000", "value": [355, 370]},
        {"name": "N006", "value": [443, 363]},
        {"name": "N005", "value": [493, 358]},
    ],
}


class DescriptivePage:
    def __init__(self, df_all: pd.DataFrame):
        self.df_all = df_all

    # ═════════════════════════════════════════════════════════════════
    #  ENTRY POINT
    # ═════════════════════════════════════════════════════════════════
    def render(self):
        # Header
        st.markdown("""
        <div class="page-hdr">
          <span class="page-title">Descriptive Analytics</span>
          <span class="page-sub">Analisis statistik data CMM</span>
        </div>
        <div class="section-desc">Eksplorasi distribusi NG · control chart · Cp/Cpk · drill-down dari Part hingga titik ukur individual.</div>
        """, unsafe_allow_html=True)

        # Inisialisasi state Quick mode
        for key, default in [
            ("desc_mode",    "quick"),   # quick | deep
            ("quick_part",   None),
            ("quick_model",  None),
            ("quick_ref",    None),
            ("quick_param",  None),
            ("active_ref",   None),      # Inisialisasi untuk Deep Investigation
            ("active_event", "marked"),
        ]:
            if key not in st.session_state:
                st.session_state[key] = default

        # Toggle bar
        self._render_mode_toggle()

        # Deteksi transisi mode. Dipakai _render_deep untuk menyinkronkan
        # periode/shift dari Quick/Dashboard HANYA saat baru berpindah ke
        # Deep — supaya selectbox periode/shift di dalam Deep tetap bisa
        # diubah pengguna (tidak ke-reset tiap render).
        _prev_mode = st.session_state.get("_desc_active_mode")
        _cur_mode  = st.session_state["desc_mode"]
        st.session_state["_desc_entered_deep"] = (_cur_mode == "deep" and _prev_mode != "deep")
        st.session_state["_desc_active_mode"]  = _cur_mode

        # Render sesuai mode
        if _cur_mode == "quick":
            self._render_quick()
        else:
            self._render_deep()

    # ═════════════════════════════════════════════════════════════════
    #  TOGGLE BAR
    # ═════════════════════════════════════════════════════════════════
    def _render_mode_toggle(self):
        mode = st.segmented_control(
            "Mode",
            options=["quick", "deep"],
            default=st.session_state["desc_mode"],
            key="desc_mode_select",
            label_visibility="collapsed",
            format_func=lambda x: "Quick" if x == "quick" else "Deep Investigation",
        )
        if mode and mode != st.session_state["desc_mode"]:
            st.session_state["desc_mode"] = mode
            st.rerun()

        _desc_mode_desc = {
            "quick": "Drill-down pareto Part → Model → Titik · terhubung ke filter Dashboard.",
            "deep":  "Analisis mendalam satu titik ukur · control chart · Cp/Cpk · deteksi 7 SPC rule.",
        }
        st.markdown(
            f'<div class="section-desc">{_desc_mode_desc[st.session_state["desc_mode"]]}</div>',
            unsafe_allow_html=True
        )

    # ═════════════════════════════════════════════════════════════════
    #  QUICK MODE — drill-down pareto
    # ═════════════════════════════════════════════════════════════════
    def _render_quick(self):
        # ── Sync filter Deep → Quick (selectbox → pills) ──────────────
        p = "shared"
        time_map_rev  = {"Hari Ini":"Hari Ini","7 Hari Terakhir":"7 Hari Terakhir","30 Hari Terakhir":"30 Hari Terakhir",
                         "Semua Periode":"Semua Periode","Custom":"Custom"}
        shift_map_rev = {"Semua Shift":"All","1":"S1","2":"S2","3":"S3"}
        deep_time  = st.session_state.get(f"{p}_time")
        deep_shift = st.session_state.get(f"{p}_shift")
        if deep_time  and deep_time  in time_map_rev:
            st.session_state[f"{p}_dash_time"]  = time_map_rev[deep_time]
        if deep_shift and str(deep_shift) in shift_map_rev:
            st.session_state[f"{p}_dash_shift"] = shift_map_rev[str(deep_shift)]

        filters = build_filters_quick(self.df_all, session_prefix="shared")
        df      = apply_filters(self.df_all, filters)

        # ── Label periode untuk judul chart (Quick mode) ──────────────
        _f_shift = filters["shift"]
        _f_d1    = filters["d1"]
        _f_d2    = filters["d2"]
        _shift_str = f"Shift {_f_shift}" if _f_shift != "Semua Shift" else "Semua Shift"
        _date_str  = f"{_f_d1.strftime('%d %b')}" if _f_d1 == _f_d2 else f"{_f_d1.strftime('%d %b')} - {_f_d2.strftime('%d %b %Y')}"
        self._quick_periode_title = f"({_date_str} | {_shift_str})"

        # Filter KP
        if df.empty:
            st.info("Tidak ada data untuk periode yang dipilih. Coba ubah filter di atas.")
            return

        # Routing level (5 level)
        part  = st.session_state["quick_part"]
        model = st.session_state["quick_model"]
        ref   = st.session_state["quick_ref"]
        param = st.session_state["quick_param"]

        # Auto-reset kalau data tidak ada untuk drill-down aktif
        if part and df[df["PartName"]==part].empty:
            self._bc_navigate(0); st.rerun()
        elif model and df[(df["PartName"]==part)&(df["ModelName"]==model)].empty:
            self._bc_navigate(1); st.rerun()
        elif ref and df[(df["PartName"]==part)&(df["ModelName"]==model)&
                        (df["ref"].astype(str).str.upper()==str(ref).upper())].empty:
            self._bc_navigate(2); st.rerun()

        # Tombol Back + Breadcrumb (display-only, tidak bisa diklik)
        _can_back_q = bool(part or model or ref or param)
        if _can_back_q:
            _qcols = st.columns([9, 1])
            with _qcols[1]:
                if st.button("Kembali", key="quick_back_btn", use_container_width=True):
                    if param:
                        st.session_state["quick_param"] = None
                    elif ref:
                        st.session_state["quick_ref"]   = None
                    elif model:
                        st.session_state["quick_model"] = None
                    elif part:
                        st.session_state["quick_part"]  = None
                    st.rerun()
        self._render_quick_breadcrumb()

        if not part:
            self._quick_level1_part(df)
        elif not model:
            self._quick_level2_model(df)
        elif not ref:
            self._quick_level3_ref(df)
        elif not param:
            self._quick_level4_param(df)
        else:
            self._quick_level5_detail(df)

    # ── Filter shared dari Dashboard (DEPRECATED — sekarang pakai build_filters_dashboard) ─
    def _apply_shared_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply filter yang sama seperti Dashboard (date, shift, part·model)."""
        mask = pd.Series(True, index=df.index)

        # Date dari session
        d1 = st.session_state.get("shared_d1")
        d2 = st.session_state.get("shared_d2")
        for k in st.session_state:
            if k.startswith("d1_shared_"):
                d1 = st.session_state[k]
            elif k.startswith("d2_shared_"):
                d2 = st.session_state[k]

        if d1 and d2:
            mask &= (df["Date"].dt.date >= d1) & (df["Date"].dt.date <= d2)

        # Shift
        shift = st.session_state.get("shared_shift", "Semua Shift")
        if str(shift) != "Semua Shift":
            shift_val = {"S1": "1", "S2": "2", "S3": "3"}.get(shift, shift)
            mask &= df["Shift"].astype(str) == str(shift_val)

        # Part · Model
        combo = st.session_state.get("shared_combo", "Semua Part")
        if combo and combo != "Semua Part":
            parts = combo.split(" · ", 1)
            mask &= df["PartName"] == parts[0]
            if len(parts) > 1:
                mask &= df["ModelName"] == parts[1]

        return df[mask]

    # ── Breadcrumb display-only (Quick) ────────────────────────────────
    def _render_quick_breadcrumb(self):
        """Breadcrumb teks saja — tidak bisa diklik, navigasi via tombol Back."""
        part  = st.session_state.get("quick_part")
        model = st.session_state.get("quick_model")
        ref   = st.session_state.get("quick_ref")
        param = st.session_state.get("quick_param")

        items = ["Semua Part"]
        if part:  items.append(part)
        if model: items.append(model)
        if ref:   items.append(ref)
        if param: items.append(param)

        bc = " <span style='color:#CBD5E1;'>›</span> ".join([
            f"<span style='color:{'#0F172A;font-weight:600' if i == len(items)-1 else '#64748B'};'>{x}</span>"
            for i, x in enumerate(items)
        ])
        st.markdown(
            f'<div style="font-size:12px;margin-bottom:6px;padding-top:6px;">{bc}</div>',
            unsafe_allow_html=True,
        )

    def _bc_navigate(self, level: int):
        """Reset state ke level tertentu — dipakai oleh auto-reset saja."""
        if level == 0:
            st.session_state["quick_part"]  = None
            st.session_state["quick_model"] = None
            st.session_state["quick_ref"]   = None
            st.session_state["quick_param"] = None
        elif level == 1:
            st.session_state["quick_model"] = None
            st.session_state["quick_ref"]   = None
            st.session_state["quick_param"] = None
        elif level == 2:
            st.session_state["quick_ref"]   = None
            st.session_state["quick_param"] = None
        elif level == 3:
            st.session_state["quick_param"] = None

    # ── LEVEL 1 — Pareto per Part ────────────────────────────────────
    def _quick_level1_part(self, df: pd.DataFrame):
        import json as _json_l1
        # Semua part (termasuk 0 NG)
        all_parts = sorted([p for p in self.df_all["PartName"].dropna().astype(str).unique()
                            if p.strip() not in ["-",""]])
        ng_per_part = (df[df["Judgement"] == "NG"]
                       .groupby("PartName").size()
                       .reindex(all_parts, fill_value=0)
                       .sort_values(ascending=False))

        # Hover per bulan
        month_dist_p = {}
        if "Date" in df.columns:
            df_ng_all = df[df["Judgement"] == "NG"].copy()
            df_ng_all["_month"] = pd.to_datetime(df_ng_all["Date"], errors="coerce").dt.strftime("%b %Y")
            for p_ in all_parts:
                sub = df_ng_all[df_ng_all["PartName"] == p_]
                month_dist_p[p_] = {str(k): int(v)
                    for k, v in sub.groupby("_month").size().items()}
        mth_js_p = _json_l1.dumps(month_dist_p, ensure_ascii=False)

        labels_p  = ng_per_part.index.astype(str).tolist()
        values_p  = [int(v) for v in ng_per_part.values]
        n_bars_p  = len(labels_p)
        end_pct_p = min(100, round(10 / max(n_bars_p, 1) * 100))

        _tt_p = ("function(p){"
                 "var nm=p[0].name,v=p[0].value;"
                 "var d=(" + mth_js_p + ")[nm]||{};"
                 "var keys=Object.keys(d);"
                 "var ds=keys.length"
                 "?keys.map(function(k){return k+': '+d[k];}).join('<br/>')"
                 ":'—';"
                 "return '<b>'+nm+'</b><br/>Total NG: '+v+'<br/><hr style=margin:4px/>'+ds;}")

        _ev_part = st_echarts(options={
            "title": {"text": "NG per Part",
                      "subtext": f"Total {ng_per_part.sum()} NG · {n_bars_p} part — {self._quick_periode_title}",
                      "left": 14, "top": 12,
                      "textStyle": {"fontSize": 14, "fontWeight": 700, "color": "#0F172A"},
                      "subtextStyle": {"fontSize": 11, "color": "#64748B"}},
            "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
            "grid": {"top": 62, "right": 60, "bottom": 16, "left": 20, "containLabel": True},
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"},
                        "backgroundColor": "#1E293B", "borderColor": "#334155",
                        "textStyle": {"color": "#F8FAFC"}, "formatter": JsCode(_tt_p)},
            "dataZoom": ([
                {"type": "slider", "yAxisIndex": 0, "orient": "vertical", "right": 8,
                 "start": 100-end_pct_p, "end": 100, "width": 12,
                 "borderColor": "transparent", "backgroundColor": "#F1F5F9",
                 "fillerColor": "#CBD5E1", "handleStyle": {"color": "#94A3B8"},
                 "showDetail": False, "showDataShadow": False},
                {"type": "inside", "yAxisIndex": 0, "start": 100-end_pct_p, "end": 100,
                 "zoomOnMouseWheel": False, "moveOnMouseWheel": True},
            ] if n_bars_p > 10 else []),
            "xAxis": {"type": "value",
                      "axisLabel": {"fontSize": 10, "color": "#94A3B8"},
                      "axisLine": {"show": False}, "axisTick": {"show": False},
                      "splitLine": {"lineStyle": {"color": "#F1F5F9", "type": "dashed"}}},
            "yAxis": {"type": "category", "data": list(reversed(labels_p)),
                      "axisLabel": {"fontSize": 12, "fontWeight": 600, "color": "#334155"},
                      "axisTick": {"show": False},
                      "axisLine": {"lineStyle": {"color": "#E2E8F0"}}},
            "series": [{"name": "NG", "type": "bar",
                        "data": list(reversed(values_p)),
                        "barMaxWidth": 28, "cursor": "pointer",
                        "itemStyle": {"color": "#EF4444", "borderRadius": [0,6,6,0]},
                        "label": {"show": True, "position": "right", "formatter": "{c}",
                                  "fontSize": 12, "fontWeight": 700,
                                  "color": "#0F172A", "distance": 6},
                        "emphasis": {"itemStyle": {"shadowBlur": 8,
                                                   "shadowColor": "rgba(0,0,0,0.15)"}}}],
        }, events={"click": "function(p){ return {name: p.name, value: p.value}; }"},
           height="380px", key="quick_pareto_part")

        # Gunakan return value langsung (Pattern B) — bukan session_state agar tidak re-fire saat back
        if _ev_part:
            if isinstance(_ev_part, dict):
                _nm = _ev_part.get("name") or (_ev_part.get("chart_event") or {}).get("name")
                if _nm:
                    st.session_state["quick_part"] = _nm
                    st.rerun()

        # ── Charts konteks ───────────────────────────────────────────
        df_trend = df.copy()
        df_trend["_d"] = df_trend["Date"].dt.strftime("%d %b")
        tc = pd.crosstab(df_trend["_d"], df_trend["Judgement"])
        if "OK" not in tc.columns: tc["OK"] = 0
        if "NG" not in tc.columns: tc["NG"] = 0


        # ── Trend OK% dengan switch Line/Bar ─────────────────────────
        q1_type = st.pills("Chart L1", ["Line","Bar"], default="Line",
                           key="q1_chart_type", selection_mode="single",
                           label_visibility="collapsed") or "Line"

        COLORS = ["#6366F1","#F59E0B","#10B981","#EF4444","#8B5CF6","#06B6D4"]
        parts_avail = sorted(df["PartName"].dropna().unique().tolist())

        if q1_type == "Bar":
            # Bar: OK vs NG per Part (no time)
            _l1_ok_pct, _l1_ng_pct = [], []
            _l1_ok_cnt, _l1_ng_cnt = [], []
            for p in parts_avail:
                _g = df[df["PartName"]==p]; _t = len(_g)
                _ok = int((_g["Judgement"]=="OK").sum())
                _ng = int((_g["Judgement"]=="NG").sum())
                _l1_ok_pct.append(round(_ok/_t*100,1) if _t else 0)
                _l1_ng_pct.append(round(_ng/_t*100,1) if _t else 0)
                _l1_ok_cnt.append(_ok)
                _l1_ng_cnt.append(_ng)
            import json as _jl1
            _l1_ok_js = _jl1.dumps(_l1_ok_cnt)
            _l1_ng_js = _jl1.dumps(_l1_ng_cnt)
            _l1_parts_js = _jl1.dumps(parts_avail)
            _tt_l1_bar = JsCode(
                "function(p){"
                "var ok_cnt="+_l1_ok_js+";var ng_cnt="+_l1_ng_js+";"
                "var idx=p[0].dataIndex;"
                "var ok=ok_cnt[idx],ng=ng_cnt[idx],tot=ok+ng;"
                "return '<b>'+p[0].axisValue+'</b><br/>"
                "OK: <b style=color:#22C55E;>'+ok+'</b> ('+p[0].value+'%)<br/>"
                "NG: <b style=color:#EF4444;>'+ng+'</b> ('+(p[1]?p[1].value:0)+'%)<br/>"
                "Total: <b>'+tot+'</b>';}"
            )
            st_echarts({
                "title": {"text": "OK% vs NG% per Part",
                          "subtext": self._quick_periode_title,
                          "textStyle": {"fontSize": 13, "fontWeight": 700}},
                "tooltip": {"trigger": "axis", "formatter": _tt_l1_bar},
                "legend": {"data": ["OK%","NG%"], "top": 8, "right": 8,
                           "icon": "circle", "itemWidth": 8, "textStyle": {"fontSize": 11}},
                "grid": {"top": 48, "bottom": 32, "left": 48, "right": 20},
                "xAxis": {"type": "category", "data": parts_avail, "axisLabel": {"fontSize": 10}},
                "yAxis": {"type": "value", "max": 100, "axisLabel": {"formatter": "{value}%", "fontSize": 10}},
                "series": [
                    {"name": "OK%", "type": "bar", "stack": "t", "data": _l1_ok_pct,
                     "itemStyle": {"color": "#22C55E"},
                     "label": {"show": True, "position": "inside", "formatter": "{c}%", "fontSize": 9, "color": "#fff"}},
                    {"name": "NG%", "type": "bar", "stack": "t", "data": _l1_ng_pct,
                     "itemStyle": {"color": "#EF4444", "borderRadius": [4,4,0,0]},
                     "label": {"show": True, "position": "inside", "formatter": "{c}%", "fontSize": 9, "color": "#fff"}},
                ],
            "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
            }, height="260px", key="q1_trend")
        else:
            df_t = df.copy().sort_values("Date")
            df_t["_d"] = df_t["Date"].dt.strftime("%d %b")
            x_labels = df_t["_d"].unique().tolist()
            # Siapkan data OK/NG count per part per tanggal untuk tooltip
            import json as _jl1l
            _ok_map, _ng_map = {}, {}
            for pn in parts_avail:
                df_p = df_t[df_t["PartName"]==pn]
                tc   = pd.crosstab(df_p["_d"], df_p["Judgement"]).reindex(x_labels).fillna(0)
                if "OK" not in tc.columns: tc["OK"] = 0
                if "NG" not in tc.columns: tc["NG"] = 0
                _ok_map[pn] = tc["OK"].astype(int).tolist()
                _ng_map[pn] = tc["NG"].astype(int).tolist()
            _ok_map_js = _jl1l.dumps(_ok_map)
            _ng_map_js = _jl1l.dumps(_ng_map)
            _tt_l1_line = JsCode(
                "function(p){"
                "var ok_m="+_ok_map_js+";var ng_m="+_ng_map_js+";"
                "var idx=p[0].dataIndex;"
                "var lines='<b>'+p[0].axisValue+'</b><br/>';"
                "p.forEach(function(s){"
                "var ok=ok_m[s.seriesName]?ok_m[s.seriesName][idx]:0;"
                "var ng=ng_m[s.seriesName]?ng_m[s.seriesName][idx]:0;"
                "lines+=s.marker+s.seriesName+': <b>'+s.value+'%</b>"
                " (OK:'+ok+' NG:'+ng+')<br/>';"
                "});return lines;}"
            )
            series_l1 = []
            for i, pn in enumerate(parts_avail):
                df_p = df_t[df_t["PartName"]==pn]
                tc   = pd.crosstab(df_p["_d"], df_p["Judgement"])
                if "OK" not in tc.columns: tc["OK"] = 0
                if "NG" not in tc.columns: tc["NG"] = 0
                tc  = tc.reindex(x_labels).fillna(0)
                pct = (tc["OK"]/(tc["OK"]+tc["NG"])*100).round(1).fillna(0).tolist()
                series_l1.append({
                    "name": pn, "type": "line", "smooth": True,
                    "data": pct, "areaStyle": {"opacity": .08},
                    "itemStyle": {"color": COLORS[i%len(COLORS)]},
                    "symbol": "circle", "symbolSize": 5,
                })
            st_echarts({
                "title": {"text": "Trend OK%", "subtext": "Per Part",
                          "textStyle": {"fontSize": 13, "fontWeight": 700}},
                "tooltip": {"trigger": "axis", "formatter": _tt_l1_line},
                "legend": {"data": parts_avail, "top": 8, "right": 8,
                           "icon": "circle", "itemWidth": 8,
                           "textStyle": {"fontSize": 11}},
                "grid": {"top": 48, "bottom": 32, "left": 52, "right": 20},
                "xAxis": {"type": "category", "boundaryGap": False,
                          "data": x_labels, "axisLabel": {"fontSize": 10}},
                "yAxis": {"type": "value", "min": 0, "max": 100,
                          "axisLabel": {"formatter": "{value}%", "fontSize": 10}},
                "dataZoom": [{"type": "inside"}],
                "series": series_l1,
            "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
            }, height="260px", key="q1_trend")

    # ── LEVEL 2 — Pareto per Model (dalam part terpilih) ─────────────
    def _quick_level2_model(self, df: pd.DataFrame):
        part = st.session_state["quick_part"]
        df_p = df[df["PartName"] == part]

        # Semua model (termasuk 0 NG)
        all_models_l2 = sorted([m for m in
                                self.df_all[self.df_all["PartName"]==part]
                                ["ModelName"].dropna().astype(str).unique()
                                if m.strip() not in ["-",""]])
        ng_per_model = (df_p[df_p["Judgement"] == "NG"]
                        .groupby("ModelName").size()
                        .reindex(all_models_l2, fill_value=0)
                        .sort_values(ascending=False))

        # ── Hover per bulan ─────────────────────────────────────────────
        import json as _json_l2
        month_dist = {}
        if "Date" in df_p.columns:
            df_ng_p = df_p[df_p["Judgement"] == "NG"].copy()
            df_ng_p["_month"] = pd.to_datetime(df_ng_p["Date"], errors="coerce").dt.strftime("%b %Y")
            for mdl in ng_per_model.index:
                sub = df_ng_p[df_ng_p["ModelName"] == mdl]
                month_dist[str(mdl)] = {str(k): int(v)
                    for k, v in sub.groupby("_month").size().items()}
        mth_js = _json_l2.dumps(month_dist, ensure_ascii=False)

        labels_m  = ng_per_model.index.astype(str).tolist()
        values_m  = [int(v) for v in ng_per_model.values]
        n_bars_m  = len(labels_m)
        end_pct_m = min(100, round(10 / max(n_bars_m, 1) * 100))

        _tt_m = ("function(p){"
                 "var nm=p[0].name,v=p[0].value;"
                 "var d=(" + mth_js + ")[nm]||{};"
                 "var keys=Object.keys(d);"
                 "var ds=keys.length"
                 "?keys.map(function(k){return k+': '+d[k];}).join('<br/>')"
                 ":'—';"
                 "return '<b>'+nm+'</b><br/>Total NG: '+v+'<br/><hr style=margin:4px/>'+ds;}")

        _ev_model = st_echarts(options={
            "title": {"text": f"NG per Model — {part}",
                      "subtext": f"Total {ng_per_model.sum()} NG · {n_bars_m} model — {self._quick_periode_title}",
                      "left": 14, "top": 12,
                      "textStyle": {"fontSize": 14, "fontWeight": 700, "color": "#0F172A"},
                      "subtextStyle": {"fontSize": 11, "color": "#64748B"}},
            "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
            "grid": {"top": 62, "right": 60, "bottom": 16, "left": 20, "containLabel": True},
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"},
                        "backgroundColor": "#1E293B", "borderColor": "#334155",
                        "textStyle": {"color": "#F8FAFC"}, "formatter": JsCode(_tt_m)},
            "dataZoom": ([
                {"type": "slider", "yAxisIndex": 0, "orient": "vertical", "right": 8,
                 "start": 100-end_pct_m, "end": 100, "width": 12,
                 "borderColor": "transparent", "backgroundColor": "#F1F5F9",
                 "fillerColor": "#CBD5E1", "handleStyle": {"color": "#94A3B8"},
                 "showDetail": False, "showDataShadow": False},
                {"type": "inside", "yAxisIndex": 0, "start": 100-end_pct_m, "end": 100,
                 "zoomOnMouseWheel": False, "moveOnMouseWheel": True},
            ] if n_bars_m > 10 else []),
            "xAxis": {"type": "value",
                      "axisLabel": {"fontSize": 10, "color": "#94A3B8"},
                      "axisLine": {"show": False}, "axisTick": {"show": False},
                      "splitLine": {"lineStyle": {"color": "#F1F5F9", "type": "dashed"}}},
            "yAxis": {"type": "category", "data": list(reversed(labels_m)),
                      "axisLabel": {"fontSize": 12, "fontWeight": 600, "color": "#334155"},
                      "axisTick": {"show": False},
                      "axisLine": {"lineStyle": {"color": "#E2E8F0"}}},
            "series": [{"name": "NG", "type": "bar",
                        "data": list(reversed(values_m)),
                        "barMaxWidth": 28, "cursor": "pointer",
                        "itemStyle": {"color": "#F59E0B", "borderRadius": [0,6,6,0]},
                        "label": {"show": True, "position": "right", "formatter": "{c}",
                                  "fontSize": 12, "fontWeight": 700,
                                  "color": "#0F172A", "distance": 6},
                        "emphasis": {"itemStyle": {"shadowBlur": 8,
                                                   "shadowColor": "rgba(0,0,0,0.15)"}}}],
        }, events={"click": "function(p){ return {name: p.name, value: p.value}; }"},
           height="380px", key="quick_pareto_model")

        # Gunakan return value langsung (Pattern B) — bukan session_state agar tidak re-fire saat back
        if _ev_model:
            if isinstance(_ev_model, dict):
                _nm = _ev_model.get("name") or (_ev_model.get("chart_event") or {}).get("name")
                if _nm:
                    st.session_state["quick_model"] = _nm
                    st.rerun()



        # ── Cakupan Titik Ukur per Model (semua model di part ini) ──────
        if "Category" in df_p.columns:
            # Semua model di part ini (dari df_all, bukan hanya yang ada di filter)
            all_models_p = sorted([m for m in
                                   self.df_all[self.df_all["PartName"]==part]
                                   ["ModelName"].dropna().unique()
                                   if str(m).strip() not in ["-",""]])
            cov_data = []
            for m_ in all_models_p:
                _d_m = self.df_all[
                    (self.df_all["PartName"] == part) &
                    (self.df_all["ModelName"] == m_)
                ]
                def _u(cat, _d=_d_m):
                    cols = [c for c in ["ID","Parameter","point"]
                            if c in _d.columns]
                    return _d[_d["Category"]==cat][cols].drop_duplicates().shape[0] if cols else 0
                n_prod_ = _u("Produksi")
                n_qis_  = _u("QIS")
                cov_data.append({"model": m_, "prod": n_prod_, "waste": n_qis_,
                                 "total": n_prod_ + n_qis_})
            if cov_data:
                st.markdown(
                    '<div style="font-size:13px;font-weight:700;color:#0F172A;'
                    'margin:16px 0 6px;">Cakupan Titik Ukur per Model</div>',
                    unsafe_allow_html=True)
                x_cov  = [c["model"] for c in cov_data]
                y_prod = [c["prod"]  for c in cov_data]
                y_wst  = [c["waste"] for c in cov_data]
                y_tot  = [c["total"] for c in cov_data]
                st_echarts({
                    "tooltip": {"trigger": "axis",
                                "axisPointer": {"type": "shadow"}},
                    "legend": {"data": ["Total","Waste","Produksi"], "bottom": 0,
                               "icon": "roundRect", "itemWidth": 12,
                               "textStyle": {"fontSize": 11}},
                    "grid": {"top": 16, "bottom": 44, "left": 16, "right": 16,
                             "containLabel": True},
                    "xAxis": {"type": "category", "data": x_cov,
                              "axisLabel": {"fontSize": 11, "fontWeight": 600,
                                            "interval": 0, "rotate": 20}},
                    "yAxis": {"type": "value", "show": False},
                    "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
                    "series": [
                        {"name": "Total", "type": "bar", "data": y_tot,
                         "barWidth": "28%", "barGap": "8%",
                         "itemStyle": {"color": "#3B82F6", "borderRadius": [4,4,0,0]},
                         "label": {"show": True, "position": "top",
                                   "fontSize": 11, "fontWeight": 700, "color": "#0F172A"}},
                        {"name": "Waste", "type": "bar", "stack": "bd", "data": y_wst,
                         "barWidth": "28%",
                         "itemStyle": {"color": "#1D9E75", "borderRadius": [4,4,0,0]},
                         "label": {"show": True, "position": "inside",
                                   "formatter": "Waste\n{c}", "fontSize": 10,
                                   "fontWeight": 700, "color": "#fff"}},
                        {"name": "Produksi", "type": "bar", "stack": "bd", "data": y_prod,
                         "barWidth": "28%",
                         "itemStyle": {"color": "#F59E0B", "borderRadius": [0,0,0,0]},
                         "label": {"show": True, "position": "inside",
                                   "formatter": "Produksi\n{c}", "fontSize": 10,
                                   "fontWeight": 700, "color": "#fff"}},
                    ],
                }, height="260px", key="q2_cakupan")

        # ── Trend OK% per Model dengan switch Line/Bar ───────────────
        q2_type = st.pills("Chart L2", ["Line","Bar"], default="Line",
                           key="q2_chart_type", selection_mode="single",
                           label_visibility="collapsed") or "Line"

        COLORS = ["#6366F1","#F59E0B","#10B981","#EF4444","#8B5CF6","#06B6D4"]
        models_avail = sorted(df_p["ModelName"].dropna().unique().tolist())

        if q2_type == "Bar":
            _l2_ok_pct, _l2_ng_pct = [], []
            _l2_ok_cnt, _l2_ng_cnt = [], []
            for m in models_avail:
                _g = df_p[df_p["ModelName"]==m]; _t = len(_g)
                _ok = int((_g["Judgement"]=="OK").sum())
                _ng = int((_g["Judgement"]=="NG").sum())
                _l2_ok_pct.append(round(_ok/_t*100,1) if _t else 0)
                _l2_ng_pct.append(round(_ng/_t*100,1) if _t else 0)
                _l2_ok_cnt.append(_ok)
                _l2_ng_cnt.append(_ng)
            import json as _jl2
            _tt_l2_bar = JsCode(
                "function(p){"
                "var ok_cnt="+_jl2.dumps(_l2_ok_cnt)+";var ng_cnt="+_jl2.dumps(_l2_ng_cnt)+";"
                "var idx=p[0].dataIndex;"
                "var ok=ok_cnt[idx],ng=ng_cnt[idx],tot=ok+ng;"
                "return '<b>'+p[0].axisValue+'</b><br/>"
                "OK: <b style=color:#22C55E;>'+ok+'</b> ('+p[0].value+'%)<br/>"
                "NG: <b style=color:#EF4444;>'+ng+'</b> ('+(p[1]?p[1].value:0)+'%)<br/>"
                "Total: <b>'+tot+'</b>';}"
            )
            st_echarts({
                "title": {"text": f"OK vs NG per Model — {part}",
                          "subtext": self._quick_periode_title,
                          "textStyle": {"fontSize": 13, "fontWeight": 700}},
                "tooltip": {"trigger": "axis", "formatter": _tt_l2_bar},
                "legend": {"data": ["OK%","NG%"], "top": 8, "right": 8,
                           "icon": "circle", "itemWidth": 8, "textStyle": {"fontSize": 11}},
                "grid": {"top": 48, "bottom": 32, "left": 48, "right": 20},
                "xAxis": {"type": "category", "data": models_avail,
                          "axisLabel": {"fontSize": 10}},
                "yAxis": {"type": "value", "max": 100, "axisLabel": {"formatter": "{value}%", "fontSize": 10}},
                "series": [
                    {"name": "OK%", "type": "bar", "stack": "t", "data": _l2_ok_pct,
                     "itemStyle": {"color": "#22C55E"},
                     "label": {"show": True, "position": "inside", "formatter": "{c}%", "fontSize": 9, "color": "#fff"}},
                    {"name": "NG%", "type": "bar", "stack": "t", "data": _l2_ng_pct,
                     "itemStyle": {"color": "#EF4444", "borderRadius": [4,4,0,0]},
                     "label": {"show": True, "position": "inside", "formatter": "{c}%", "fontSize": 9, "color": "#fff"}},
                ],
            "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
            }, height="260px", key="q2_trend")
        else:
            df_t = df_p.copy().sort_values("Date")
            n_dates = df_t["Date"].dt.date.nunique()
            df_t["_d"] = df_t["Date"].dt.strftime("%d %b")
            x_labels = df_t["_d"].unique().tolist()
            subtext = "Per Hari"
            def _get_x(df_m):
                df_m = df_m.copy(); df_m["_d"] = df_m["Date"].dt.strftime("%d %b")
                tc = pd.crosstab(df_m["_d"], df_m["Judgement"])
                return tc.reindex(x_labels).fillna(0)

            import json as _jl2l
            _ok_map_l2, _ng_map_l2 = {}, {}
            series_l2 = []
            for i, mn in enumerate(models_avail):
                tc = _get_x(df_t[df_t["ModelName"]==mn])
                if "OK" not in tc.columns: tc["OK"] = 0
                if "NG" not in tc.columns: tc["NG"] = 0
                _ok_map_l2[mn] = tc["OK"].astype(int).tolist()
                _ng_map_l2[mn] = tc["NG"].astype(int).tolist()
                pct = (tc["OK"]/(tc["OK"]+tc["NG"])*100).round(1).fillna(0).tolist()
                series_l2.append({
                    "name": mn, "type": "line", "smooth": True,
                    "data": pct, "areaStyle": {"opacity": .08},
                    "itemStyle": {"color": COLORS[i%len(COLORS)]},
                    "symbol": "circle", "symbolSize": 5,
                })
            _tt_l2_line = JsCode(
                "function(p){"
                "var ok_m="+_jl2l.dumps(_ok_map_l2)+";var ng_m="+_jl2l.dumps(_ng_map_l2)+";"
                "var idx=p[0].dataIndex;"
                "var lines='<b>'+p[0].axisValue+'</b><br/>';"
                "p.forEach(function(s){"
                "var ok=ok_m[s.seriesName]?ok_m[s.seriesName][idx]:0;"
                "var ng=ng_m[s.seriesName]?ng_m[s.seriesName][idx]:0;"
                "lines+=s.marker+s.seriesName+': <b>'+s.value+'%</b>"
                " (OK:'+ok+' NG:'+ng+')<br/>';"
                "});return lines;}"
            )
            st_echarts({
                "title": {"text": f"Trend OK% — {part}", "subtext": subtext,
                          "textStyle": {"fontSize": 13, "fontWeight": 700}},
                "tooltip": {"trigger": "axis", "formatter": _tt_l2_line},
                "legend": {"data": models_avail, "top": 8, "right": 8,
                           "icon": "circle", "itemWidth": 8, "textStyle": {"fontSize": 11}},
                "grid": {"top": 48, "bottom": 32, "left": 52, "right": 20},
                "xAxis": {"type": "category", "boundaryGap": False, "data": x_labels,
                          "axisLabel": {"fontSize": 10, "interval": "auto"}},
                "yAxis": {"type": "value", "min": 0, "max": 100,
                          "axisLabel": {"formatter": "{value}%", "fontSize": 10}},
                "dataZoom": [{"type": "inside"}],
                "series": series_l2,
            "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
            }, height="260px", key="q2_trend")

    # ── LEVEL 3 — Pareto per Ref/Titik ───────────────────────────────
    def _quick_level3_ref(self, df: pd.DataFrame):
        part  = st.session_state["quick_part"]
        model = st.session_state["quick_model"]
        df_pm = df[(df["PartName"] == part) & (df["ModelName"] == model)]

        # Semua titik ukur (termasuk 0 NG)
        all_refs = sorted(
            [r for r in self.df_all[
                (self.df_all["PartName"]==part) &
                (self.df_all["ModelName"]==model)
            ]["ref"].dropna().astype(str).unique()
             if r.strip() not in ["-",""]],
            key=lambda x: (0, int(x[1:])) if (len(x)>1 and x[1:].isdigit()) else (1, x)
        )
        ng_per_ref = (df_pm[df_pm["Judgement"] == "NG"]
                      .groupby("ref").size()
                      .reindex(all_refs, fill_value=0)
                      .sort_values(ascending=False))

        # ── Skema Quick — ECharts scatter, pop key sebelum render ────
        active_key  = _detect_active_key(part, model)
        img_path_q3 = _get_image_path(active_key)

        # snos untuk trend chart
        snos = sorted(df_pm["SampleNo"].dropna().astype(str).unique().tolist(),
                      key=lambda s: (0,int(s)) if s.isdigit() else (1,s))

        if img_path_q3 and active_key in COORD_DB:
            # Pop SEBELUM render — cegah corrupt pills + infinite rerun
            prev_click = st.session_state.pop("q3_schema_quick", None)

            ORIG_W = 1280
            ORIG_H = ORIG_H_MAP.get(active_key, 500)
            DISP_W = 1200
            DISP_H = int(DISP_W * ORIG_H / ORIG_W)

            img_b64_q3 = "data:image/png;base64," + \
                __import__("base64").b64encode(
                    open(str(img_path_q3),"rb").read()
                ).decode()

            _all_r = [r for r in df_pm["ref"].dropna().astype(str).unique()
                      if r.strip() not in ["-",""]]
            _n_t  = len(_all_r)
            _n_ng = int((df_pm["Judgement"] == "NG").sum())
            _n_kp = _n_kpng = 0
            if "KP" in df_pm.columns:
                _km = df_pm["KP"].astype(str).str.strip().isin(["1","True","true","KP"])
                _n_kp   = int(df_pm[_km]["ref"].nunique())
                _n_kpng = int((df_pm["Judgement"].eq("NG") & _km).sum())
            _sch_sub = (f"Titik: {_n_t}  |  KP: {_n_kp}  |"
                        f"  Total NG: {_n_ng}  |  KP NG: {_n_kpng}")

            points_data = []
            for pt in COORD_DB[active_key]:
                ref_name = pt["name"].upper()
                df_pt    = df_pm[df_pm["ref"].astype(str).str.strip().str.upper()==ref_name]
                if df_pt.empty:
                    clr     = "#94A3B8"
                    tip_str = f"<b>{ref_name}</b><br/>Tidak ada data"
                else:
                    has_ng = (df_pt["Judgement"] == "NG").any()
                    clr    = "#EF4444" if has_ng else "#22C55E"
                    n_tot  = len(df_pt)
                    df_ng  = df_pt[df_pt["Judgement"] == "NG"]
                    n_ng   = len(df_ng)
                    pcol   = "point" if "point" in df_pt.columns and df_pt["point"].notna().any() else "Parameter"

                    if not has_ng:
                        tip_str = (f"<b>{ref_name}</b>"
                                   f"<br/>✓ Semua OK"
                                   f"<br/><span style='color:#94A3B8;font-size:10px;'>"
                                   f"Total: {n_tot} pengukuran</span>")
                    else:
                        # Bangun tip per-parameter: nama · count · deviasi NG terbaru
                        hr = "<br/><hr style='margin:3px 0;border-color:#334155;border-width:0.5px;'/>"
                        param_cnt = (df_ng.groupby(pcol).size().sort_values(ascending=False)
                                     if pcol in df_ng.columns else None)
                        parts = []
                        if param_cnt is not None:
                            for p, c in param_cnt.items():
                                p_str = str(p)
                                df_p  = df_ng[df_ng[pcol].astype(str) == p_str]
                                # Deviasi NG terbaru untuk parameter ini
                                df_ps = df_p.sort_values("Date", ascending=False) if "Date" in df_p.columns else df_p
                                last_dev = None
                                if "Deviation" in df_ps.columns and df_ps["Deviation"].notna().any():
                                    last_dev = round(float(df_ps["Deviation"].dropna().iloc[0]), 4)
                                elif "Actual" in df_ps.columns and "Nominal" in df_ps.columns:
                                    r0 = df_ps[df_ps["Actual"].notna() & df_ps["Nominal"].notna()]
                                    if not r0.empty:
                                        last_dev = round(float(r0.iloc[0]["Actual"] - r0.iloc[0]["Nominal"]), 4)
                                sign = "+" if last_dev is not None and last_dev >= 0 else ""
                                dev_line = (f"<br/><span style='color:#94A3B8;font-size:10px;'>"
                                            f"Deviasi NG terbaru: {sign}{last_dev}</span>"
                                            if last_dev is not None else "")
                                is_kp_p = ("KP" in df_p.columns and
                                           df_p["KP"].astype(str).str.strip()
                                           .isin(["1","True","true","KP"]).any())
                                kp_lbl  = (" <span style='color:#FBBF24;font-weight:700;'>(KP)</span>"
                                           if is_kp_p else "")
                                parts.append(f"<b>{p_str}</b>{kp_lbl} : {int(c)}{dev_line}")
                        tip_str = (f"<b>{ref_name}</b>"
                                   f"<br/>Total NG: <b style='color:#EF4444;'>{n_ng}</b>"
                                   + (hr + hr.join(parts) if parts else ""))
                points_data.append({
                    "name":  ref_name,
                    "value": pt["value"],
                    "_tip":  tip_str,
                    "itemStyle": {"color": clr, "borderColor": "#ffffff",
                                  "borderWidth": 1.5, "opacity": 0.9}
                })

            clicked_q3 = st_echarts(
                options={
                    "title": {"text": "Schematic Part View",
                              "subtext": _sch_sub,
                              "left": 16, "top": 8,
                              "textStyle": {"color": "#0F172A", "fontSize": 14, "fontWeight": 700},
                              "subtextStyle": {"color": "#64748B", "fontSize": 11}},
                    "grid":  {"left": 0, "width": DISP_W, "height": DISP_H, "top": 55, "bottom": 10},
                    "xAxis": {"show": False, "min": 0, "max": ORIG_W},
                    "yAxis": {"show": False, "min": 0, "max": ORIG_H, "inverse": True},
                    "graphic": [{"type": "image", "left": 0, "top": 55, "z": -10,
                                 "style": {"image": img_b64_q3,
                                           "width": DISP_W, "height": DISP_H}}],
                    "tooltip": {"trigger": "item",
                                "backgroundColor": "#1E293B", "borderColor": "#334155",
                                "textStyle": {"color": "#F8FAFC", "fontSize": 12},
                                "formatter": JsCode("function(p){ return p.data._tip || ('<b>'+p.name+'</b>'); }")},
                    "series": [{"type": "scatter", "symbol": "circle", "symbolSize": 12,
                                "itemStyle": {"color": "rgba(220,38,38,0.1)",
                                              "borderColor": "#DC2626", "borderWidth": 0},
                                "emphasis": {"itemStyle": {"borderColor": "#ffffff",
                                                           "borderWidth": 2},
                                             "symbolSize": 18},
                                "data": points_data}],
                },
                events={"click": """function(params) {
                    try {
                        if (params.componentSubType === 'scatter') {
                            return {name: params.name, value: params.value, type: 'marked'};
                        } else {
                            return {name: 'Area Kosong', value: [0,0], type: 'unmarked'};
                        }
                    } catch(e) { return null; }
                }"""},
                height=f"{DISP_H + 70}px",
                width=f"{DISP_W}px",
                key="q3_schema_quick",
            )

            # Semua ref bisa di-drill-down (termasuk 0 NG)
            if clicked_q3:
                if isinstance(clicked_q3, dict):
                    ev = clicked_q3.get("chart_event", clicked_q3)
                    if isinstance(ev, dict) and ev.get("type") == "marked":
                        ref_name = ev.get("name", "")
                        if ref_name:
                            st.session_state["quick_ref"] = ref_name
                            st.rerun()
                elif isinstance(clicked_q3, str) and clicked_q3 not in ("null","Area Kosong",""):
                    st.session_state["quick_ref"] = clicked_q3
                    st.rerun()

        # KP per ref
        kp_refs = set()
        if "KP" in df_pm.columns:
            kp_refs = set(df_pm[df_pm["KP"].astype(str).str.strip().isin(
                ["1","True","true","KP"])]["ref"].astype(str).unique())

        labels_r = ng_per_ref.index.astype(str).tolist()
        values_r = [int(v) for v in ng_per_ref.values]
        total_r  = max(sum(values_r), 1)

        # Distribusi NG per parameter per titik untuk tooltip
        import json as _json
        param_dist  = {}
        kp_dist_r   = {}
        param_col_r = "point" if "point" in df_pm.columns and df_pm["point"].notna().any() else "Parameter"
        for r in labels_r:
            d = df_pm[(df_pm["ref"].astype(str)==r) & (df_pm["Judgement"]=="NG")]
            param_dist[r] = {str(k): int(v)
                             for k, v in d.groupby(param_col_r).size().items()}
            kp_dist_r[r]  = (list(d[d["KP"].astype(str).str.strip()
                                      .isin(["1","True","true","KP"])]
                                  [param_col_r].astype(str).unique())
                             if "KP" in d.columns else [])
        samp_js_r = _json.dumps(param_dist, ensure_ascii=False)
        kp_js_r   = _json.dumps(kp_dist_r,  ensure_ascii=False)

        bar_colors_r = []
        for lbl in reversed(labels_r):
            idx = labels_r.index(lbl)
            v   = values_r[idx]
            if v == 0:
                bar_colors_r.append("#94A3B8")   # abu — 0 NG, tetap clickable
            elif lbl in kp_refs:
                bar_colors_r.append("#EF4444")   # merah — KP NG
            else:
                bar_colors_r.append("#3B82F6")   # biru — non-KP NG
        bar_vals_r   = list(reversed(values_r))
        clr_js_r     = _json.dumps(bar_colors_r)

        _tt_r = ("function(p){"
                 "var nm=p[0].name,v=p[0].value;"
                 "var d=(" + samp_js_r + ")[nm]||{};"
                 "var kp=(" + kp_js_r + ")[nm]||[];"
                 "var keys=Object.keys(d);"
                 "var ds=keys.length"
                 "?keys.map(function(k){"
                 "var t=kp.indexOf(k)>=0"
                 "?' <span style=color:#FBBF24;font-weight:700;>(KP)</span>':'';"
                 "return k+t+': '+d[k];}).join('<br/>')"
                 ":'—';"
                 "return '<b>'+nm+'</b><br/>Total NG: '+v+'<br/><hr style=margin:4px/>'+ds;}")
        tooltip_js_r = JsCode(_tt_r)
        color_fn_r   = JsCode("function(p){var c=" + clr_js_r + ";return c[p.dataIndex]||'#3B82F6';}")

        n_bars_r  = len(labels_r)
        end_pct_r = min(100, round(10 / max(n_bars_r, 1) * 100))
        legend_gr = [
            {"type":"group","right":90,"top":38,"children":[
                {"type":"rect","shape":{"x":0,"y":0,"width":12,"height":12},
                 "style":{"fill":"#EF4444"}},
                {"type":"text","x":16,"y":1,"style":{"text":"KP","font":"11px Arial","fill":"#334155"}},
            ]},
            {"type":"group","right":20,"top":38,"children":[
                {"type":"rect","shape":{"x":0,"y":0,"width":12,"height":12},
                 "style":{"fill":"#3B82F6"}},
                {"type":"text","x":16,"y":1,"style":{"text":"Non-KP","font":"11px Arial","fill":"#334155"}},
            ]},
        ]
        options_r = {
            "title": {"text": f"NG per Titik Ukur — {part} · {model}",
                      "subtext": self._quick_periode_title,
                      "left": 14, "top": 12,
                      "textStyle": {"fontSize": 14, "fontWeight": 700, "color": "#0F172A"}},
            "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
            "graphic": legend_gr,
            "grid": {"top": 62, "right": 60, "bottom": 16, "left": 20, "containLabel": True},
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"},
                        "backgroundColor": "#1E293B", "borderColor": "#334155",
                        "textStyle": {"color": "#F8FAFC"}, "formatter": tooltip_js_r},
            "dataZoom": ([
                {"type": "slider", "yAxisIndex": 0, "orient": "vertical", "right": 8,
                 "start": 100-end_pct_r, "end": 100, "width": 12,
                 "borderColor": "transparent", "backgroundColor": "#F1F5F9",
                 "fillerColor": "#CBD5E1", "handleStyle": {"color": "#94A3B8"},
                 "showDetail": False, "showDataShadow": False},
                {"type": "inside", "yAxisIndex": 0, "start": 100-end_pct_r, "end": 100,
                 "zoomOnMouseWheel": False, "moveOnMouseWheel": True},
            ] if n_bars_r > 10 else []),
            "xAxis": {"type": "value",
                      "axisLabel": {"fontSize": 10, "color": "#94A3B8"},
                      "axisLine": {"show": False}, "axisTick": {"show": False},
                      "splitLine": {"lineStyle": {"color": "#F1F5F9", "type": "dashed"}}},
            "yAxis": {"type": "category", "data": list(reversed(labels_r)),
                      "axisLabel": {"fontSize": 12, "fontWeight": 600, "color": "#334155"},
                      "axisTick": {"show": False},
                      "axisLine": {"lineStyle": {"color": "#E2E8F0"}}},
            "series": [{"name": "NG", "type": "bar", "data": bar_vals_r,
                        "barMaxWidth": 28, "cursor": "pointer",
                        "itemStyle": {"color": color_fn_r, "borderRadius": [0,6,6,0]},
                        "label": {"show": True, "position": "right", "formatter": "{c}",
                                  "fontSize": 12, "fontWeight": 700,
                                  "color": "#0F172A", "distance": 6},
                        "emphasis": {"itemStyle": {"shadowBlur": 8,
                                                   "shadowColor": "rgba(0,0,0,0.15)"}}}],
        }
        events_r = {"click": "function(params){ return {name: params.name, value: params.value}; }"}
        clicked_r = st_echarts(options=options_r, events=events_r,
                               height="420px", key="quick_pareto_ref")
        if clicked_r:
            name_r = None
            if isinstance(clicked_r, dict):
                name_r = clicked_r.get("name")
                if not name_r and "chart_event" in clicked_r:
                    inner_r = clicked_r["chart_event"]
                    if isinstance(inner_r, dict): name_r = inner_r.get("name")
            elif isinstance(clicked_r, str):
                name_r = clicked_r
            if name_r:
                st.session_state["quick_ref"] = name_r
                st.rerun()

        # ── Trend OK% per SampleNo + switch line/bar ─────────────────
        q3_chart_type = st.pills(
            "Tipe chart", ["Line", "Bar"],
            default="Line", key="q3_chart_type",
            selection_mode="single", label_visibility="collapsed"
        ) or "Line"

        df_t  = df_pm.copy().sort_values("Date")
        n_dates = df_t["Date"].dt.date.nunique()
        df_t["_d"] = df_t["Date"].dt.strftime("%d %b")
        x_labels   = df_t["_d"].unique().tolist()
        subtext    = "Per Hari"

        if q3_chart_type == "Bar":
            # Bar chart: OK vs NG per SampleNo (no time axis)
            snos_bar  = sorted(df_pm["SampleNo"].astype(str).unique(),
                               key=lambda s: [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", str(s))])
            ok_pct, ng_pct, tot_list = [], [], []
            ok_cnt_l3, ng_cnt_l3 = [], []
            for sno in snos_bar:
                grp = df_pm[df_pm["SampleNo"].astype(str)==sno]
                tot = len(grp)
                ok  = int((grp["Judgement"]=="OK").sum())
                ng  = int((grp["Judgement"]=="NG").sum())
                ok_pct.append(round(ok/tot*100,1) if tot else 0)
                ng_pct.append(round(ng/tot*100,1) if tot else 0)
                tot_list.append(tot)
                ok_cnt_l3.append(ok)
                ng_cnt_l3.append(ng)
            import json as _jl3
            _tt_l3_bar = JsCode(
                "function(p){"
                "var ok_cnt="+_jl3.dumps(ok_cnt_l3)+";var ng_cnt="+_jl3.dumps(ng_cnt_l3)+";"
                "var idx=p[0].dataIndex;"
                "var ok=ok_cnt[idx],ng=ng_cnt[idx],tot=ok+ng;"
                "return '<b>Sample '+p[0].axisValue+'</b><br/>"
                "OK: <b style=color:#22C55E;>'+ok+'</b> ('+p[0].value+'%)<br/>"
                "NG: <b style=color:#EF4444;>'+ng+'</b> ('+(p[1]?p[1].value:0)+'%)<br/>"
                "Total: <b>'+tot+'</b>';}"
            )
            st_echarts({
                "title": {"text": f"OK% vs NG% per Sample — {part} · {model}",
                          "subtext": self._quick_periode_title,
                          "textStyle": {"fontSize": 13, "fontWeight": 700}},
                "tooltip": {"trigger": "axis", "formatter": _tt_l3_bar},
                "legend": {"data": ["OK%","NG%"], "top": 8, "right": 8,
                           "icon": "circle", "itemWidth": 8, "textStyle": {"fontSize": 11}},
                "grid": {"top": 48, "bottom": 32, "left": 48, "right": 20},
                "xAxis": {"type": "category", "data": snos_bar,
                          "axisLabel": {"fontSize": 10}},
                "yAxis": {"type": "value", "max": 100,
                          "axisLabel": {"formatter": "{value}%", "fontSize": 10}},
                "series": [
                    {"name": "OK%", "type": "bar", "stack": "total",
                     "data": ok_pct, "itemStyle": {"color": "#22C55E", "borderRadius": [0,0,0,0]},
                     "label": {"show": True, "position": "inside", "formatter": "{c}%", "fontSize": 9, "color": "#fff"}},
                    {"name": "NG%", "type": "bar", "stack": "total",
                     "data": ng_pct, "itemStyle": {"color": "#EF4444", "borderRadius": [4,4,0,0]},
                     "label": {"show": True, "position": "inside", "formatter": "{c}%", "fontSize": 9, "color": "#fff"}},
                ],
            "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
            }, height="260px", key="q3_trend_bar")
        else:
            # Line chart: OK% per SampleNo per waktu
            COLORS = ["#6366F1","#F59E0B","#10B981","#EF4444","#8B5CF6","#06B6D4",
                      "#EC4899","#84CC16","#F97316","#14B8A6","#A78BFA","#FB923C"]
            import json as _jl3l
            _ok_map_l3, _ng_map_l3 = {}, {}
            series_l3 = []
            for i, sno in enumerate(snos):
                df_s = df_t[df_t["SampleNo"].astype(str)==sno].copy()
                df_s["_d"] = df_s["Date"].dt.strftime("%d %b")
                tc = pd.crosstab(df_s["_d"], df_s["Judgement"]).reindex(x_labels).fillna(0)
                if "OK" not in tc.columns: tc["OK"] = 0
                if "NG" not in tc.columns: tc["NG"] = 0
                _ok_map_l3[str(sno)] = tc["OK"].astype(int).tolist()
                _ng_map_l3[str(sno)] = tc["NG"].astype(int).tolist()
                pct = (tc["OK"]/(tc["OK"]+tc["NG"])*100).round(1).fillna(0).tolist()
                series_l3.append({
                    "name": str(sno), "type": "line", "smooth": True,
                    "data": pct, "areaStyle": {"opacity": .06},
                    "itemStyle": {"color": COLORS[i%len(COLORS)]},
                    "symbol": "circle", "symbolSize": 5,
                })
            _tt_l3_line = JsCode(
                "function(p){"
                "var ok_m="+_jl3l.dumps(_ok_map_l3)+";var ng_m="+_jl3l.dumps(_ng_map_l3)+";"
                "var idx=p[0].dataIndex;"
                "var lines='<b>'+p[0].axisValue+'</b><br/>';"
                "p.forEach(function(s){"
                "var ok=ok_m[s.seriesName]?ok_m[s.seriesName][idx]:0;"
                "var ng=ng_m[s.seriesName]?ng_m[s.seriesName][idx]:0;"
                "lines+=s.marker+'No.'+s.seriesName+': <b>'+s.value+'%</b>"
                " (OK:'+ok+' NG:'+ng+')<br/>';"
                "});return lines;}"
            )
            st_echarts({
                "title": {"text": f"Trend OK% — {part} · {model}", "subtext": subtext,
                          "textStyle": {"fontSize": 13, "fontWeight": 700}},
                "tooltip": {"trigger": "axis", "formatter": _tt_l3_line},
                "legend": {"data": snos, "top": 8, "right": 8,
                           "icon": "circle", "itemWidth": 8, "textStyle": {"fontSize": 11}},
                "grid": {"top": 48, "bottom": 32, "left": 52, "right": 20},
                "xAxis": {"type": "category", "boundaryGap": False,
                          "data": x_labels,
                          "axisLabel": {"fontSize": 10, "interval": "auto"}},
                "yAxis": {"type": "value", "min": 0, "max": 100,
                          "axisLabel": {"formatter": "{value}%", "fontSize": 10}},
                "toolbox": {"feature": {"magicType": {"type": ["line","bar"]}, "saveAsImage": {"title": "Download PNG"}}},
                "dataZoom": [{"type": "inside"}],
                "series": series_l3,
            }, height="260px", key="q3_trend_line")



    # ── LEVEL 4 — Pareto per Parameter ───────────────────────────────
    def _quick_level4_param(self, df: pd.DataFrame):
        part  = st.session_state["quick_part"]
        model = st.session_state["quick_model"]
        ref   = st.session_state["quick_ref"]

        df_r = df[
            (df["PartName"] == part) &
            (df["ModelName"] == model) &
            (df["ref"].astype(str).str.strip().str.upper() == str(ref).upper())
        ]

        # Pakai kolom 'point' kalau ada, fallback ke 'Parameter'
        param_col = "point" if "point" in df_r.columns and df_r["point"].notna().any() else "Parameter"

        # Auto-skip kalau hanya 1 parameter
        _df_all_r = self.df_all[
            (self.df_all["PartName"] == part) &
            (self.df_all["ModelName"] == model) &
            (self.df_all["ref"].astype(str).str.strip().str.upper() == str(ref).upper())
        ]
        _pcol_all = "point" if "point" in _df_all_r.columns and _df_all_r["point"].notna().any() else "Parameter"
        all_params = [p for p in _df_all_r[_pcol_all].dropna().astype(str).unique()
                      if p.strip() not in ["-",""]]
        if len(all_params) == 1:
            st.session_state["quick_param"] = all_params[0]
            st.rerun()

        # Semua parameter (termasuk 0 NG)
        all_param_list = [p for p in all_params if str(p).strip() not in ["-",""]]
        ng_count = (df_r[df_r["Judgement"] == "NG"]
                    .groupby(param_col).size()
                    .reindex(all_param_list, fill_value=0)
                    .sort_values(ascending=False))
        kp_params = set()
        if "KP" in df_r.columns:
            kp_params = set(df_r[df_r["KP"].astype(str).str.strip().isin(
                ["1","True","true","KP"])][param_col].astype(str).unique())
        labels  = ng_count.index.astype(str).tolist()
        values  = [int(v) for v in ng_count.values]
        total   = max(sum(values), 1)
        bar_colors = []
        for lbl in reversed(labels):
            idx = labels.index(lbl)
            v   = values[idx]
            if v == 0:
                bar_colors.append("#94A3B8")   # abu — 0 NG, tetap clickable
            elif lbl in kp_params:
                bar_colors.append("#EF4444")   # merah — KP NG
            else:
                bar_colors.append("#3B82F6")   # biru — non-KP NG
        bar_vals   = list(reversed(values))
        import json as _json
        samp_dist = {}
        for p in labels:
            d = df_r[(df_r[param_col].astype(str)==p) & (df_r["Judgement"]=="NG")]
            samp_dist[p] = {str(k): int(v)
                            for k, v in d.groupby("SampleNo").size().items()}
        samp_js = _json.dumps(samp_dist, ensure_ascii=False)
        clr_js  = _json.dumps(bar_colors)
        _tt = ("function(p){var nm=p[0].name,v=p[0].value;var pct=((v/__TOTAL__)*100).toFixed(1);var d=(__SAMP__)[nm]||{};var keys=Object.keys(d);var ds=keys.length?keys.map(function(k){return 'Sample '+k+': '+d[k];}).join('<br/>'):'\\u2014';return '<b>'+nm+'</b><br/>Total NG: '+v+'<br/><hr style=margin:4px/>'+ds;}"
               .replace("__TOTAL__", str(total))
               .replace("__SAMP__", samp_js))
        tooltip_js = JsCode(_tt)
        color_fn = JsCode(
            "function(p){var c=" + clr_js + ";return c[p.dataIndex]||'#3B82F6';}"
        )
        n_bars  = len(labels)
        end_pct = min(100, round(10 / max(n_bars, 1) * 100))
        legend_g = [
            {"type":"group","right":90,"top":38,"children":[
                {"type":"rect","shape":{"x":0,"y":0,"width":12,"height":12},
                 "style":{"fill":"#EF4444"}},
                {"type":"text","x":16,"y":1,"style":{"text":"KP","font":"11px Arial","fill":"#334155"}},
            ]},
            {"type":"group","right":20,"top":38,"children":[
                {"type":"rect","shape":{"x":0,"y":0,"width":12,"height":12},
                 "style":{"fill":"#3B82F6"}},
                {"type":"text","x":16,"y":1,"style":{"text":"Non-KP","font":"11px Arial","fill":"#334155"}},
            ]},
        ]
        options = {
            "title": {"text": f"NG per Parameter — Titik {ref}",
                      "subtext": self._quick_periode_title,
                      "left": 14, "top": 12,
                      "textStyle": {"fontSize": 14, "fontWeight": 700, "color": "#0F172A"}},
            "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
            "graphic": legend_g,
            "grid": {"top": 62, "right": 60, "bottom": 16, "left": 20, "containLabel": True},
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"},
                        "backgroundColor": "#1E293B", "borderColor": "#334155",
                        "textStyle": {"color": "#F8FAFC"}, "formatter": tooltip_js},
            "dataZoom": ([
                {"type": "slider", "yAxisIndex": 0, "orient": "vertical", "right": 8,
                 "start": 100-end_pct, "end": 100, "width": 12,
                 "borderColor": "transparent", "backgroundColor": "#F1F5F9",
                 "fillerColor": "#CBD5E1", "handleStyle": {"color": "#94A3B8"},
                 "showDetail": False, "showDataShadow": False},
                {"type": "inside", "yAxisIndex": 0, "start": 100-end_pct, "end": 100,
                 "zoomOnMouseWheel": False, "moveOnMouseWheel": True},
            ] if n_bars > 10 else []),
            "xAxis": {"type": "value",
                      "axisLabel": {"fontSize": 10, "color": "#94A3B8"},
                      "axisLine": {"show": False}, "axisTick": {"show": False},
                      "splitLine": {"lineStyle": {"color": "#F1F5F9", "type": "dashed"}}},
            "yAxis": {"type": "category", "data": list(reversed(labels)),
                      "axisLabel": {"fontSize": 12, "fontWeight": 600, "color": "#334155"},
                      "axisTick": {"show": False},
                      "axisLine": {"lineStyle": {"color": "#E2E8F0"}}},
            "series": [{"name": "NG", "type": "bar", "data": bar_vals,
                        "barMaxWidth": 28, "cursor": "pointer",
                        "itemStyle": {"color": color_fn, "borderRadius": [0,6,6,0]},
                        "label": {"show": True, "position": "right", "formatter": "{c}",
                                  "fontSize": 12, "fontWeight": 700,
                                  "color": "#0F172A", "distance": 6},
                        "emphasis": {"itemStyle": {"shadowBlur": 8,
                                                   "shadowColor": "rgba(0,0,0,0.15)"}}}],
        }
        events = {"click": "function(params){ return {name: params.name, value: params.value}; }"}
        clicked = st_echarts(options=options, events=events,
                             height="420px", key="quick_pareto_param")
        if clicked:
            name = None
            if isinstance(clicked, dict):
                name = clicked.get("name")
                if not name and "chart_event" in clicked:
                    inner = clicked["chart_event"]
                    if isinstance(inner, dict): name = inner.get("name")
            elif isinstance(clicked, str):
                name = clicked
            if name:
                st.session_state["quick_param"] = name
                st.rerun()

    # ── LEVEL 5 — Detail titik+parameter ─────────────────────────────
# ══════════════════════════════════════════════════════════════════════
#  [B] GANTI _quick_level5_detail DENGAN VERSI INI
# ══════════════════════════════════════════════════════════════════════

    def _quick_level5_detail(self, df: "pd.DataFrame"):
        part  = st.session_state["quick_part"]
        model = st.session_state["quick_model"]
        ref   = st.session_state["quick_ref"]
        param = st.session_state["quick_param"]

        param_col = "point" if "point" in df.columns and df["point"].notna().any() else "Parameter"
        df_detail = df[
            (df["PartName"] == part) &
            (df["ModelName"] == model) &
            (df["ref"].astype(str).str.strip().str.upper() == str(ref).upper()) &
            (df[param_col].astype(str) == str(param))
        ].sort_values(["Date", "Shift", "Cycle"])

        self._render_point_detail(df_detail, ref, param, key_suffix=f"q_{ref}_{param}")

    # ── Helper: empty state ──────────────────────────────────────────
    def _render_empty_state(self, title: str, subtitle: str):
        st.markdown(f"""
        <div style="background:#F0FDF4;border:0.5px solid #BBF7D0;border-radius:10px;
             padding:32px;text-align:center;margin-top:16px;">
          <div style="font-size:32px;margin-bottom:8px;">✓</div>
          <div style="font-size:14px;font-weight:700;color:#14532D;margin-bottom:4px;">{title}</div>
          <div style="font-size:12px;color:#166534;">{subtitle}</div>
        </div>
        """, unsafe_allow_html=True)

    # ── Helper: render pareto chart (clean, no cumulative line) ──────
    def _render_pareto(
        self,
        data: pd.Series,
        title: str,
        subtitle: str,
        key: str,
        on_click_state_key: str,
        bar_color: str = "#EF4444",
    ):
        """
        Render pareto chart horizontal — clean, tanpa cumulative line.
        Klik bar → set session_state[on_click_state_key] = nama bar.
        """
        # Jumlah bar dan window awal (tampilkan max 10, sisanya bisa di-scroll)
        labels = data.index.astype(str).tolist()
        values = [int(v) for v in data.values.tolist()]
        total  = sum(values) if sum(values) > 0 else 1
        n_bars = len(labels)
        # Persen window awal: tampilkan 10 bar pertama
        end_pct = min(100, round(10 / n_bars * 100)) if n_bars > 10 else 100

        # Tooltip: NG count + % dari total
        tooltip_js = JsCode(f"""
            function(p){{
                var pct = ((p[0].value / {total}) * 100).toFixed(1);
                return '<div style="font-family:Inter;font-size:12px;line-height:1.7;">'
                     + '<b style="font-size:13px;">' + p[0].name + '</b><br/>'
                     + 'NG : <b style="color:#EF4444;">' + p[0].value + '</b><br/>'
                     + 'Porsi : <b>' + pct + '%</b>'
                     + '</div>';
            }}
        """)

        # Fixed height, scroll via dataZoom Y-axis
        VISIBLE_BARS = 10
        chart_h = 420
        end_pct = min(100, round(VISIBLE_BARS / max(len(labels), 1) * 100))

        options = {
            "title": {
                "text": title, "subtext": subtitle,
                "left": 14, "top": 12,
                "textStyle": {"fontSize": 14, "fontWeight": 700, "color": "#0F172A", "fontFamily": "Inter"},
                "subtextStyle": {"fontSize": 11, "color": "#94A3B8", "fontFamily": "Inter"},
            },
            "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
            "grid": {"top": 62, "right": 60, "bottom": 16, "left": 20, "containLabel": True},
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {"type": "shadow"},
                "backgroundColor": "#1E293B",
                "borderColor": "#334155",
                "textStyle": {"color": "#F8FAFC"},
                "formatter": tooltip_js,
            },
            "dataZoom": [
                {
                    "type": "slider",
                    "yAxisIndex": 0,
                    "orient": "vertical",
                    "right": 8,
                    "start": 100 - end_pct,
                    "end": 100,
                    "width": 14,
                    "handleSize": "80%",
                    "borderColor": "#E2E8F0",
                    "fillerColor": "rgba(59,130,246,0.15)",
                    "handleStyle": {"color": "#3B82F6"},
                    "showDetail": False,
                },
                {"type": "inside", "yAxisIndex": 0},
            ],
            "xAxis": {
                "type": "value",
                "axisLabel": {"fontSize": 10, "color": "#94A3B8"},
                "axisLine": {"show": False},
                "axisTick": {"show": False},
                "splitLine": {"lineStyle": {"color": "#F1F5F9", "type": "dashed"}},
            },
            "yAxis": {
                "type": "category",
                "data": list(reversed(labels)),
                "axisLabel": {"fontSize": 12, "fontWeight": 600, "color": "#334155",
                              "fontFamily": "Inter"},
                "axisTick": {"show": False},
                "axisLine": {"lineStyle": {"color": "#E2E8F0"}},
            },
            "series": [{
                "name": "NG",
                "type": "bar",
                "data": list(reversed(values)),
                "itemStyle": {"color": bar_color, "borderRadius": [0, 6, 6, 0]},
                "emphasis": {
                    "itemStyle": {"color": bar_color, "shadowBlur": 8,
                                  "shadowColor": "rgba(0,0,0,0.15)"},
                },
                "label": {
                    "show": True, "position": "right",
                    "formatter": "{c}",
                    "fontSize": 12, "fontWeight": 700,
                    "color": "#0F172A", "fontFamily": "Inter",
                    "distance": 6,
                },
                "barMaxWidth": 28,
                "cursor": "pointer",
            }],
            "dataZoom": ([
                {
                    "type": "slider", "yAxisIndex": 0,
                    "start": 100 - end_pct, "end": 100,
                    "width": 12, "right": 2,
                    "borderColor": "transparent",
                    "backgroundColor": "#F1F5F9",
                    "fillerColor": "#CBD5E1",
                    "handleStyle": {"color": "#94A3B8"},
                    "showDetail": False,
                    "showDataShadow": False,
                },
                {
                    "type": "inside", "yAxisIndex": 0,
                    "start": 100 - end_pct, "end": 100,
                    "zoomOnMouseWheel": False,
                    "moveOnMouseWheel": True,
                },
            ] if n_bars > 10 else []),
        }

        events = {
            "click": "function(params){ return {name: params.name, value: params.value}; }"
        }

        clicked = st_echarts(options=options, events=events,
                             height="420px", key=key)
        # Hint klik

        # Process click — handle multiple return format
        if clicked:
            name = None
            if isinstance(clicked, dict):
                name = clicked.get("name")
                if not name and "chart_event" in clicked:
                    inner = clicked["chart_event"]
                    if isinstance(inner, dict):
                        name = inner.get("name")
            elif isinstance(clicked, str):
                name = clicked

            if name and name in labels:
                st.session_state[on_click_state_key] = name
                st.rerun()

    # ═════════════════════════════════════════════════════════════════
    #  DEEP INVESTIGATION MODE — wrap kondisi 1-4 existing
    # ═════════════════════════════════════════════════════════════════
    def _render_deep(self):
        # ── Sync filter Quick/Dashboard → Deep (HANYA saat baru masuk Deep) ──
        # Nilai periode/shift tersimpan di key bersama _dash_time/_dash_shift.
        # Periode memakai string yang sama persis dengan build_filters →
        # cukup identitas. Shift bisa berformat "Semua"/"1".. (Quick) atau
        # "Semua Shift"/"Shift 1".. (Dashboard) → petakan keduanya, dan
        # validasi agar nilainya benar-benar ada di opsi (hindari crash).
        p = "shared"
        if st.session_state.get("_desc_entered_deep"):
            _valid_time = {"Hari Ini", "7 Hari Terakhir", "30 Hari Terakhir",
                           "Semua Periode", "Custom"}
            _shift_map = {
                "Semua": "Semua Shift", "Semua Shift": "Semua Shift",
                "Shift 1": "1", "Shift 2": "2", "Shift 3": "3",
                "1": "1", "2": "2", "3": "3",
            }
            _pill_time  = st.session_state.get(f"{p}_dash_time")
            _pill_shift = st.session_state.get(f"{p}_dash_shift")
            if _pill_time in _valid_time:
                st.session_state[f"{p}_time"] = _pill_time
            if _pill_shift in _shift_map:
                _mapped = _shift_map[_pill_shift]
                _avail_shift = set(self.df_all["Shift"].dropna().astype(str).unique().tolist())
                if _mapped == "Semua Shift" or _mapped in _avail_shift:
                    st.session_state[f"{p}_shift"] = _mapped
        """
        Deep Investigation mode — kondisi 1-4 yang sudah ada di file lama.

        IMPLEMENTASI: copy seluruh logika dari descriptive.py lama mulai dari
        baris `filters = build_filters(...)` sampai sebelum tabel data terfilter.

        Yang berubah dari versi lama:
          1. Breadcrumb di atas filter
          2. Kondisi 3 disembunyikan kalau kondisi 4 aktif (titik diklik)
          3. kpi_card & get_ok_ratio jadi method class (deduplikasi)
        """
                # ── Filters ─────────────────────────────────────────────────
        # Prefix "shared" sama dengan Dashboard → user tidak perlu filter ulang saat pindah halaman.

        # Konsumsi flag reset dari tombol Back SEBELUM build_filters merender widget
        if st.session_state.pop("_reset_shared_model", False):
            st.session_state["shared_model"] = "Semua Model"
        if st.session_state.pop("_reset_shared_part", False):
            st.session_state["shared_part"]  = "Semua Part"
            st.session_state["shared_model"] = "Semua Model"

        # Konsumsi flag search — set Part+Model+Ref sebelum widget dirender
        if st.session_state.get("_search_target_ref"):
            st.session_state["shared_part"]  = st.session_state.pop("_search_target_part", "Semua Part")
            st.session_state["shared_model"] = st.session_state.pop("_search_target_model", "Semua Model")
            st.session_state["active_ref"]   = st.session_state.pop("_search_target_ref")
            st.session_state["active_event"] = "marked"
            st.session_state["_search_just_applied"] = True  # flag: jangan reset active_ref

        filters = build_filters(self.df_all, session_prefix="shared")
        df      = apply_filters(self.df_all, filters)

        f_cmm   = filters["cmm"]
        f_part  = filters["part"]
        f_model = filters["model"]

        # Reset active_ref kalau Part atau Model berubah secara MANUAL
        # (bukan dari search — search sudah set Part+Model+Ref bersamaan)
        _p_key, _m_key = "_deep_prev_part", "_deep_prev_model"
        _from_search = st.session_state.get("_search_just_applied", False)
        if _from_search:
            st.session_state.pop("_search_just_applied", None)
        if (st.session_state.get(_p_key) != f_part or
                st.session_state.get(_m_key) != f_model):
            st.session_state[_p_key] = f_part
            st.session_state[_m_key] = f_model
            # Jangan reset active_ref kalau perubahan ini dari search
            if st.session_state.get("active_ref") and not _from_search:
                st.session_state["active_ref"]   = None
                st.session_state["active_event"] = "marked"
                st.rerun()
        f_cat   = filters["cat"]
        f_d1    = filters["d1"]
        f_d2    = filters["d2"]
        f_shift = filters["shift"]
        f_cycle = filters["cycle"]
 
        # ── Label periode untuk judul chart ─────────────────────────
        shift_str = f"Shift {f_shift}" if f_shift != "Semua Shift" else "Semua Shift"
        date_str  = f"{f_d1.strftime('%d %b')}" if f_d1 == f_d2 else f"{f_d1.strftime('%d %b')} - {f_d2.strftime('%d %b %Y')}"
        PERIODE_TITLE = f"({date_str} | {shift_str})"
        
        # ── Tombol Back (pojok kanan bawah filter) ───────────────────
        _active_ref = st.session_state.get("active_ref")
        _can_back   = (_active_ref or f_model != "Semua Model" or f_part != "Semua Part")
        if _can_back:
            _bcols = st.columns([9, 1])
            with _bcols[1]:
                if st.button("Kembali", key="deep_back_top", use_container_width=True):
                    if _active_ref:
                        st.session_state["active_ref"]   = None
                        st.session_state["active_event"] = "marked"
                    elif f_model != "Semua Model":
                        # Pakai flag — tidak langsung modif widget key
                        st.session_state["_reset_shared_model"] = True
                    elif f_part != "Semua Part":
                        st.session_state["_reset_shared_part"]   = True
                        st.session_state["_reset_shared_model"]  = True
                    st.rerun()

        self._render_deep_breadcrumb()
        st.markdown('<div class="row-gap"></div>', unsafe_allow_html=True)

        # ── Search bar — langsung ke titik ───────────────────────────
        if not df.empty:
            # Bangun opsi: "REF · Part · Model" agar identitas jelas
            _ref_rows = (
                self.df_all[["ref","PartName","ModelName"]]
                .dropna(subset=["ref"])
                .drop_duplicates()
            )
            _ref_rows = _ref_rows[
                _ref_rows["ref"].astype(str).str.strip().isin(
                    [r for r in self.df_all["ref"].dropna().astype(str).unique()
                     if r.strip() not in ("","-","nan")]
                )
            ]
            # Terapkan filter Part+Model aktif supaya opsi menyempit kalau sudah filter
            if f_part not in ("Semua Part",""):
                _ref_rows = _ref_rows[_ref_rows["PartName"]==f_part]
            if f_model not in ("Semua Model",""):
                _ref_rows = _ref_rows[_ref_rows["ModelName"]==f_model]

            _search_opts = sorted([
                f"{r['ref']} · {r['PartName']} · {r['ModelName']}"
                for _, r in _ref_rows.iterrows()
            ])

            if _search_opts:
                _sc1, _sc2 = st.columns([3, 1], gap="small")
                with _sc1:
                    _search_val = st.selectbox(
                        "🔍 Cari Titik",
                        ["Pilih titik..."] + _search_opts,
                        key="deep_search_ref",
                        label_visibility="visible",
                    )
                with _sc2:
                    st.markdown('<div style="height:27px;"></div>', unsafe_allow_html=True)
                    if st.button("🔍", key="deep_search_go",
                                 use_container_width=True,
                                 disabled=_search_val == "Pilih titik...",
                                 help="Langsung ke titik yang dipilih"):
                        _parts = _search_val.split(" · ", 2)
                        if len(_parts) == 3:
                            _s_ref, _s_part, _s_model = _parts
                            # Pakai flag — tidak langsung modif widget key
                            st.session_state["_search_target_part"]  = _s_part
                            st.session_state["_search_target_model"] = _s_model
                            st.session_state["_search_target_ref"]   = _s_ref
                            st.rerun()

        total_part = df.groupby([df["Date"].dt.date, "Cycle", "PartName", "ModelName"]).ngroups if not df.empty else 0


        # ─────────────────────────────────────────────────────────────────
        #  DATABASE KOORDINAT TITIK (Berdasarkan Ukuran Asli 1280x400)
        # ─────────────────────────────────────────────────────────────────

        # ─────────────────────────────────────────────────────────────────
        #  KOTAK GAMBAR DINAMIS (INTERAKTIF ECHARTS)
        # ─────────────────────────────────────────────────────────────────
        active_key = _detect_active_key(f_part, f_model) if (
            f_model not in ("Semua Model","") and f_part not in ("Semua Part","")
        ) else ""
        image_url  = _get_image_b64(active_key) if active_key else None
        clicked_point = None

        if image_url:
            # Clear stale session state dari render sebelumnya
            _scatter_key = f"scatter_{active_key}"
            if isinstance(st.session_state.get(_scatter_key), dict):
                del st.session_state[_scatter_key]

            # 1. SETUP UKURAN ASLI DAN UKURAN DISPLAY (Tanpa perhitungan scale manual)
            ORIGINAL_W = 1280
            ORIGINAL_H = ORIG_H_MAP.get(active_key, 500)
            
            # Anda menggunakan lebar 1200 yang sudah pas di layar
            DISPLAY_W = 1200
            DISPLAY_H = int(DISPLAY_W * (ORIGINAL_H / ORIGINAL_W)) # Hasil otomatis proporsional
            
# Hitung subtext schematic (sama seperti Quick)
            _all_r_deep = [r for r in df["ref"].dropna().astype(str).unique()
                           if r.strip() not in ["-", ""]]
            _n_t_deep  = len(_all_r_deep)
            _n_ng_deep = int((df["Judgement"] == "NG").sum())
            _n_kp_deep = _n_kpng_deep = 0
            if "KP" in df.columns:
                _km_deep      = df["KP"].astype(str).str.strip().isin(["1", "True", "true", "KP"])
                _n_kp_deep    = int(df[_km_deep]["ref"].nunique())
                _n_kpng_deep  = int((df["Judgement"].eq("NG") & _km_deep).sum())
            _sch_sub_deep = (f"Titik: {_n_t_deep}  |  KP: {_n_kp_deep}  |"
                             f"  Total NG: {_n_ng_deep}  |  KP NG: {_n_kpng_deep}")

# Ambil data point dari COORD_DB dan warnai otomatis (Lampu Indikator)
            # Bangun tooltip per titik — sama seperti Quick Level 3
            points_data = []
            for pt in COORD_DB.get(active_key, []):
                ref_name = pt["name"].upper()
                df_pt    = df[df["ref"].astype(str).str.strip().str.upper()==ref_name]

                if df_pt.empty:
                    clr     = "#94A3B8"
                    tip_str = f"<b>{ref_name}</b><br/>Tidak ada data"
                else:
                    has_ng = (df_pt["Judgement"] == "NG").any()
                    clr    = "#EF4444" if has_ng else "#22C55E"
                    n_tot  = len(df_pt)
                    df_ng  = df_pt[df_pt["Judgement"] == "NG"]
                    n_ng   = len(df_ng)
                    pcol   = "point" if "point" in df_pt.columns and df_pt["point"].notna().any() else "Parameter"

                    if not has_ng:
                        tip_str = (f"<b>{ref_name}</b>"
                                   f"<br/>✓ Semua OK"
                                   f"<br/><span style='color:#94A3B8;font-size:10px;'>"
                                   f"Total: {n_tot} pengukuran</span>")
                    else:
                        hr = "<br/><hr style='margin:3px 0;border-color:#334155;border-width:0.5px;'/>"
                        param_cnt = (df_ng.groupby(pcol).size().sort_values(ascending=False)
                                     if pcol in df_ng.columns else None)
                        parts_tip = []
                        if param_cnt is not None:
                            for p, c in param_cnt.items():
                                p_str = str(p)
                                df_p  = df_ng[df_ng[pcol].astype(str) == p_str]
                                df_ps = df_p.sort_values("Date", ascending=False) if "Date" in df_p.columns else df_p
                                last_dev = None
                                if "Deviation" in df_ps.columns and df_ps["Deviation"].notna().any():
                                    last_dev = round(float(df_ps["Deviation"].dropna().iloc[0]), 4)
                                sign = "+" if last_dev is not None and last_dev >= 0 else ""
                                dev_line = (f"<br/><span style='color:#94A3B8;font-size:10px;'>"
                                            f"Deviasi NG terbaru: {sign}{last_dev}</span>"
                                            if last_dev is not None else "")
                                is_kp_p = ("KP" in df_p.columns and
                                           df_p["KP"].astype(str).str.strip()
                                           .isin(["1","True","true","KP"]).any())
                                kp_lbl  = (" <span style='color:#FBBF24;font-weight:700;'>(KP)</span>"
                                           if is_kp_p else "")
                                parts_tip.append(f"<b>{p_str}</b>{kp_lbl} : {int(c)}{dev_line}")
                        tip_str = (f"<b>{ref_name}</b>"
                                   f"<br/>Total NG: <b style='color:#EF4444;'>{n_ng}</b>"
                                   + (hr + hr.join(parts_tip) if parts_tip else ""))

                points_data.append({
                    "name":  ref_name,
                    "value": pt["value"],
                    "_tip":  tip_str,
                    "itemStyle": {"color": clr, "borderColor": "#ffffff",
                                  "borderWidth": 1.5, "opacity": 0.9}
                })

            # 2. ECHARTS OPTIONS
            options = {
                "title": {
                    "text": "Schematic Part View",
                    "subtext": _sch_sub_deep,
                    "left": 16, "top": 8,
                    "textStyle": {"color": "#0F172A", "fontSize": 14, "fontWeight": 700, "fontFamily": "Inter"},
                    "subtextStyle": {"color": "#64748B", "fontSize": 11},
                },
                "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
                
                # KUNCI 1: "left": 0 agar titik koordinat nempel di kiri dan tidak loncat saat di-zoom
                "grid": {"left": 0, "width": DISPLAY_W, "height": DISPLAY_H, "top": 55, "bottom": 10},
                
                # KUNCI 2: Sumbu X & Y dikunci mutlak ke resolusi asli gambar (1280x400)
                "xAxis": {"show": False, "min": 0, "max": ORIGINAL_W},
                "yAxis": {"show": False, "min": 0, "max": ORIGINAL_H, "inverse": True},
                
                
                "graphic": [{
                    "type": "image",
                    
                    # KUNCI 3: "left": 0 agar gambar juga nempel di kiri sehidup semati dengan titik koordinat
                    "left": 0, 
                    
                    "top": 55,
                    "z": -10,
                    "style": {
                        "image": image_url,
                        "width": DISPLAY_W,
                        "height": DISPLAY_H
                    }
                }],
                
                "tooltip": {
                    "trigger": "item",
                    "backgroundColor": "#1E293B",
                    "borderColor": "#334155",
                    "textStyle": {"color": "#F8FAFC", "fontSize": 12},
                    "formatter": JsCode("function(p){ return p.data._tip || ('<b>'+p.name+'</b>'); }")
                },
                "series": [{
                    "type": "scatter",
                    "symbol": "circle",
                    "symbolSize": 12,
                    "itemStyle": {"color": "rgba(220, 38, 38, 0.1)", "borderColor": "#DC2626", "borderWidth": 0},
                    "emphasis": {"itemStyle": {"borderColor": "#ffffff", "borderWidth": 2},
                                 "symbolSize": 18},
                    "data": points_data
                }]
                
            }
            # 3. ECHARTS EVENTS (Smart Click dengan auto-convert resolusi)
# 3. ECHARTS EVENTS (Smart Click yang kebal error)
            events = {
                "click": """function(params) {
                    try {
                        // Jika yang diklik adalah titik (scatter)
                        if (params.componentSubType === 'scatter') {
                            return {name: params.name, value: params.value, type: 'marked'};
                        } 
                        // Jika yang diklik adalah area gambar kosong
                        else {
                            var mouseX = params.event ? params.event.offsetX : 0;
                            var mouseY = params.event ? params.event.offsetY : 0;
                            return {name: 'Area Kosong', value: [mouseX, mouseY], type: 'unmarked'};
                        }
                    } catch (error) {
                        return null; // Mencegah crash
                    }
                }"""
            }            
            total_height = DISPLAY_H + 70 
            # Tambahkan parameter width=f"{DISPLAY_W}px" agar kanvas terkunci permanen
            clicked_point = st_echarts(
                options=options, 
                events=events, 
                height=f"{total_height}px", 
                width=f"{DISPLAY_W}px",  # 🔴 KUNCI PAMUNGKASNYA DI SINI
                key=f"scatter_{active_key}"
            )
        else:
            empty_card = """
            <div style="width: 100%; box-sizing: border-box; background: #fff; border-radius: 10px; border: 1px solid #E8ECF2; box-shadow: 0 2px 4px rgba(15,23,42,.03); padding: 20px; margin-bottom: 16px;">
                <div style="font-size: 14px; font-weight: 700; color: #0F172A; margin-bottom: 12px;">Schematic Part View</div>
                <div style="padding: 20px; background: #F8FAFC; border-radius: 6px; color: #64748B; font-size: 13px; text-align: center; border: 1px dashed #CBD5E1;">
                    💡 Pilih spesifik kombinasi <b>Model</b> dan <b>Part</b> pada filter di atas untuk menampilkan gambar skematik interaktif.
                </div>
            </div>
            """
            st.markdown(empty_card, unsafe_allow_html=True)


        # ─────────────────────────────────────────────────────────────────
        #  APPLY POINT FILTER & MAPPING KOORDINAT
        # ─────────────────────────────────────────────────────────────────
        point_col_name = "ref" 
        actual_point = None
        pixel_pos = None
        event_type = "marked"

# PARSING KLIK ECHARTS
        if clicked_point is not None:
            if isinstance(clicked_point, dict):
                event_data = clicked_point.get("chart_event", clicked_point)
                if isinstance(event_data, dict):
                    new_ref = event_data.get("name")
                    if new_ref and event_data.get("type") == "marked":
                        st.session_state.active_ref   = new_ref
                        st.session_state.active_event = "marked"
                        st.session_state.pop(f"scatter_{active_key}", None)
                        st.rerun()
            
        # Gunakan nilai dari memori untuk menentukan kondisi
        actual_point = st.session_state.active_ref
        event_type = st.session_state.active_event

        # KP filter — sekarang di top filter (build_filters), lihat filters.py
        f_kp = filters.get("kp", "All KP")
        if f_kp != "All KP" and "KP" in df.columns:
            df = df[df["KP"].astype(str) == f_kp]

# 2. TAMPILKAN DEBUG (MODE FILTER vs MODE MAPPING)
#        if pixel_pos:
#            x_val = pixel_pos[0]
#            y_val = pixel_pos[1]
            
#            if event_type == "unmarked":
                # Rumus reverse-scale manual (Karena top margin ECharts kita set 55)
                # Pastikan saat melakukan mapping, layar web Anda dimaksimalkan (Full Screen)
#                ORIGINAL_W = 1280
#                ORIGINAL_H = 400
#                DISPLAY_W = 1200
#                DISPLAY_H = int(DISPLAY_W * (ORIGINAL_H / ORIGINAL_W)) # 375
                
#                real_x = x_val * (ORIGINAL_W / DISPLAY_W)
#                real_y = (y_val - 55) * (ORIGINAL_H / DISPLAY_H)
                
#                st.warning("🛠️ **Mode Mapping Aktif (Area Kosong Diklik)**")
#                st.success(f"🎯 **Tebakan Koordinat (Copy ke COORD_DB):** `[X: {real_x:.0f}, Y: {real_y:.0f}]`")
#                actual_point = None # Kosongkan agar tabel tidak hilang
#            else:
#                st.success(f"🎯 **Koordinat Titik COORD_DB:** `[X: {x_val:.0f}, Y: {y_val:.0f}]`")
#        else:
#            if clicked_point:
#                st.write(f"🔍 **Debug Nilai Klik:** `{clicked_point}`")

        # 3. JIKA TITIK MERAH DITEMUKAN, FILTER DATA
#        if actual_point and event_type == "marked":
#            st.info(f"📍 Filter aktif untuk Titik Inspeksi (Ref): **{actual_point}**")
#            df = df[df[point_col_name].astype(str).str.strip().str.upper() == actual_point.upper()]

        # ─────────────────────────────────────────────────────────────────
        #  KONDISI 4: TITIK DIPILIH — cek duluan, skip kondisi lain
        # ─────────────────────────────────────────────────────────────────
        if actual_point and event_type == "marked":
            df_ref = df[df[point_col_name].astype(str).str.strip().str.upper() == actual_point.upper()]
            if not df_ref.empty:
                st.markdown(
                    f'<div style="font-size:18px;font-weight:700;color:#0F172A;'
                    f'margin-bottom:16px;">Analisis Titik: {actual_point}</div>',
                    unsafe_allow_html=True
                )
                detail_points = sorted(df_ref["point"].dropna().astype(str).unique().tolist())
                if detail_points:
                    selected_detail = st.radio(
                        f"Pilih parameter untuk point {actual_point}:",
                        detail_points,
                        key="detail_point_select",
                        horizontal=True
                    )
                    df_detail = df_ref[df_ref["point"].astype(str) == selected_detail]
                    self._render_point_detail(
                        df_detail, actual_point, selected_detail,
                        key_suffix=f"deep_{actual_point}_{selected_detail}"
                    )
            return  # stop — tidak render kondisi 1/2/3

        # ─────────────────────────────────────────────────────────────────
        #  KONDISI 1: GAMBARAN GLOBAL PABRIK (TIDAK MEMILIH FILTER)
        # ─────────────────────────────────────────────────────────────────
        # Syarat Kondisi 1: Tidak ada titik yang diklik, Part = All, Model = All
        if not actual_point and f_part == "Semua Part" and f_model == "Semua Model":
            st.markdown('<div style="font-size: 18px; font-weight: 700; color: #0F172A; margin-bottom: 16px;"></div>', unsafe_allow_html=True)

            if not df.empty:
                # ---------------------------------------------------------
                # 3. KPI METRICS (Total Diukur, Jumlah NG, Persentase OK)
                # ---------------------------------------------------------
                total_measured = len(df)
                total_ng       = len(df[df["Judgement"] == "NG"])
                total_ok       = total_measured - total_ng
                ok_ratio       = (total_ok / total_measured * 100) if total_measured > 0 else 0

                c1, c2, c3, c4, c5 = st.columns(5)

                # Fungsi pembuat UI Kartu (Card) dengan HTML & CSS
                def kpi_card(title, value, icon, color):
                    return f"""
                    <div style="background: #ffffff; border-radius: 10px; border: 1px solid #E8ECF2; box-shadow: 0 2px 4px rgba(15,23,42,.03); padding: 20px; display: flex; align-items: center; gap: 16px;">
                        <div style="background: {color}15; color: {color}; width: 50px; height: 50px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 24px;">
                            {icon}
                        </div>
                        <div>
                            <div style="color: #64748B; font-size: 13px; font-weight: 600; margin-bottom: 4px;">{title}</div>
                            <div style="color: #0F172A; font-size: 24px; font-weight: 700;">{value}</div>
                        </div>
                    </div>
                    """

                _total_part_kpi    = self._count_parts(df)
                _total_part_ng_kpi = self._count_parts(df[df["Judgement"] == "NG"]) if total_ng > 0 else 0
                with c1:
                    st.markdown(kpi_card("Total Part Diukur", f"{_total_part_kpi:,}", "📦", "#3B82F6"), unsafe_allow_html=True)
                with c2:
                    st.markdown(kpi_card("Total Part NG", f"{_total_part_ng_kpi:,}", "🚫", "#F97316"), unsafe_allow_html=True)
                with c3:
                    st.markdown(kpi_card("Total Titik Diukur", f"{total_measured:,}", "📍", "#8B5CF6"), unsafe_allow_html=True)
                with c4:
                    st.markdown(kpi_card("Total Titik NG", f"{total_ng:,}", "⚠️", "#EF4444"), unsafe_allow_html=True)
                with c5:
                    st.markdown(kpi_card("Persentase OK", f"{ok_ratio:.2f}%", "✅", "#10B981"), unsafe_allow_html=True)
                
                st.markdown('<div class="row-gap" style="height: 24px;"></div>', unsafe_allow_html=True)
                # ---------------------------------------------------------
                # DATA PREPARATION (Pandas)
                # ---------------------------------------------------------
                # Fungsi bantuan agar operasi Crosstab selalu punya kolom OK dan NG
                def get_ok_ratio(grouper):
                    ct = pd.crosstab(df[grouper], df['Judgement'])
                    if 'OK' not in ct.columns: ct['OK'] = 0
                    if 'NG' not in ct.columns: ct['NG'] = 0
                    ct['Total'] = ct['OK'] + ct['NG']
                    ct['OK_Ratio'] = (ct['OK'] / ct['Total']) * 100
                    return ct.sort_values(by='OK_Ratio', ascending=False)

                # Data OK Ratio Antar Part
                part_ratio_df = get_ok_ratio('PartName')
                part_x = part_ratio_df.index.tolist()
                part_ratio_y = part_ratio_df['OK_Ratio'].round(2).tolist()

                # Data OK Ratio Antar Mesin
                cmm_ratio_df = get_ok_ratio('CMMName')
                cmm_x = cmm_ratio_df.index.tolist()
                cmm_ratio_y = cmm_ratio_df['OK_Ratio'].round(2).tolist()

                # Data Top Part NG
                top_ng_part = df[df['Judgement'] == 'NG']['PartName'].value_counts().head(10)
                top_ng_x = top_ng_part.index.tolist()
                top_ng_y = top_ng_part.values.tolist()

                # Data Pie Chart Proporsi Part
                part_prop = df['PartName'].value_counts()
                pie_data = [{"name": str(k), "value": int(v)} for k, v in part_prop.items()]

                # Trend selalu per Date·Shift — kondisi 1 gabungan semua part
                df_trend = df.copy()
                df_trend["_donly"] = df_trend["Date"].dt.date
                df_trend["_x"] = (df_trend["Date"].dt.strftime("%d %b")
                                  + " · S" + df_trend["Shift"].astype(str))
                x_order1 = (df_trend.drop_duplicates("_x")
                            .sort_values(["_donly", "Shift"])["_x"].tolist())
                trend_ct1 = pd.crosstab(df_trend["_x"], df_trend["Judgement"])
                if "OK" not in trend_ct1.columns: trend_ct1["OK"] = 0
                if "NG" not in trend_ct1.columns: trend_ct1["NG"] = 0
                trend_dates = x_order1
                _ok1 = [int(trend_ct1.loc[x,"OK"]) if x in trend_ct1.index else 0 for x in x_order1]
                _ng1 = [int(trend_ct1.loc[x,"NG"]) if x in trend_ct1.index else 0 for x in x_order1]
                trend_ok = [round(_ok1[i]/(_ok1[i]+_ng1[i])*100,1) if (_ok1[i]+_ng1[i])>0 else 0 for i in range(len(trend_dates))]
                trend_ng = [round(_ng1[i]/(_ok1[i]+_ng1[i])*100,1) if (_ok1[i]+_ng1[i])>0 else 0 for i in range(len(trend_dates))]
                trend_sub = "Per Tanggal · Shift"
                # ---------------------------------------------------------
                # RENDER ECHARTS VISUALIZATION
                # ---------------------------------------------------------
                row1_col1, row1_col2 = st.columns(2)
                
                with row1_col1:
                    # 1. Perbandingan OK Ratio Antar Part
                    import json as _jk1r
                    _part_ok_cnt = [int(part_ratio_df.loc[p,"OK"]) if p in part_ratio_df.index else 0 for p in part_x]
                    _part_ng_cnt = [int(part_ratio_df.loc[p,"NG"]) if p in part_ratio_df.index else 0 for p in part_x]
                    _tt_part_ratio = JsCode(
                        "function(p){"
                        "var ok_cnt="+_jk1r.dumps(_part_ok_cnt)+";var ng_cnt="+_jk1r.dumps(_part_ng_cnt)+";"
                        "var idx=p[0].dataIndex;"
                        "var ok=ok_cnt[idx],ng=ng_cnt[idx],tot=ok+ng;"
                        "return '<b>'+p[0].axisValue+'</b><br/>"
                        "OK: <b style=color:#22C55E;>'+ok+'</b><br/>"
                        "NG: <b style=color:#EF4444;>'+ng+'</b><br/>"
                        "OK Ratio: <b>'+p[0].value+'%</b><br/>"
                        "Total: <b>'+tot+'</b>';}"
                    )
                    st_echarts({
                        "title": {"text": f"OK Ratio Antar Part", "subtext": PERIODE_TITLE, "textStyle": {"fontSize": 14, "fontWeight": "bold"}},
                        "tooltip": {"trigger": "axis", "formatter": _tt_part_ratio},
                        "yAxis": {"type": "value", "min": 0, "max": 100,
                                "axisLabel": {"formatter": "{value}%"}},
                        "xAxis": {"type": "category", "data": part_x, "axisLabel": {"interval": 0, "rotate": 30}},
                        "series": [{"data": part_ratio_y, "type": "bar", "itemStyle": {"color": "#3B82F6", "borderRadius": [4,4,0,0]}, "label": {"show": True, "position": "top", "formatter": "{c}%"}}],
                        "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
                    }, height="300px", key="chart_part_ratio")

                with row1_col2:
                    # 2. Perbandingan OK Ratio Antar Mesin
                    _cmm_ok_cnt = [int(cmm_ratio_df.loc[c,"OK"]) if c in cmm_ratio_df.index else 0 for c in cmm_x]
                    _cmm_ng_cnt = [int(cmm_ratio_df.loc[c,"NG"]) if c in cmm_ratio_df.index else 0 for c in cmm_x]
                    _tt_cmm_ratio = JsCode(
                        "function(p){"
                        "var ok_cnt="+_jk1r.dumps(_cmm_ok_cnt)+";var ng_cnt="+_jk1r.dumps(_cmm_ng_cnt)+";"
                        "var idx=p[0].dataIndex;"
                        "var ok=ok_cnt[idx],ng=ng_cnt[idx],tot=ok+ng;"
                        "return '<b>'+p[0].axisValue+'</b><br/>"
                        "OK: <b style=color:#22C55E;>'+ok+'</b><br/>"
                        "NG: <b style=color:#EF4444;>'+ng+'</b><br/>"
                        "OK Ratio: <b>'+p[0].value+'%</b><br/>"
                        "Total: <b>'+tot+'</b>';}"
                    )
                    st_echarts({
                        "title": {"text": f"OK Ratio Antar Mesin (CMM)","subtext": PERIODE_TITLE, "textStyle": {"fontSize": 14, "fontWeight": "bold"}},
                        "tooltip": {"trigger": "axis", "formatter": _tt_cmm_ratio},
                        "xAxis": {"type": "category", "data": cmm_x},
                        "yAxis": {"type": "value", "max": 100},
                        "series": [{"data": cmm_ratio_y, "type": "bar", "itemStyle": {"color": "#10B981", "borderRadius": [4,4,0,0]}, "label": {"show": True, "position": "top", "formatter": "{c}%"}}],
                        "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
                    }, height="300px", key="chart_cmm_ratio")


                row2_col1, row2_col2 = st.columns(2)

                with row2_col1:
                    # 5. Pie Chart Proporsi Part Diukur
                    st_echarts({
                        "title": {"text": f"Proporsi Part Diukur", "subtext": PERIODE_TITLE,"left": "center", "textStyle": {"fontSize": 14, "fontWeight": "bold"}},
                        "tooltip": {"trigger": "item"},
                        "legend": {"bottom": "0%", "left": "center"},
                        "series": [{"type": "pie", "radius": ["40%", "70%"], "itemStyle": {"borderRadius": 10, "borderColor": "#fff", "borderWidth": 2}, "label": {"show": True, "formatter": "{b}\n{d}%", "fontSize": 11}, "data": pie_data}],
                        "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
                    }, height="350px", key="chart_part_pie")

                with row2_col2:
                    # 4. Top Part NG
                    st_echarts({
                        "title": {"text": f"Top Part NG","subtext": PERIODE_TITLE, "textStyle": {"fontSize": 14, "fontWeight": "bold"}},
                        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                        "xAxis": {"type": "value"},
                        "yAxis": {"type": "category", "data": list(reversed(top_ng_x))}, # Dibalik agar nilai tertinggi di atas
                        "series": [{"data": list(reversed(top_ng_y)), "type": "bar", "itemStyle": {"color": "#EF4444", "borderRadius": [0,4,4,0]}, "label": {"show": True, "position": "right"}}],
                    "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
                    }, height="350px", key="chart_top_ng")



                # ── OK Ratio per Shift kondisi 1 — di atas tren ──────────
                if "Shift" in df.columns:
                    shifts_k1 = sorted(df["Shift"].dropna().unique())
                    parts_k1  = sorted(df["PartName"].dropna().unique())
                    COLORS_K1 = ["#6366F1","#F59E0B","#10B981","#EF4444","#8B5CF6","#06B6D4"]

                    import json as _jdk1
                    # xAxis = Part, series = per Shift — nama part muncul di bawah tiap grup
                    _ok_cnt_k1, _ng_cnt_k1 = {}, {}
                    ser_p = []
                    for i, sh in enumerate(shifts_k1):
                        vals = []
                        ok_c, ng_c = [], []
                        for pn in parts_k1:
                            grp = df[(df["PartName"]==pn) & (df["Shift"]==sh)]
                            tot = len(grp)
                            ok  = int((grp["Judgement"]=="OK").sum())
                            ng  = int((grp["Judgement"]=="NG").sum())
                            vals.append(round(ok/tot*100,1) if tot else 0)
                            ok_c.append(ok); ng_c.append(ng)
                        _ok_cnt_k1[f"S{sh}"] = ok_c
                        _ng_cnt_k1[f"S{sh}"]  = ng_c
                        ser_p.append({"name": f"Shift {sh}", "type": "bar", "data": vals,
                            "itemStyle": {"color": COLORS_K1[i%len(COLORS_K1)],
                                          "borderRadius": [4,4,0,0]},
                            "label": {"show": True, "position": "top",
                                      "formatter": "{c}%", "fontSize": 9}})
                    _tt_k1 = JsCode(
                        "function(p){"
                        "var ok_m="+_jdk1.dumps(_ok_cnt_k1)+";var ng_m="+_jdk1.dumps(_ng_cnt_k1)+";"
                        "var idx=p[0].dataIndex;"
                        "var lines='<b>'+p[0].axisValue+'</b><br/>';"
                        "p.forEach(function(s){"
                        "var key=s.seriesName.replace('Shift ','S');"
                        "var ok=ok_m[key]?ok_m[key][idx]:0;"
                        "var ng=ng_m[key]?ng_m[key][idx]:0;"
                        "lines+=s.marker+s.seriesName+': <b>'+s.value+'%</b>"
                        " (OK:'+ok+' NG:'+ng+')<br/>';"
                        "});return lines;}"
                    )
                    st_echarts({
                        "title": {"text": "OK Ratio per Shift",
                                  "subtext": PERIODE_TITLE,
                                  "textStyle": {"fontSize": 13, "fontWeight": 700}},
                        "tooltip": {"trigger": "axis", "formatter": _tt_k1},
                        "legend": {"data": [f"Shift {s}" for s in shifts_k1], "top": 8, "right": 8,
                                   "icon": "circle", "itemWidth": 8,
                                   "textStyle": {"fontSize": 11}},
                        "grid": {"left": "3%", "right": "4%", "bottom": "3%",
                                 "containLabel": True},
                        "xAxis": {"type": "category", "data": parts_k1,
                                  "axisLabel": {"fontSize": 11, "interval": 0, "rotate": 20}},
                        "yAxis": {"type": "value", "min": 0, "max": 100,
                                  "axisLabel": {"formatter": "{value}%"}},
                        "series": ser_p,
                    "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
                    }, height="300px", key="deep_shift_k1_part")

                # Grafik Trend OK vs NG — K1
                _tt_trend_k1 = JsCode(
                    "function(p){"
                    "var ok_cnt="+str(_ok1)+";var ng_cnt="+str(_ng1)+";"
                    "var idx=p[0].dataIndex;"
                    "var ok=ok_cnt[idx]||0,ng=ng_cnt[idx]||0,tot=ok+ng;"
                    "return '<b>'+p[0].axisValue+'</b><br/>"
                    "OK: <b style=color:#22C55E;>'+ok+'</b> ('+p[0].value+'%)<br/>"
                    "NG: <b style=color:#EF4444;>'+ng+'</b> ('+(p[1]?p[1].value:0)+'%)<br/>"
                    "Total: <b>'+tot+'</b>';}"
                )
                st_echarts({
                    "title": {"text": "Tren OK%", "subtext": PERIODE_TITLE + " | " + trend_sub,
                              "textStyle": {"fontSize": 14, "fontWeight": "bold"}},
                    "tooltip": {"trigger": "axis", "formatter": _tt_trend_k1},
                    "legend": {"data": ["OK%", "NG%"], "right": 100, "top": 12,
                               "icon": "circle", "itemWidth": 8,
                               "textStyle": {"color": "#64748B", "fontSize": 11}},
                    "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
                    "xAxis": {"type": "category", "boundaryGap": False, "data": trend_dates,
                              "axisLabel": {"interval": "auto"}},
                    "dataZoom": [{"type": "inside", "start": 0, "end": 100}],
                    "toolbox": {"feature": {"magicType": {"type": ["line", "bar"], "top": 12}, "saveAsImage": {"title": "Download PNG"}}},
                    "yAxis": {"type": "value", "min": 0, "max": 100,
                              "axisLabel": {"formatter": "{value}%"}},
                    "series": [
                        {"name": "OK%", "type": "line", "areaStyle": {"opacity": 0.2},
                         "itemStyle": {"color": "#22C55E"}, "data": trend_ok},
                        {"name": "NG%", "type": "line", "areaStyle": {"opacity": 0.2},
                         "itemStyle": {"color": "#EF4444"}, "data": trend_ng},
                    ],
                }, height="400px", key="chart_trend_okng")
            else:
                st.info("💡 Tidak ada data untuk periode ini.")

        # ─────────────────────────────────────────────────────────────────
        #  KONDISI 2: MEMILIH SALAH SATU PART (ANALISIS ANTAR MODEL)
        # ─────────────────────────────────────────────────────────────────
        # Syarat Kondisi 2: Part dipilih spesifik, Model masih "All", Tidak ada klik titik
        elif not actual_point and f_part != "Semua Part" and f_model == "Semua Model":
            st.markdown(f'<div style="font-size: 18px; font-weight: 700; color: #0F172A; margin-bottom: 16px;">⚙️ Analisis Kualitas Part: {f_part}</div>', unsafe_allow_html=True)

            if not df.empty:
                # ---------------------------------------------------------
                # 3. KPI METRICS (Total Diukur, Jumlah NG, Persentase OK)
                # ---------------------------------------------------------
                total_measured = len(df)
                total_ng = len(df[df["Judgement"] == "NG"])
                total_ok = total_measured - total_ng
                ok_ratio = (total_ok / total_measured * 100) if total_measured > 0 else 0

                c1, c2, c3, c4 = st.columns(4)
                
                # Memanggil UI Kartu (Card) dengan HTML & CSS
                def kpi_card(title, value, icon, color):
                    return f"""
                    <div style="background: #ffffff; border-radius: 10px; border: 1px solid #E8ECF2; box-shadow: 0 2px 4px rgba(15,23,42,.03); padding: 20px; display: flex; align-items: center; gap: 16px;">
                        <div style="background: {color}15; color: {color}; width: 50px; height: 50px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 24px;">
                            {icon}
                        </div>
                        <div>
                            <div style="color: #64748B; font-size: 13px; font-weight: 600; margin-bottom: 4px;">{title}</div>
                            <div style="color: #0F172A; font-size: 24px; font-weight: 700;">{value}</div>
                        </div>
                    </div>
                    """

                _total_part_kpi = self._count_parts(df)
                with c1:
                    st.markdown(kpi_card("Total Part Diukur", f"{_total_part_kpi:,}", "📦", "#3B82F6"), unsafe_allow_html=True)
                with c2:
                    st.markdown(kpi_card("Total Titik Diukur", f"{total_measured:,}", "📍", "#8B5CF6"), unsafe_allow_html=True)
                with c3:
                    st.markdown(kpi_card("Total Titik NG", f"{total_ng:,}", "⚠️", "#EF4444"), unsafe_allow_html=True)
                with c4:
                    st.markdown(kpi_card("Persentase OK", f"{ok_ratio:.2f}%", "✅", "#10B981"), unsafe_allow_html=True)
                
                st.markdown('<div class="row-gap" style="height: 24px;"></div>', unsafe_allow_html=True)

                # ---------------------------------------------------------
                # DATA PREPARATION (Level Model)
                # ---------------------------------------------------------
                def get_ok_ratio(grouper):
                    ct = pd.crosstab(df[grouper], df['Judgement'])
                    if 'OK' not in ct.columns: ct['OK'] = 0
                    if 'NG' not in ct.columns: ct['NG'] = 0
                    ct['Total'] = ct['OK'] + ct['NG']
                    ct['OK_Ratio'] = (ct['OK'] / ct['Total']) * 100
                    return ct.sort_values(by='OK_Ratio', ascending=False)

                # Data OK Ratio Antar Model (Bukan Part lagi)
                model_ratio_df = get_ok_ratio('ModelName')
                model_x = model_ratio_df.index.astype(str).tolist()
                model_ratio_y = model_ratio_df['OK_Ratio'].round(2).tolist()

                # Data OK Ratio Antar Mesin
                cmm_ratio_df = get_ok_ratio('CMMName')
                cmm_x = cmm_ratio_df.index.astype(str).tolist()
                cmm_ratio_y = cmm_ratio_df['OK_Ratio'].round(2).tolist()

                # Data Top Model NG (Bukan Top Part lagi)
                top_ng_model = df[df['Judgement'] == 'NG']['ModelName'].value_counts().head(5)
                top_ng_x = top_ng_model.index.astype(str).tolist()
                top_ng_y = top_ng_model.values.tolist()

                # Data Pie Chart Proporsi Model
                model_prop = df['ModelName'].value_counts()
                pie_data = [{"name": str(k), "value": int(v)} for k, v in model_prop.items()]

                # Trend per Date·Shift — kondisi 2 masih banyak model
                df_trend = df.copy()
                df_trend["_donly"] = df_trend["Date"].dt.date
                df_trend["_x"] = (df_trend["Date"].dt.strftime("%d %b")
                                  + " · S" + df_trend["Shift"].astype(str))
                x_order2 = (df_trend.drop_duplicates("_x")
                            .sort_values(["_donly", "Shift"])["_x"].tolist())
                trend_ct2 = pd.crosstab(df_trend["_x"], df_trend["Judgement"])
                if "OK" not in trend_ct2.columns: trend_ct2["OK"] = 0
                if "NG" not in trend_ct2.columns: trend_ct2["NG"] = 0
                trend_dates = x_order2
                _ok2 = [int(trend_ct2.loc[x,"OK"]) if x in trend_ct2.index else 0 for x in x_order2]
                _ng2 = [int(trend_ct2.loc[x,"NG"]) if x in trend_ct2.index else 0 for x in x_order2]
                trend_ok = [round(_ok2[i]/(_ok2[i]+_ng2[i])*100,1) if (_ok2[i]+_ng2[i])>0 else 0 for i in range(len(trend_dates))]
                trend_ng = [round(_ng2[i]/(_ok2[i]+_ng2[i])*100,1) if (_ok2[i]+_ng2[i])>0 else 0 for i in range(len(trend_dates))]
                trend_sub2  = "Per Tanggal · Shift"

                # ---------------------------------------------------------
                # RENDER ECHARTS VISUALIZATION (KONDISI 2)
                # ---------------------------------------------------------
                # Catatan: Tambahkan akhiran "_k2" pada parameter key agar Echarts 
                # tidak bingung saat pindah dari Kondisi 1 ke Kondisi 2
                
                row1_col1, row1_col2 = st.columns(2)
                
                with row1_col1:
                    # 1. Perbandingan OK Ratio Antar Model
                    import json as _jk2r
                    _model_ok_cnt = [int(model_ratio_df.loc[m,"OK"]) if m in model_ratio_df.index else 0 for m in model_x]
                    _model_ng_cnt = [int(model_ratio_df.loc[m,"NG"]) if m in model_ratio_df.index else 0 for m in model_x]
                    _tt_model_ratio = JsCode(
                        "function(p){"
                        "var ok_cnt="+_jk2r.dumps(_model_ok_cnt)+";var ng_cnt="+_jk2r.dumps(_model_ng_cnt)+";"
                        "var idx=p[0].dataIndex;"
                        "var ok=ok_cnt[idx],ng=ng_cnt[idx],tot=ok+ng;"
                        "return '<b>'+p[0].axisValue+'</b><br/>"
                        "OK: <b style=color:#22C55E;>'+ok+'</b><br/>"
                        "NG: <b style=color:#EF4444;>'+ng+'</b><br/>"
                        "OK Ratio: <b>'+p[0].value+'%</b><br/>"
                        "Total: <b>'+tot+'</b>';}"
                    )
                    st_echarts({
                        "title": {"text": f"OK Ratio Antar Model ({f_part})", "subtext": PERIODE_TITLE, "textStyle": {"fontSize": 14, "fontWeight": "bold"}},
                        "tooltip": {"trigger": "axis", "formatter": _tt_model_ratio},
                        "xAxis": {"type": "category", "data": model_x, "axisLabel": {"interval": 0, "rotate": 30}},
                        "yAxis": {"type": "value", "max": 100},
                        "series": [{"data": model_ratio_y, "type": "bar", "itemStyle": {"color": "#3B82F6", "borderRadius": [4,4,0,0]}, "label": {"show": True, "position": "top", "formatter": "{c}%"}}],
                    "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
                    }, height="300px", key="chart_model_ratio_k2")

                with row1_col2:
                    # 2. Perbandingan OK Ratio Antar Mesin
                    _cmm_ok_cnt_k2 = [int(cmm_ratio_df.loc[c,"OK"]) if c in cmm_ratio_df.index else 0 for c in cmm_x]
                    _cmm_ng_cnt_k2 = [int(cmm_ratio_df.loc[c,"NG"]) if c in cmm_ratio_df.index else 0 for c in cmm_x]
                    _tt_cmm_k2 = JsCode(
                        "function(p){"
                        "var ok_cnt="+_jk2r.dumps(_cmm_ok_cnt_k2)+";var ng_cnt="+_jk2r.dumps(_cmm_ng_cnt_k2)+";"
                        "var idx=p[0].dataIndex;"
                        "var ok=ok_cnt[idx],ng=ng_cnt[idx],tot=ok+ng;"
                        "return '<b>'+p[0].axisValue+'</b><br/>"
                        "OK: <b style=color:#22C55E;>'+ok+'</b><br/>"
                        "NG: <b style=color:#EF4444;>'+ng+'</b><br/>"
                        "OK Ratio: <b>'+p[0].value+'%</b><br/>"
                        "Total: <b>'+tot+'</b>';}"
                    )
                    st_echarts({
                        "title": {"text": "OK Ratio Antar Mesin (CMM)", "subtext": PERIODE_TITLE, "textStyle": {"fontSize": 14, "fontWeight": "bold"}},
                        "tooltip": {"trigger": "axis", "formatter": _tt_cmm_k2},
                        "xAxis": {"type": "category", "data": cmm_x},
                        "yAxis": {"type": "value", "max": 100},
                        "series": [{"data": cmm_ratio_y, "type": "bar", "itemStyle": {"color": "#10B981", "borderRadius": [4,4,0,0]}, "label": {"show": True, "position": "top", "formatter": "{c}%"}}],
                    "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
                    }, height="300px", key="chart_cmm_ratio_k2")


                row2_col1, row2_col2 = st.columns(2)

                with row2_col1:
                    # 5. Pie Chart Proporsi Model Diukur
                    st_echarts({
                        "title": {"text": "Proporsi Model Diukur", "subtext": PERIODE_TITLE, "left": "center", "textStyle": {"fontSize": 14, "fontWeight": "bold"}},
                        "tooltip": {"trigger": "item"},
                        "legend": {"bottom": "0%", "left": "center"},
                        "series": [{"type": "pie", "radius": ["40%", "70%"], "itemStyle": {"borderRadius": 10, "borderColor": "#fff", "borderWidth": 2}, "label": {"show": True, "formatter": "{b}\n{d}%", "fontSize": 11}, "data": pie_data}],
                        "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
                    }, height="350px", key="chart_model_pie_k2")

                with row2_col2:
                    # 4. Top Model NG
                    st_echarts({
                        "title": {"text": "Top Model NG", "subtext": PERIODE_TITLE, "textStyle": {"fontSize": 14, "fontWeight": "bold"}},
                        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                        "xAxis": {"type": "value"},
                        "yAxis": {"type": "category", "data": list(reversed(top_ng_x))}, 
                        "series": [{"data": list(reversed(top_ng_y)), "type": "bar", "itemStyle": {"color": "#EF4444", "borderRadius": [0,4,4,0]}, "label": {"show": True, "position": "right"}}],
                    "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
                    }, height="350px", key="chart_top_ng_model_k2")



                # ── OK Ratio per Shift kondisi 2 — di atas tren ──────────
                if "Shift" in df.columns:
                    shifts_k2 = sorted(df["Shift"].dropna().unique())
                    models_k2 = sorted(df[df["PartName"]==f_part]["ModelName"].dropna().unique())
                    COLORS_K2 = ["#6366F1","#F59E0B","#10B981","#EF4444","#8B5CF6","#06B6D4"]
                    import json as _jdk2
                    # xAxis = Model, series = per Shift
                    _ok_cnt_k2, _ng_cnt_k2 = {}, {}
                    ser_k2 = []
                    for i, sh in enumerate(shifts_k2):
                        vals = []
                        ok_c, ng_c = [], []
                        for mn in models_k2:
                            grp = df[(df["ModelName"]==mn) & (df["Shift"]==sh)]
                            tot = len(grp)
                            ok  = int((grp["Judgement"]=="OK").sum())
                            ng  = int((grp["Judgement"]=="NG").sum())
                            vals.append(round(ok/tot*100,1) if tot else 0)
                            ok_c.append(ok); ng_c.append(ng)
                        _ok_cnt_k2[f"S{sh}"] = ok_c
                        _ng_cnt_k2[f"S{sh}"]  = ng_c
                        ser_k2.append({"name": f"Shift {sh}", "type": "bar", "data": vals,
                            "itemStyle": {"color": COLORS_K2[i%len(COLORS_K2)],
                                          "borderRadius": [4,4,0,0]},
                            "label": {"show": True, "position": "top",
                                      "formatter": "{c}%", "fontSize": 9}})
                    _tt_k2 = JsCode(
                        "function(p){"
                        "var ok_m="+_jdk2.dumps(_ok_cnt_k2)+";var ng_m="+_jdk2.dumps(_ng_cnt_k2)+";"
                        "var idx=p[0].dataIndex;"
                        "var lines='<b>'+p[0].axisValue+'</b><br/>';"
                        "p.forEach(function(s){"
                        "var key=s.seriesName.replace('Shift ','S');"
                        "var ok=ok_m[key]?ok_m[key][idx]:0;"
                        "var ng=ng_m[key]?ng_m[key][idx]:0;"
                        "lines+=s.marker+s.seriesName+': <b>'+s.value+'%</b>"
                        " (OK:'+ok+' NG:'+ng+')<br/>';"
                        "});return lines;}"
                    )
                    st_echarts({
                        "title": {"text": f"OK Ratio per Shift — {f_part}", "subtext": PERIODE_TITLE,
                                  "textStyle": {"fontSize": 13, "fontWeight": 700}},
                        "tooltip": {"trigger": "axis", "formatter": _tt_k2},
                        "legend": {"data": [f"Shift {s}" for s in shifts_k2], "top": 8, "right": 8,
                                   "icon": "circle", "itemWidth": 8,
                                   "textStyle": {"fontSize": 11}},
                        "grid": {"left": "3%", "right": "4%", "bottom": "3%",
                                 "containLabel": True},
                        "xAxis": {"type": "category", "data": list(models_k2),
                                  "axisLabel": {"fontSize": 11, "interval": 0, "rotate": 20}},
                        "yAxis": {"type": "value", "min": 0, "max": 100,
                                  "axisLabel": {"formatter": "{value}%"}},
                        "series": ser_k2,
                    "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
                    }, height="300px", key="deep_shift_k2")

                # Grafik Trend OK vs NG — K2
                _tt_trend_k2 = JsCode(
                    "function(p){"
                    "var ok_cnt="+str(_ok2)+";var ng_cnt="+str(_ng2)+";"
                    "var idx=p[0].dataIndex;"
                    "var ok=ok_cnt[idx]||0,ng=ng_cnt[idx]||0,tot=ok+ng;"
                    "return '<b>'+p[0].axisValue+'</b><br/>"
                    "OK: <b style=color:#22C55E;>'+ok+'</b> ('+p[0].value+'%)<br/>"
                    "NG: <b style=color:#EF4444;>'+ng+'</b> ('+(p[1]?p[1].value:0)+'%)<br/>"
                    "Total: <b>'+tot+'</b>';}"
                )
                st_echarts({
                    "title": {"text": f"Tren OK% — {f_part}", "subtext": PERIODE_TITLE + " | " + trend_sub2,
                              "textStyle": {"fontSize": 14, "fontWeight": "bold"}},
                    "tooltip": {"trigger": "axis", "formatter": _tt_trend_k2},
                    "legend": {"data": ["OK%", "NG%"], "right": 100, "top": 12,
                               "icon": "circle", "itemWidth": 8,
                               "textStyle": {"color": "#64748B", "fontSize": 11}},
                    "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
                    "xAxis": {"type": "category", "boundaryGap": False, "data": trend_dates,
                              "axisLabel": {"interval": "auto", "rotate": 20}},
                    "yAxis": {"type": "value", "min": 0, "max": 100,
                              "axisLabel": {"formatter": "{value}%"}},
                    "dataZoom": [{"type": "inside", "start": 0, "end": 100}],
                    "toolbox": {"feature": {"magicType": {"type": ["line", "bar"], "top": 12}, "saveAsImage": {"title": "Download PNG"}}},
                    "series": [
                        {"name": "OK%", "type": "line", "areaStyle": {"opacity": 0.2},
                         "itemStyle": {"color": "#22C55E"}, "data": trend_ok},
                        {"name": "NG%", "type": "line", "areaStyle": {"opacity": 0.2},
                         "itemStyle": {"color": "#EF4444"}, "data": trend_ng},
                    ],
                }, height="400px", key="chart_trend_okng_k2")

            else:
                st.info(f"💡 Tidak ada data untuk part {f_part} pada periode ini.")

        # ─────────────────────────────────────────────────────────────────
        #  KONDISI 3: MEMILIH MODEL (ANALISIS TINGKAT TITIK/POINT)
        # ─────────────────────────────────────────────────────────────────
        # Syarat Kondisi 3: Part & Model dipilih, tetapi belum ada titik yang diklik
        elif not actual_point and f_part != "Semua Part" and f_model != "Semua Model":
            st.markdown(f'<div style="font-size: 18px; font-weight: 700; color: #0F172A; margin-bottom: 16px;">🔍 Analisis Detail Titik Model: {f_model} ({f_part})</div>', unsafe_allow_html=True)

            if not df.empty:
                # ---------------------------------------------------------
                # 3. KPI METRICS (Total Titik Diukur, Jumlah NG, Persentase OK)
                # ---------------------------------------------------------
                total_measured = len(df)
                total_ng = len(df[df["Judgement"] == "NG"])
                total_ok = total_measured - total_ng
                ok_ratio = (total_ok / total_measured * 100) if total_measured > 0 else 0

                c1, c2, c3, c4 = st.columns(4)
                
                def kpi_card(title, value, icon, color):
                    return f"""
                    <div style="background: #ffffff; border-radius: 10px; border: 1px solid #E8ECF2; box-shadow: 0 2px 4px rgba(15,23,42,.03); padding: 20px; display: flex; align-items: center; gap: 16px;">
                        <div style="background: {color}15; color: {color}; width: 50px; height: 50px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 24px;">
                            {icon}
                        </div>
                        <div>
                            <div style="color: #64748B; font-size: 13px; font-weight: 600; margin-bottom: 4px;">{title}</div>
                            <div style="color: #0F172A; font-size: 24px; font-weight: 700;">{value}</div>
                        </div>
                    </div>
                    """

                _total_part_kpi = self._count_parts(df)
                with c1:
                    st.markdown(kpi_card("Total Part Diukur", f"{_total_part_kpi:,}", "📦", "#3B82F6"), unsafe_allow_html=True)
                with c2:
                    st.markdown(kpi_card("Total Titik Diukur", f"{total_measured:,}", "📍", "#8B5CF6"), unsafe_allow_html=True)
                with c3:
                    st.markdown(kpi_card("Total Titik NG", f"{total_ng:,}", "⚠️", "#EF4444"), unsafe_allow_html=True)
                with c4:
                    st.markdown(kpi_card("Persentase OK", f"{ok_ratio:.2f}%", "✅", "#10B981"), unsafe_allow_html=True)
                
                st.markdown('<div class="row-gap" style="height: 24px;"></div>', unsafe_allow_html=True)

                # ---------------------------------------------------------
                # DATA PREPARATION (Level Point / Ref)
                # ---------------------------------------------------------
                def get_ok_ratio(grouper):
                    ct = pd.crosstab(df[grouper], df['Judgement'])
                    if 'OK' not in ct.columns: ct['OK'] = 0
                    if 'NG' not in ct.columns: ct['NG'] = 0
                    ct['Total'] = ct['OK'] + ct['NG']
                    ct['OK_Ratio'] = (ct['OK'] / ct['Total']) * 100
                    return ct.sort_values(by='OK_Ratio', ascending=False)

                # Filter baris yang kolom ref-nya tidak kosong
                df_valid_ref = df[df['ref'].astype(str).str.strip() != ""]

                # Data OK Ratio Antar Point (Ref)
                if not df_valid_ref.empty:
                    ref_ratio_df = get_ok_ratio('ref')
                    ref_x = ref_ratio_df.index.astype(str).tolist()
                    ref_ratio_y = ref_ratio_df['OK_Ratio'].round(2).tolist()
                else:
                    ref_x, ref_ratio_y = [], []

                # Data OK Ratio Antar Mesin
                cmm_ratio_df = get_ok_ratio('CMMName')
                cmm_x = cmm_ratio_df.index.astype(str).tolist()
                cmm_ratio_y = cmm_ratio_df['OK_Ratio'].round(2).tolist()

                # Data Top Point NG
                top_ng_ref = df[df['Judgement'] == 'NG']['ref'].value_counts().head(10)
                top_ng_x = top_ng_ref.index.astype(str).tolist()
                top_ng_y = top_ng_ref.values.tolist()

                # Data Trend OK/NG Harian
                df_trend = df.copy()
                df_trend['DateOnly'] = df_trend['Date'].dt.strftime('%Y-%m-%d')
                trend_ct = pd.crosstab(df_trend['DateOnly'], df_trend['Judgement'])
                if 'OK' not in trend_ct.columns: trend_ct['OK'] = 0
                if 'NG' not in trend_ct.columns: trend_ct['NG'] = 0
                trend_dates = trend_ct.index.astype(str).tolist()
                _ok3 = trend_ct['OK'].tolist()
                _ng3 = trend_ct['NG'].tolist()
                trend_ok = [round(_ok3[i]/(_ok3[i]+_ng3[i])*100,1) if (_ok3[i]+_ng3[i])>0 else 0 for i in range(len(trend_dates))]
                trend_ng = [round(_ng3[i]/(_ok3[i]+_ng3[i])*100,1) if (_ok3[i]+_ng3[i])>0 else 0 for i in range(len(trend_dates))]

                # ---------------------------------------------------------
                # VENN DIAGRAM — QIS vs Produksi (jumlah titik ukur unik)
                # ---------------------------------------------------------
                if "Category" in df.columns:
                    _d2 = self.df_all[
                        (self.df_all["PartName"] == f_part) &
                        (self.df_all["ModelName"] == f_model)
                    ]
                    def _uniq2(cat):
                        sub = _d2[_d2["Category"] == cat]
                        return sub[["ID","Parameter","point"]].drop_duplicates().shape[0]
                    n_prod2 = _uniq2("Produksi"); n_qis2 = _uniq2("QIS")
                    n_total2 = n_prod2 + n_qis2

                    col_cat, col_sh3 = st.columns(2)
                    with col_cat:
                        st_echarts({
                            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                            "legend": {"data": ["QIS","Waste","Produksi"], "bottom": 0,
                                       "icon": "roundRect", "itemWidth": 12,
                                       "textStyle": {"fontSize": 11}},
                            "grid": {"top": 16, "bottom": 40, "left": 16, "right": 16,
                                     "containLabel": True},
                            "xAxis": {"type": "category", "data": [f_model],
                                      "axisLabel": {"fontSize": 11, "fontWeight": 600}},
                            "yAxis": {"type": "value", "show": False},
                            "series": [
                                {"name": "QIS", "type": "bar", "data": [n_total2],
                                 "itemStyle": {"color": "#3B82F6", "borderRadius": [4,4,0,0]},
                                 "label": {"show": True, "position": "inside",
                                           "formatter": f"{n_total2}", "fontSize": 13,
                                           "fontWeight": 700, "color": "#fff"},
                                 "barWidth": "35%", "barGap": "0%"},
                                {"name": "Waste", "type": "bar", "stack": "bd",
                                 "data": [n_qis2],
                                 "itemStyle": {"color": "#1D9E75", "borderRadius": [4,4,0,0]},
                                 "label": {"show": True, "position": "inside",
                                           "formatter": f"Waste\n{n_qis2}", "fontSize": 11,
                                           "fontWeight": 700, "color": "#fff"},
                                 "barWidth": "35%", "barGap": "0%"},
                                {"name": "Produksi", "type": "bar", "stack": "bd",
                                 "data": [n_prod2],
                                 "itemStyle": {"color": "#F59E0B", "borderRadius": [0,0,0,0]},
                                 "label": {"show": True, "position": "inside",
                                           "formatter": f"Produksi\n{n_prod2}", "fontSize": 11,
                                           "fontWeight": 700, "color": "#fff"},
                                 "barWidth": "35%", "barGap": "0%"},
                            ],
                        "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
                        }, height="350px", key="deep_venn_k3")

                    with col_sh3:
                        if top_ng_x:
                            st_echarts({
                                "title": {"text": f"Top Titik NG — {f_model}",
                                          "subtext": PERIODE_TITLE,
                                          "textStyle": {"fontSize": 13, "fontWeight": 700}},
                                "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                                "grid": {"left": "3%", "right": "8%", "bottom": "3%",
                                         "containLabel": True},
                                "xAxis": {"type": "value"},
                                "yAxis": {"type": "category",
                                          "data": list(reversed(top_ng_x))},
                                "dataZoom": [{"type": "slider", "yAxisIndex": 0,
                                              "start": 100, "end": 0, "width": 15, "right": 5,
                                              "borderColor": "transparent",
                                              "fillerColor": "rgba(220,38,38,0.15)",
                                              "handleStyle": {"color": "#DC2626"}}],
                                "series": [{"data": list(reversed(top_ng_y)), "type": "bar",
                                            "itemStyle": {"color": "#EF4444",
                                                          "borderRadius": [0,4,4,0]},
                                            "label": {"show": True, "position": "right"}}],
                            "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
                            }, height="350px", key="deep_top_ng_k3")

                # Trend kondisi 3 — selalu per Tanggal · Shift
                df_t3 = df.copy()
                df_t3["_donly"] = df_t3["Date"].dt.date
                n_d3 = df_t3["Date"].dt.date.nunique()
                df_t3["_x"] = (df_t3["Date"].dt.strftime("%d %b")
                               + " · S" + df_t3["Shift"].astype(str))
                x_order3    = (df_t3.drop_duplicates("_x")
                               .sort_values(["_donly", "Shift"])["_x"].tolist())
                sub3        = "Per Tanggal · Shift"
                tc3 = pd.crosstab(df_t3["_x"], df_t3["Judgement"])
                if "OK" not in tc3.columns: tc3["OK"] = 0
                if "NG" not in tc3.columns: tc3["NG"] = 0
                _ok3r = [int(tc3.loc[x,"OK"]) if x in tc3.index else 0 for x in x_order3]
                _ng3r = [int(tc3.loc[x,"NG"]) if x in tc3.index else 0 for x in x_order3]
                ok3 = [round(_ok3r[i]/(_ok3r[i]+_ng3r[i])*100,1) if (_ok3r[i]+_ng3r[i])>0 else 0 for i in range(len(x_order3))]
                ng3 = [round(_ng3r[i]/(_ok3r[i]+_ng3r[i])*100,1) if (_ok3r[i]+_ng3r[i])>0 else 0 for i in range(len(x_order3))]

                # ── OK Ratio per Shift kondisi 3 — di atas tren ───────────
                if "Shift" in df.columns:
                    shifts_k3 = sorted(df["Shift"].dropna().unique())
                    sno_k3    = sorted(df["SampleNo"].dropna().unique(), key=lambda s: [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", str(s))])
                    COLORS_K3 = ["#6366F1","#F59E0B","#10B981","#EF4444","#8B5CF6","#06B6D4"]
                    import json as _jdk3
                    # xAxis = SampleNo, series = per Shift
                    _ok_cnt_k3, _ng_cnt_k3 = {}, {}
                    ser_k3 = []
                    for i, sh in enumerate(shifts_k3):
                        vals = []
                        ok_c, ng_c = [], []
                        for sno in sno_k3:
                            grp = df[(df["SampleNo"]==sno) & (df["Shift"]==sh)]
                            tot = len(grp)
                            ok  = int((grp["Judgement"]=="OK").sum())
                            ng  = int((grp["Judgement"]=="NG").sum())
                            vals.append(round(ok/tot*100,1) if tot else 0)
                            ok_c.append(ok); ng_c.append(ng)
                        _ok_cnt_k3[f"S{sh}"] = ok_c
                        _ng_cnt_k3[f"S{sh}"] = ng_c
                        ser_k3.append({"name": f"Shift {sh}", "type": "bar", "data": vals,
                            "itemStyle": {"color": COLORS_K3[i%len(COLORS_K3)],
                                          "borderRadius": [4,4,0,0]},
                            "label": {"show": True, "position": "top",
                                      "formatter": "{c}%", "fontSize": 9}})
                    _tt_k3 = JsCode(
                        "function(p){"
                        "var ok_m="+_jdk3.dumps(_ok_cnt_k3)+";var ng_m="+_jdk3.dumps(_ng_cnt_k3)+";"
                        "var idx=p[0].dataIndex;"
                        "var lines='<b>'+p[0].axisValue+'</b><br/>';"
                        "p.forEach(function(s){"
                        "var key=s.seriesName.replace('Shift ','S');"
                        "var ok=ok_m[key]?ok_m[key][idx]:0;"
                        "var ng=ng_m[key]?ng_m[key][idx]:0;"
                        "lines+=s.marker+s.seriesName+': <b>'+s.value+'%</b>"
                        " (OK:'+ok+' NG:'+ng+')<br/>';"
                        "});return lines;}"
                    )
                    st_echarts({
                        "title": {"text": f"OK Ratio per Shift — {f_model}", "subtext": PERIODE_TITLE,
                                  "textStyle": {"fontSize": 13, "fontWeight": 700}},
                        "tooltip": {"trigger": "axis", "formatter": _tt_k3},
                        "legend": {"data": [f"Shift {s}" for s in shifts_k3], "top": 8, "right": 8,
                                   "icon": "circle", "itemWidth": 8,
                                   "textStyle": {"fontSize": 11}},
                        "grid": {"left": "3%", "right": "4%", "bottom": "3%",
                                 "containLabel": True},
                        "xAxis": {"type": "category", "data": [f"No.{s}" for s in sno_k3],
                                  "axisLabel": {"fontSize": 11, "interval": 0}},
                        "yAxis": {"type": "value", "min": 0, "max": 100,
                                  "axisLabel": {"formatter": "{value}%"}},
                        "series": ser_k3,
                    "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
                    }, height="300px", key="deep_shift_k3")

                _tt_trend_k3 = JsCode(
                    "function(p){"
                    "var ok_cnt="+str(_ok3r)+";var ng_cnt="+str(_ng3r)+";"
                    "var idx=p[0].dataIndex;"
                    "var ok=ok_cnt[idx]||0,ng=ng_cnt[idx]||0,tot=ok+ng;"
                    "return '<b>'+p[0].axisValue+'</b><br/>"
                    "OK: <b style=color:#22C55E;>'+ok+'</b> ('+p[0].value+'%)<br/>"
                    "NG: <b style=color:#EF4444;>'+ng+'</b> ('+(p[1]?p[1].value:0)+'%)<br/>"
                    "Total: <b>'+tot+'</b>';}"
                )
                st_echarts({
                    "title": {"text": f"Trend OK% — {f_model}", "subtext": PERIODE_TITLE + " | " + sub3,
                              "textStyle": {"fontSize": 13, "fontWeight": 700}},
                    "tooltip": {"trigger": "axis", "formatter": _tt_trend_k3},
                    "legend": {"data": ["OK%","NG%"], "right": 8, "top": 8,
                               "icon": "circle", "itemWidth": 8,
                               "textStyle": {"fontSize": 11}},
                    "grid": {"top": 48, "bottom": 32, "left": 48, "right": 20},
                    "xAxis": {"type": "category", "boundaryGap": False,
                              "data": x_order3,
                              "axisLabel": {"fontSize": 10, "interval": "auto"}},
                    "yAxis": {"type": "value", "min": 0, "max": 100,
                              "axisLabel": {"formatter": "{value}%"}},
                    "dataZoom": [{"type": "inside", "start": 0, "end": 100}],
                    "series": [
                        {"name": "OK%", "type": "line", "smooth": True,
                         "areaStyle": {"opacity": .12},
                         "itemStyle": {"color": "#22C55E"}, "data": ok3},
                        {"name": "NG%", "type": "line", "smooth": True,
                         "areaStyle": {"opacity": .12},
                         "itemStyle": {"color": "#EF4444"}, "data": ng3},
                    ],
                "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
                }, height="300px", key="chart_trend_k3")
# ══════════════════════════════════════════════════════════════════════
#  [A] 3 METHOD HELPER — masukkan ke dalam class DescriptivePage
#      letakkan persis sebelum _render_deep_breadcrumb
# ══════════════════════════════════════════════════════════════════════

    # ── Helper: hitung jumlah part (khusus Category=Produksi) ────────
    # Definisi "1 part" identik dengan Dashboard: 1 set titik ukur (sesuai
    # Mapping) dari satu SampleNo dalam satu kali pengukuran. Kunci unik:
    #   (Date, Shift, Cycle, SampleNo, PartName, ModelName)
    # KHUSUS Produksi agar konsisten dengan KPI part di Dashboard.
    def _count_parts(self, df: "pd.DataFrame") -> int:
        if df.empty:
            return 0
        if "Category" in df.columns:
            df = df[df["Category"] == "Produksi"]
            if df.empty:
                return 0
        group_cols = [c for c in ["Date", "Shift", "Cycle", "SampleNo", "PartName", "ModelName"]
                      if c in df.columns]
        return df.groupby(group_cols).ngroups

    def _calc_cpk(
        self,
        values: "pd.Series",
        usl: float,
        lsl: float,
    ) -> dict:
        return _calc_cpk_cached(tuple(values.dropna().tolist()), usl, lsl)

    # ── Helper: render Cpk card ──────────────────────────────────────
    def _render_cpk_card(self, cpk_result: dict, usl: float, lsl: float, nominal: float):
        """
        Render KPI card Cpk.
        cpk_result = output dari _calc_cpk().
        """
        if cpk_result is None:
            st.info("Data tidak cukup untuk menghitung Cpk (minimum 2 data point).")
            return

        cpk = cpk_result["cpk"]
        cp  = cpk_result["cp"]

        # Tentukan status
        if cpk >= 1.67:
            status_label = "Sangat Baik"
            status_color = "#059669"   # green-600
            status_bg    = "#ECFDF5"
            status_border= "#6EE7B7"
        elif cpk >= 1.33:
            status_label = "Capable"
            status_color = "#16A34A"
            status_bg    = "#F0FDF4"
            status_border= "#86EFAC"
        elif cpk >= 1.00:
            status_label = "Perlu perhatian"
            status_color = "#D97706"
            status_bg    = "#FFFBEB"
            status_border= "#FCD34D"
        else:
            status_label = "Tidak Capable"
            status_color = "#DC2626"
            status_bg    = "#FEF2F2"
            status_border= "#FCA5A5"

        cpk_color = status_color

        st.markdown(f"""
        <div style="background:#FFFFFF;border:0.5px solid #E2E8F0;border-radius:10px;
                    padding:16px;margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;
                      margin-bottom:12px;">
            <span style="font-size:13px;font-weight:700;color:#0F172A;">
              Process Capability (Cpk)
            </span>
            <span style="background:{status_bg};color:{status_color};
                         border:0.5px solid {status_border};border-radius:6px;
                         font-size:11px;font-weight:600;padding:3px 10px;">
              {status_label}
            </span>
          </div>

          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;
                      margin-bottom:10px;">
            <div style="background:#F8FAFC;border-radius:8px;padding:10px;text-align:center;">
              <div style="font-size:22px;font-weight:700;color:{cpk_color};">{cpk}</div>
              <div style="font-size:11px;color:#64748B;margin-top:2px;">Cpk</div>
              <div style="font-size:10px;color:#94A3B8;">Target &ge; 1.33</div>
            </div>
            <div style="background:#F8FAFC;border-radius:8px;padding:10px;text-align:center;">
              <div style="font-size:22px;font-weight:700;color:#334155;">{cp}</div>
              <div style="font-size:11px;color:#64748B;margin-top:2px;">Cp</div>
              <div style="font-size:10px;color:#94A3B8;">Potensi proses</div>
            </div>
            <div style="background:#F8FAFC;border-radius:8px;padding:10px;text-align:center;">
              <div style="font-size:22px;font-weight:700;color:#334155;">{cpk_result['n']}</div>
              <div style="font-size:11px;color:#64748B;margin-top:2px;">n sampel</div>
              <div style="font-size:10px;color:#94A3B8;">&nbsp;</div>
            </div>
          </div>

          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">
            <div style="background:#F8FAFC;border-radius:8px;padding:8px;text-align:center;">
              <div style="font-size:14px;font-weight:600;color:#334155;">
                {cpk_result['mean']}
              </div>
              <div style="font-size:10px;color:#64748B;">Mean aktual</div>
            </div>
            <div style="background:#F8FAFC;border-radius:8px;padding:8px;text-align:center;">
              <div style="font-size:14px;font-weight:600;color:#334155;">
                {nominal}
              </div>
              <div style="font-size:10px;color:#64748B;">Nominal</div>
            </div>
            <div style="background:#F8FAFC;border-radius:8px;padding:8px;text-align:center;">
              <div style="font-size:14px;font-weight:600;color:#334155;">
                {cpk_result['sigma']}
              </div>
              <div style="font-size:10px;color:#64748B;">Sigma proses</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Helper: deteksi kondisi proses di luar kendali & render tabel ──────────────────
    def _render_kendali_table(self, df_sorted: "pd.DataFrame", mean: float, sigma: float, chart_key_suffix: str):
        """
        Deteksi 7 kondisi proses di luar kendali pada df_sorted (sudah diurutkan Date→Shift→Cycle).
        Render tabel violation dan return list index yang violation
        (untuk highlight di grafik tren).

        Return:
          violations_by_rule: dict {rule_num: set(index_posisi)}
          violation_rows: list of dict untuk tabel
        """
        vals = df_sorted["Actual"].tolist()
        n    = len(vals)

        # Label waktu per baris
        def time_label(row):
            try:
                date_str  = row["Date"].strftime("%d %b %Y")
                shift_str = f"Shift {row['Shift']}"
                cycle_str = f"Cycle {row['Cycle']}"
                return f"{date_str} · {shift_str} · {cycle_str}"
            except Exception:
                return str(row.get("Date", ""))

        time_labels = df_sorted.apply(time_label, axis=1).tolist()

        # ── Deteksi masing-masing rule ──────────────────────────────
        violations_by_rule = {r: set() for r in range(1, 8)}
        violation_rows = []

        def add_violation(rule_num, indices, desc, severity):
            for i in indices:
                violations_by_rule[rule_num].add(i)
            # Rentang waktu
            times = [time_labels[i] for i in sorted(indices)]
            time_str = times[0] if len(times) == 1 else f"{times[0]}  →  {times[-1]}"
            actuals  = [round(vals[i], 5) for i in sorted(indices)]
            val_str  = str(actuals[0]) if len(actuals) == 1 else f"{min(actuals)} – {max(actuals)}"
            violation_rows.append({
                "rule":     rule_num,
                "label":    f"Rule {rule_num}",
                "desc":     desc,
                "time":     time_str,
                "val":      val_str,
                "n_pts":    len(indices),
                "severity": severity,
            })

        # Rule 1 — 1 titik > 3σ dari mean
        for i, v in enumerate(vals):
            if abs(v - mean) > 3 * sigma:
                add_violation(1, [i],
                    "Satu atau lebih titik data berada di luar batas kendali.",
                    "Critical")

        # Rule 2 — 9 titik berturut di satu sisi mean
        for i in range(n - 7):
            window = vals[i:i+8]
            if all(v > mean for v in window) or all(v < mean for v in window):
                add_violation(2, list(range(i, i+8)),
                    "Delapan titik data berurutan berada di satu sisi nilai rata-rata.",
                    "Warning")

        # Rule 3 — 7 titik naik atau turun terus (Nelson)
        for i in range(n - 6):
            window = vals[i:i+7]
            if all(window[j] < window[j+1] for j in range(6)) or \
               all(window[j] > window[j+1] for j in range(6)):
                add_violation(3, list(range(i, i+7)),
                    "Tujuh titik data berturut-turut yang meningkat atau menurun.",
                    "Warning")

        # Rule 4 — 14 titik selang-seling naik turun
        for i in range(n - 13):
            window = vals[i:i+14]
            alternating = all(
                (window[j] < window[j+1]) != (window[j+1] < window[j+2])
                for j in range(12)
            )
            if alternating:
                add_violation(4, list(range(i, i+14)),
                    "Empat belas titik data berurutan yang bergantian naik dan turun.",
                    "Warning")

        # Rule 5 — 2 dari 3 titik > 2σ di satu sisi
        for i in range(n - 2):
            window = vals[i:i+3]
            above = sum(1 for v in window if v > mean + 2*sigma)
            below = sum(1 for v in window if v < mean - 2*sigma)
            if above >= 2 or below >= 2:
                add_violation(5, list(range(i, i+3)),
                    "Dua titik data, dari tiga titik data berurutan, berada di sisi yang sama dari rata-rata di zona A atau di luarnya.",
                    "Warning")

        # Rule 6 — 4 dari 5 titik > 1σ di satu sisi
        for i in range(n - 4):
            window = vals[i:i+5]
            above = sum(1 for v in window if v > mean + sigma)
            below = sum(1 for v in window if v < mean - sigma)
            if above >= 4 or below >= 4:
                add_violation(6, list(range(i, i+5)),
                    "Empat titik data, dari lima titik data berurutan, berada di sisi yang sama dari rata-rata di zona B atau lebih jauh.",
                    "Warning")

        # Rule 7 — 15 titik berurutan dalam zona C (±1σ)
        for i in range(n - 14):
            window = vals[i:i+15]
            if all(abs(v - mean) < sigma for v in window):
                add_violation(7, list(range(i, i+15)),
                    "Lima belas titik data berurutan berada dalam zona C (di atas dan di bawah rata-rata).",
                    "Warning")

        # ── Render tabel ────────────────────────────────────────────
        total_violations = sum(len(s) for s in violations_by_rule.values())
        if total_violations == 0:
            badge_html = (
                '<span style="background:#F0FDF4;color:#166534;border:0.5px solid #86EFAC;'
                'border-radius:6px;font-size:11px;font-weight:600;padding:3px 10px;">'
                'Tidak ada violation</span>'
            )
        else:
            n_rules = sum(1 for s in violations_by_rule.values() if s)
            badge_html = (
                f'<span style="background:#FEF2F2;color:#991B1B;border:0.5px solid #FCA5A5;'
                f'border-radius:6px;font-size:11px;font-weight:600;padding:3px 10px;">'
                f'{n_rules} rule terdeteksi</span>'
            )

        # ── Build seluruh HTML kendali dalam satu blok ────────────────
        thead = """<thead><tr style="border-bottom:1px solid #E2E8F0;">
          <th style="padding:6px 8px;text-align:left;font-size:11px;font-weight:600;color:#64748B;width:12%;">Rule</th>
          <th style="padding:6px 8px;text-align:left;font-size:11px;font-weight:600;color:#64748B;width:30%;">Deskripsi</th>
          <th style="padding:6px 8px;text-align:left;font-size:11px;font-weight:600;color:#64748B;width:20%;">Artinya</th>
          <th style="padding:6px 8px;text-align:left;font-size:11px;font-weight:600;color:#64748B;width:18%;">Waktu</th>
          <th style="padding:6px 8px;text-align:left;font-size:11px;font-weight:600;color:#64748B;width:12%;">Nilai aktual</th>
          <th style="padding:6px 8px;text-align:center;font-size:11px;font-weight:600;color:#64748B;width:6%;">N</th>
          <th style="padding:6px 8px;text-align:left;font-size:11px;font-weight:600;color:#64748B;width:10%;">Severity</th>
        </tr></thead>"""

        if not violation_rows:
            tbody = """<tbody><tr><td colspan="7" style="padding:16px 8px;text-align:center;
                color:#94A3B8;font-size:12px;">Tidak ada pola abnormal terdeteksi</td></tr></tbody>"""
        else:
            sev_style = {
                "Critical": ("background:#FEF2F2;color:#991B1B;border:0.5px solid #FCA5A5;",
                             "background:#FEF2F2;"),
                "Warning":  ("background:#FFFBEB;color:#92400E;border:0.5px solid #FCD34D;",
                             "background:#FFFBEB;"),
            }
            rule_color = {1: "#EF4444", 2: "#F59E0B", 3: "#8B5CF6",
                          4: "#06B6D4", 5: "#10B981", 6: "#F97316", 7: "#3B82F6"}
            KONTEKS_D = {
                1: "Indikasi penyebab khusus (special cause) yang perlu segera diinvestigasi.",
                2: "Proses mengalami pergeseran (shift) — kemungkinan perubahan material, mesin, atau operator.",
                3: "Drift pada proses — misalnya keausan alat atau perubahan bertahap.",
                4: "Kemungkinan over-adjustment atau gangguan sistematis pada pengukuran.",
                5: "Peringatan dini pergeseran — dua dari tiga titik mendekati batas kendali.",
                6: "Pergeseran halus dari rata-rata — proses mulai tidak stabil.",
                7: "Proses terlalu konsisten di dekat rata-rata — kemungkinan stratifikasi data.",
            }
            rows_html = ""
            for vr in violation_rows:
                badge_s, row_bg = sev_style.get(vr["severity"], ("", ""))
                rc = rule_color.get(vr["rule"], "#64748B")
                konteks = KONTEKS_D.get(vr["rule"], "")
                rows_html += (
                    f'<tr style="{row_bg}border-bottom:0.5px solid #E2E8F0;">'
                    f'<td style="padding:7px 8px;vertical-align:top;">'
                    f'<span style="font-weight:600;color:{rc};">{vr["label"]}</span></td>'
                    f'<td style="padding:7px 8px;color:#475569;font-size:11px;vertical-align:top;">{vr["desc"]}</td>'
                    f'<td style="padding:7px 8px;color:#64748B;font-size:11px;vertical-align:top;font-style:italic;">{konteks}</td>'
                    f'<td style="padding:7px 8px;color:#334155;font-size:11px;vertical-align:top;">{vr["time"]}</td>'
                    f'<td style="padding:7px 8px;font-weight:600;color:#334155;vertical-align:top;">{vr["val"]}</td>'
                    f'<td style="padding:7px 8px;text-align:center;color:#334155;vertical-align:top;">{vr["n_pts"]}</td>'
                    f'<td style="padding:7px 8px;vertical-align:top;">'
                    f'<span style="border-radius:5px;font-size:10px;font-weight:600;padding:2px 7px;{badge_s}">{vr["severity"]}</span>'
                    f'</td></tr>'
                )
            tbody = f"<tbody>{rows_html}</tbody>"

        st.markdown(
            f'<div style="background:white;border:1px solid #E2E8F0;border-radius:10px;'
            f'padding:14px 16px;margin:8px 0 12px;box-shadow:0 1px 2px rgba(15,23,42,.04);">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
            f'<span style="font-size:13px;font-weight:700;color:#0F172A;">Deteksi Proses di Luar Kendali</span>'
            f'{badge_html}</div>'
            f'<div style="overflow-x:auto;">'
            f'<table style="width:100%;border-collapse:collapse;font-size:12px;">'
            f'{thead}{tbody}</table></div>'
            f'<div style="font-size:11px;color:#94A3B8;margin-top:8px;">'
            f'Rule dideteksi berdasarkan urutan Date → Shift → Cycle. '
            f'Titik berring di grafik = violation.</div></div>',
            unsafe_allow_html=True
        )

        with st.expander("Keterangan Kondisi Proses di Luar Kendali", expanded=False):
            RULE_META_DS = [
                (1,"#EF4444","Critical","Satu atau lebih titik data berada di luar batas kendali."),
                (2,"#F59E0B","Warning", "Delapan titik data berurutan berada di satu sisi nilai rata-rata."),
                (3,"#8B5CF6","Warning", "Tujuh titik data berturut-turut yang meningkat atau menurun."),
                (4,"#06B6D4","Warning", "Empat belas titik data berurutan yang bergantian naik dan turun."),
                (5,"#10B981","Warning", "Dua dari tiga titik berurutan berada di zona A atau di luarnya."),
                (6,"#F97316","Warning", "Empat dari lima titik berurutan berada di zona B atau lebih jauh."),
                (7,"#3B82F6","Warning", "Lima belas titik berurutan berada dalam zona C."),
            ]
            cols_ds = st.columns(2)
            for idx_ds, (r_num, clr, sev, desc) in enumerate(RULE_META_DS):
                is_crit = sev == "Critical"
                sev_bg  = "#FEE2E2" if is_crit else "#EFF6FF"
                sev_clr = "#991B1B" if is_crit else "#1D4ED8"
                card_bg = "#FFF0F0" if is_crit else "#F0F4FF"
                with cols_ds[idx_ds % 2]:
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
                        _get_rule_img_html_ds(r_num, clr) +
                        '</div>',
                        unsafe_allow_html=True
                    )

        return violations_by_rule


        # Tabel data terfilter selalu di bawah
        st.markdown(
            '<div style="font-size:14px;font-weight:700;color:#0F172A;'
            'margin-top:24px;margin-bottom:12px;">Filtered Inspection Data</div>',
            unsafe_allow_html=True
        )
        if not df.empty:
            st.dataframe(df, use_container_width=True, height=400)
        else:
            st.info("Tidak ada data yang sesuai dengan filter yang dipilih.")

    # ── Breadcrumb untuk Deep Investigation ──────────────────────────
    def _render_deep_breadcrumb(self):
        """Breadcrumb + tombol back untuk navigasi Deep."""
        f_part  = st.session_state.get("shared_part", "Semua Part")
        f_model = st.session_state.get("shared_model", "Semua Model")
        active  = st.session_state.get("active_ref")

        items = ["Semua Part"]
        if f_part != "Semua Part":
            items.append(f_part)
        if f_model != "Semua Model":
            items.append(f_model)
        if active:
            items.append(f"Titik {active}")

        bc = " <span style='color:#CBD5E1;'>›</span> ".join([
            f"<span style='color:{'#0F172A;font-weight:600' if i == len(items)-1 else '#64748B'};'>{x}</span>"
            for i, x in enumerate(items)
        ])

        st.markdown(
            f'<div style="font-size:12px;margin-bottom:6px;padding-top:6px;">{bc}</div>',
            unsafe_allow_html=True
        )

    # ════════════════════════════════════════════════════════════════
    #  SHARED — Detail satu titik+parameter (dipakai Quick & Deep)
    # ════════════════════════════════════════════════════════════════

    # ── Helper: overview multi-line semua sampel ─────────────────────
    def _render_sample_overview(
        self,
        df_all: "pd.DataFrame",
        ref: str,
        param: str,
        usl: float,
        lsl: float,
        nominal: float,
        key_suffix: str,
    ):
        from streamlit_echarts import st_echarts as _ech, JsCode

        PALETTE = [
            "#6366f1","#0ea5e9","#10b981","#f59e0b","#ef4444",
            "#8b5cf6","#ec4899","#14b8a6","#f97316","#84cc16",
            "#a855f7","#06b6d4","#22c55e","#f43f5e","#64748b",
        ]

        df = df_all.copy()
        df["_donly"] = df["Date"].dt.date
        df = df.sort_values(["_donly", "Shift", "Cycle"])
        df["time_key"] = df["Date"].dt.strftime("%d %b") + " S" + df["Shift"].astype(str)
        time_order = list(dict.fromkeys(df["time_key"].tolist()))
        samples = sorted(df["SampleNo"].dropna().astype(str).unique(), key=lambda s: [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", str(s))])

        series_list = []
        for i, s in enumerate(samples):
            df_s = df[df["SampleNo"].astype(str) == s]
            pts = []
            for t_key in time_order:
                row = df_s[df_s["time_key"] == t_key]
                if row.empty:
                    pts.append(None)
                else:
                    v   = round(float(row["Actual"].iloc[0]), 4)
                    dev = round(float(row["Deviation"].iloc[0]), 4)
                    j   = row["Judgement"].iloc[0]
                    is_ng = j == "NG"
                    pts.append({
                        "value": v, "dev": dev, "j": j,
                        "itemStyle": {"color": "#ef4444", "borderColor": "#ef4444",
                                      "borderWidth": 3} if is_ng else {},
                    })
            clr = PALETTE[i % len(PALETTE)]
            series_list.append({
                "name": s, "type": "line",
                "data": pts, "connectNulls": False, "smooth": False,
                "symbol": "circle", "symbolSize": 7,
                "lineStyle": {"color": clr, "width": 1.8},
                "itemStyle": {"color": clr},
            })

        mark_line_data = [
            {"yAxis": usl, "lineStyle": {"color": "#EF4444", "width": 2, "type": "solid"},
             "label": {"formatter": f"USL {usl}", "fontSize": 10, "color": "#EF4444"}},
            {"yAxis": lsl, "lineStyle": {"color": "#EF4444", "width": 2, "type": "solid"},
             "label": {"formatter": f"LSL {lsl}", "fontSize": 10, "color": "#EF4444"}},
            {"yAxis": nominal, "lineStyle": {"color": "#22C55E", "width": 1.5, "type": "dashed"},
             "label": {"formatter": f"Nom {nominal}", "fontSize": 10, "color": "#22C55E"}},
        ]
        if series_list:
            series_list[0]["markLine"] = {"symbol": ["none","none"], "silent": True,
                                          "data": mark_line_data}

        # ── Cpk mini-cards per sampel — di bawah Target Nominal ──────
        st.markdown(
            '<div style="font-size:12px;font-weight:600;color:#64748B;'
            'margin:14px 0 8px;">Cpk per Sampel</div>',
            unsafe_allow_html=True
        )
        cols_n = min(len(samples), 5)
        cols_g = st.columns(cols_n, gap="small")
        for i, s in enumerate(samples):
            df_s  = df[df["SampleNo"].astype(str) == s]
            cpk_r = self._calc_cpk(df_s["Actual"].dropna(), usl, lsl)
            ng_c  = int((df_s["Judgement"] == "NG").sum())
            ok_c  = int((df_s["Judgement"] == "OK").sum())
            cpk_v = cpk_r["cpk"] if cpk_r else None
            if cpk_v is None:
                c_clr, c_bg, c_str = "#94A3B8", "#F8FAFC", "—"
            elif cpk_v >= 1.67:
                c_clr, c_bg, c_str = "#16A34A", "#DCFCE7", f"{cpk_v:.2f}"
            elif cpk_v >= 1.33:
                c_clr, c_bg, c_str = "#D97706", "#FEF3C7", f"{cpk_v:.2f}"
            else:
                c_clr, c_bg, c_str = "#DC2626", "#FEE2E2", f"{cpk_v:.2f}"
            border = "#FECACA" if ng_c > 0 else "#E2E8F0"
            with cols_g[i % cols_n]:
                st.markdown(
                    f'<div style="background:white;border:1px solid {border};'
                    f'border-radius:8px;padding:10px 8px;text-align:center;margin-bottom:6px;">'
                    f'<div style="font-size:13px;font-weight:600;color:#0F172A;">{s}</div>'
                    f'<div style="font-size:17px;font-weight:700;color:{c_clr};'
                    f'background:{c_bg};border-radius:6px;padding:3px 0;margin:4px 0;">'
                    f'Cpk {c_str}</div>'
                    f'<div style="font-size:11px;color:#64748B;">'
                    f'<span style="color:#22C55E">{round(ok_c/(ok_c+ng_c)*100,1) if (ok_c+ng_c) else 0}% OK</span> · '
                    f'<span style="color:#EF4444">{round(ng_c/(ok_c+ng_c)*100,1) if (ok_c+ng_c) else 0}% NG</span></div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

        tooltip_ov = JsCode("""
        function(params) {
            if (!params || params.length === 0) return '';
            var html = '<div style="font-size:12px;line-height:1.9;min-width:200px">'
                     + '<b>' + params[0].axisValue + '</b><br/>';
            params.forEach(function(p) {
                if (p.data === null || p.data === undefined) return;
                var d = p.data;
                var st  = (typeof d === 'object' && d.j)   ? d.j   : '—';
                var val = (typeof d === 'object') ? d.value : d;
                var dev = (typeof d === 'object' && d.dev !== undefined) ? d.dev : '—';
                var clr = st === 'NG' ? '#ef4444' : '#22c55e';
                html += p.marker + ' <b>' + p.seriesName + '</b>: ' + val
                      + ' &nbsp;<span style="color:' + clr + ';font-weight:700;">[' + st + ']</span>'
                      + ' (dev: ' + dev + ')<br/>';
            });
            html += '</div>';
            return html;
        }
        """)

        _ech({
            "title": {
                "text": f"Tren Aktual per Sampel — {ref} · {param}",
                "subtext": f"Semua sampel · {len(time_order)} shift · titik merah = NG",
                "left": 12, "top": 8,
                "textStyle": {"fontSize": 13, "fontWeight": 700, "color": "#0F172A"},
                "subtextStyle": {"color": "#94A3B8", "fontSize": 10},
            },
            "legend": {
                "data": samples, "right": 16, "top": 12,
                "icon": "circle", "itemWidth": 8,
                "textStyle": {"color": "#64748B", "fontSize": 11},
            },
            "grid": {"top": 60, "right": 100, "bottom": 55, "left": 65},
            "tooltip": {"trigger": "axis", "backgroundColor": "#1E293B", "borderColor": "#334155",
                        "textStyle": {"color": "#F8FAFC", "fontSize": 12}, "formatter": tooltip_ov},
            "xAxis": {
                "type": "category", "data": time_order,
                "axisLine": {"lineStyle": {"color": "#E2E8F0"}},
                "axisTick": {"show": False},
                "axisLabel": {"color": "#94A3B8", "fontSize": 9, "rotate": 30, "interval": 0},
                "splitLine": {"show": False},
            },
            "yAxis": {
                "type": "value", "scale": True,
                "axisLabel": {"color": "#94A3B8", "fontSize": 10},
                "splitLine": {"lineStyle": {"color": "#F1F5F9", "type": "dashed"}},
            },
            "series": series_list,
            "dataZoom": [{"type": "inside", "start": 0, "end": 100},
                         {"type": "slider", "bottom": 8, "height": 16}],
        "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
        }, height="380px", key=f"ov_trend_{key_suffix}")

    # ── Helper: detail satu sampel ───────────────────────────────────
    def _render_single_detail(
        self,
        df_s: "pd.DataFrame",
        ref: str,
        param: str,
        usl: float,
        lsl: float,
        nominal: float,
        sname: str,
        key_suffix: str,
    ):
        from streamlit_echarts import st_echarts as _ech

        if df_s.empty:
            st.warning(f"Tidak ada data untuk sampel {sname}.")
            return

        # Cpk card
        cpk_result = self._calc_cpk(df_s["Actual"], usl, lsl)
        self._render_cpk_card(cpk_result, usl, lsl, nominal)

        # Tren aktual + Deteksi Kendali
        df_trend = df_s.copy()
        df_trend["_donly"] = df_trend["Date"].dt.date
        df_trend = df_trend.sort_values(["_donly","Shift","Cycle"]).drop(columns=["_donly"]).dropna(subset=["Actual","Date"])
        x_labels = df_trend.apply(
            lambda r: f"{r['Date'].strftime('%d %b')} S{r['Shift']}",
            axis=1
        ).tolist()
        y_actual = df_trend["Actual"].tolist()

        if cpk_result:
            proc_mean  = cpk_result["mean"]
            proc_sigma = cpk_result["sigma"]
        else:
            proc_mean  = float(df_trend["Actual"].mean())
            proc_sigma = float(df_trend["Actual"].std(ddof=1)) if len(df_trend) > 1 else 0.0

        ucl = round(proc_mean + 3*proc_sigma, 5) if proc_sigma else usl
        lcl = round(proc_mean - 3*proc_sigma, 5) if proc_sigma else lsl

        vbr = {r: set() for r in range(1,8)}
        if proc_sigma > 0 and len(y_actual) >= 2:
            for i,v in enumerate(y_actual):
                if abs(v-proc_mean) > 3*proc_sigma: vbr[1].add(i)
            for i in range(len(y_actual)-7):
                w=y_actual[i:i+8]
                if all(v>proc_mean for v in w) or all(v<proc_mean for v in w):
                    for j in range(i,i+8): vbr[2].add(j)
            for i in range(len(y_actual)-6):
                w=y_actual[i:i+7]
                if all(w[j]<w[j+1] for j in range(6)) or all(w[j]>w[j+1] for j in range(6)):
                    for j in range(i,i+7): vbr[3].add(j)
            for i in range(len(y_actual)-13):
                w=y_actual[i:i+14]
                if all((w[j]<w[j+1])!=(w[j+1]<w[j+2]) for j in range(12)):
                    for j in range(i,i+14): vbr[4].add(j)
            for i in range(len(y_actual)-2):
                w=y_actual[i:i+3]
                if sum(1 for v in w if v>proc_mean+2*proc_sigma)>=2 or \
                   sum(1 for v in w if v<proc_mean-2*proc_sigma)>=2:
                    for j in range(i,i+3): vbr[5].add(j)
            for i in range(len(y_actual)-4):
                w=y_actual[i:i+5]
                if sum(1 for v in w if v>proc_mean+proc_sigma)>=4 or \
                   sum(1 for v in w if v<proc_mean-proc_sigma)>=4:
                    for j in range(i,i+5): vbr[6].add(j)
            for i in range(len(y_actual)-14):
                w=y_actual[i:i+15]
                if all(abs(v-proc_mean)<proc_sigma for v in w):
                    for j in range(i,i+15): vbr[7].add(j)

        # Bangun lookup tooltip per index: nilai aktual, deviasi, judgement, rule
        import json as _jl5
        _jl5_judgements = df_trend["Judgement"].tolist()
        _jl5_deviations = [round(float(v),4) if pd.notna(v) else None
                           for v in df_trend["Deviation"].tolist()]
        _rule_map_l5 = {}
        for r in range(1,8):
            for idx in vbr[r]:
                _rule_map_l5.setdefault(idx, []).append(f"Rule {r}")
        _rule_map_l5_list = {str(k): ", ".join(v) for k,v in _rule_map_l5.items()}

        _tt_l5 = JsCode(
            "function(params){"
            "var p=params[0];"
            "var judgements="+_jl5.dumps(_jl5_judgements)+";"
            "var devs="+_jl5.dumps(_jl5_deviations)+";"
            "var rules="+_jl5.dumps(_rule_map_l5_list)+";"
            "var idx=p.dataIndex;"
            "var j=judgements[idx]||'—';"
            "var dev=devs[idx]!==null?devs[idx]:'—';"
            "var rule=rules[String(idx)]||'';"
            "var jclr=j==='NG'?'#EF4444':'#22C55E';"
            "var val=typeof p.data==='object'?p.data.value:p.data;"
            "var html='<b>'+p.axisValue+'</b><br/>';"
            "html+='Aktual: <b>'+val+'</b><br/>';"
            "html+='Deviasi: <b>'+dev+'</b><br/>';"
            "html+='Status: <b style=color:'+jclr+';>'+j+'</b>';"
            "if(rule) html+='<br/><span style=color:#F59E0B;font-weight:700;>⚠ '+rule+'</span>';"
            "return html;}"
        )

        rc = {1:"#EF4444",2:"#F59E0B",3:"#8B5CF6",4:"#06B6D4",5:"#10B981",6:"#F97316",7:"#3B82F6"}

        def pt_style(i):
            for r in [1,2,3,4,5,6,7]:
                if i in vbr[r]:
                    return {"color":"#6366F1","borderColor":rc[r],"borderWidth":2.5}
            return {"color":"#6366F1"}

        series_data = [{"value":v,"itemStyle":pt_style(i)} for i,v in enumerate(y_actual)]

        st.markdown("""
        <div style="display:flex;flex-wrap:wrap;gap:14px;font-size:11px;
                    color:#64748B;margin-bottom:6px;">
          <span>&#9632; <span style="color:#EF4444;">solid</span> USL/LSL</span>
          <span>&#8943; <span style="color:#EF4444;">dashed</span> UCL/LCL (3&sigma;)</span>
          <span>&#8943; <span style="color:#22C55E;">dashed</span> Nominal</span>
          <span style="color:#EF4444;">&#9711;</span> Rule 1 &nbsp;
          <span style="color:#F59E0B;">&#9711;</span> Rule 2 &nbsp;
          <span style="color:#8B5CF6;">&#9711;</span> Rule 3 &nbsp;
          <span style="color:#06B6D4;">&#9711;</span> Rule 4 &nbsp;
          <span style="color:#10B981;">&#9711;</span> Rule 5 &nbsp;
          <span style="color:#F97316;">&#9711;</span> Rule 6 &nbsp;
          <span style="color:#3B82F6;">&#9711;</span> Rule 7
        </div>
        """, unsafe_allow_html=True)

        _ech({
            "title": {"text": f"Tren — {ref} · {param} · {sname}", "left":12, "top":8,
                      "textStyle":{"fontSize":13,"fontWeight":700,"color":"#0F172A"}},
            "graphic": [{"type":"text","right":36,"top":9,
                "style":{"text":(f"Nom {nominal}  USL {usl}  UCL {ucl}"
                               f"  LCL {lcl}  LSL {lsl}"),
                         "font":"10px Arial","fill":"#64748B","textAlign":"right"}}],
            "grid": {"top":50,"right":80,"bottom":55,"left":60},
            "tooltip": {"trigger":"axis","formatter": _tt_l5},
            "xAxis": {"type":"category","data":x_labels,
                      "axisLabel":{"rotate":20,"fontSize":9,"interval":"auto"}},
            "yAxis": {"type":"value",
                      "min": round(min(y_actual+[usl,lsl,ucl,lcl,nominal])-abs(proc_sigma)*0.5, 5),
                      "max": round(max(y_actual+[usl,lsl,ucl,lcl,nominal])+abs(proc_sigma)*0.5, 5),
                      "name":"Aktual","axisLabel":{"fontSize":10}},
            "dataZoom": [{"type":"inside","start":0,"end":100},
                         {"type":"slider","bottom":8,"height":16}],
            "series": [{
                "data": series_data,"type":"line","symbol":"circle","symbolSize":8,
                "lineStyle":{"color":"#6366F1","width":1.5},
                "markLine":{"symbol":["none","none"],"silent":True,"data":[
                    {"yAxis":usl,"lineStyle":{"color":"#EF4444","width":2,"type":"solid"},
                     "label":{"formatter":f"USL {usl}","fontSize":10,"color":"#EF4444"}},
                    {"yAxis":lsl,"lineStyle":{"color":"#EF4444","width":2,"type":"solid"},
                     "label":{"formatter":f"LSL {lsl}","fontSize":10,"color":"#EF4444"}},
                    {"yAxis":ucl,"lineStyle":{"color":"#EF4444","width":1,"type":"dashed"},
                     "label":{"formatter":f"UCL {ucl}","fontSize":9,"color":"#EF4444"}},
                    {"yAxis":lcl,"lineStyle":{"color":"#EF4444","width":1,"type":"dashed"},
                     "label":{"formatter":f"LCL {lcl}","fontSize":9,"color":"#EF4444"}},
                    {"yAxis":nominal,"lineStyle":{"color":"#22C55E","width":1.5,"type":"dashed"},
                     "label":{"formatter":f"Nom {nominal}","fontSize":10,"color":"#22C55E"}},
                ]},
            }],
        "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
        }, height="340px", key=f"sd_trend_{key_suffix}_{sname}")

        if proc_sigma > 0 and len(y_actual) >= 2:
            self._render_kendali_table(
                df_trend.reset_index(drop=True),
                proc_mean, proc_sigma,
                chart_key_suffix=f"sd_{key_suffix}_{sname}"
            )

        c1, c2 = st.columns(2, gap="small")
        with c1:
            jc   = df_s["Judgement"].value_counts()
            pd_  = [{"name":str(k),"value":int(v)} for k,v in jc.items()]
            pc_  = ["#22C55E" if k=="OK" else "#EF4444" for k in jc.index]
            _ech({
                "title":{"text":"OK vs NG","left":"center","top":8,
                         "textStyle":{"fontSize":12,"fontWeight":700}},
                "tooltip":{"trigger":"item","formatter":"{b}: <b>{c}</b> ({d}%)"},
                "color":pc_,
                "series":[{"type":"pie","radius":["45%","70%"],"center":["50%","55%"],
                           "data":pd_,"itemStyle":{"borderColor":"#fff","borderWidth":2},
                           "label":{"show":True,"formatter":"{b}\n{d}%","fontSize":11}}],
            "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
            }, height="240px", key=f"sd_pie_{key_suffix}_{sname}")
        with c2:
            shifts = sorted(df_s["Shift"].dropna().astype(str).unique().tolist())
            _sh_ok_pct, _sh_ng_pct, _sh_ok_cnt, _sh_ng_cnt, sh_labels = [], [], [], [], []
            for sh in shifts:
                d = df_s[df_s["Shift"].astype(str) == sh]["Judgement"]
                if not d.empty:
                    _t = len(d)
                    _ok = int((d=="OK").sum())
                    _ng = int((d=="NG").sum())
                    sh_labels.append(f"Shift {sh}")
                    _sh_ok_pct.append(round(_ok/_t*100,1) if _t else 0)
                    _sh_ng_pct.append(round(_ng/_t*100,1) if _t else 0)
                    _sh_ok_cnt.append(_ok)
                    _sh_ng_cnt.append(_ng)
            import json as _jl5s
            _tt_shift = JsCode(
                "function(p){"
                "var ok_cnt="+_jl5s.dumps(_sh_ok_cnt)+";var ng_cnt="+_jl5s.dumps(_sh_ng_cnt)+";"
                "var idx=p[0].dataIndex;"
                "var ok=ok_cnt[idx],ng=ng_cnt[idx],tot=ok+ng;"
                "return '<b>'+p[0].name+'</b><br/>"
                "OK: <b style=color:#22C55E;>'+ok+'</b> ('+p[0].value+'%)<br/>"
                "NG: <b style=color:#EF4444;>'+ng+'</b> ('+(p[1]?p[1].value:0)+'%)<br/>"
                "Total: <b>'+tot+'</b>';}"
            )
            _ech({
                "title":{"text":"OK% vs NG% per Shift","left":12,"top":8,
                         "textStyle":{"fontSize":12,"fontWeight":700}},
                "grid":{"top":38,"right":16,"bottom":30,"left":16,"containLabel":True},
                "tooltip":{"trigger":"axis","axisPointer":{"type":"shadow"},
                           "formatter": _tt_shift},
                "legend":{"data":["OK%","NG%"],"top":8,"right":16,"itemWidth":10,"itemHeight":10,
                          "textStyle":{"fontSize":10}},
                "xAxis":{"type":"category","data":sh_labels,"axisLabel":{"fontSize":10}},
                "yAxis":{"type":"value","max":100,"axisLabel":{"formatter":"{value}%","fontSize":9}},
                "series":[
                    {"name":"OK%","type":"bar","stack":"jd","data":_sh_ok_pct,
                     "itemStyle":{"color":"#22C55E","borderRadius":[4,4,0,0]},
                     "label":{"show":True,"position":"inside","formatter":"{c}%","fontSize":9,"color":"#fff"},
                     "emphasis":{"itemStyle":{"color":"#16A34A"}}},
                    {"name":"NG%","type":"bar","stack":"jd","data":_sh_ng_pct,
                     "itemStyle":{"color":"#EF4444","borderRadius":[4,4,0,0]},
                     "label":{"show":True,"position":"inside","formatter":"{c}%","fontSize":9,"color":"#fff"},
                     "emphasis":{"itemStyle":{"color":"#DC2626"}}},
                ],
            "toolbox": {"feature": {"saveAsImage": {"title": "Download PNG"}}},
            }, height="240px", key=f"sd_shift_{key_suffix}_{sname}")

    def _render_analisa(
        self,
        df: "pd.DataFrame",
        ref: str,
        param: str,
        usl: float,
        lsl: float,
        nominal: float,
        uppertol: float,
        lowertol: float,
        sel: str,
        key_suffix: str,
    ):
        """
        Hasilkan ringkasan analisa otomatis dari data titik ukur.
        Rule-based: Kapabilitas → Tren → Pola SPC → Distribusi NG → Rekomendasi
        """
        import numpy as np
        from local_db import get_root_causes

        if df.empty:
            return

        df = df.dropna(subset=["Actual"]).copy()
        if df.empty:
            return

        y = df["Actual"].tolist()
        n = len(y)

        # ── 1. Kapabilitas ────────────────────────────────────────
        mean_v  = float(np.mean(y))
        sigma_v = float(np.std(y, ddof=1)) if n > 1 else 0.0
        if sigma_v > 0:
            cpu  = (usl - mean_v) / (3 * sigma_v)
            cpl  = (mean_v - lsl) / (3 * sigma_v)
            cpk  = round(min(cpu, cpl), 2)
            cp   = round((usl - lsl) / (6 * sigma_v), 2)
        else:
            cpk, cp = None, None

        n_ok  = int((df["Judgement"] == "OK").sum())
        n_ng  = int((df["Judgement"] == "NG").sum())
        n_tot = n_ok + n_ng
        ng_rate = round(n_ng / n_tot * 100, 1) if n_tot else 0

        # Shift dominan NG
        shift_ng = None
        if "Shift" in df.columns and n_ng > 0:
            sc = df[df["Judgement"]=="NG"]["Shift"].astype(str).value_counts()
            if not sc.empty:
                shift_ng = sc.index[0]
                shift_ng_pct = round(sc.iloc[0] / n_ng * 100)

        # ── 2. Tren (linear regression) ───────────────────────────
        slope, intercept = np.polyfit(range(n), y, 1) if n >= 3 else (0.0, mean_v)
        slope_per_shift = round(slope, 5)

        # Estimasi shift ke batas
        est_shifts = None
        est_direction = None
        if slope > 1e-6:
            s = (usl - y[-1]) / slope
            if 0 < s <= 100:
                est_shifts = int(round(s))
                est_direction = "USL"
        elif slope < -1e-6:
            s = (lsl - y[-1]) / slope
            if 0 < s <= 100:
                est_shifts = int(round(s))
                est_direction = "LSL"

        # Pergeseran mean terbaru (7 data terakhir vs keseluruhan)
        mean_shift_str = None
        if n >= 10:
            mean_recent = float(np.mean(y[-7:]))
            delta = round(mean_recent - mean_v, 4)
            if abs(delta) > sigma_v * 0.3:
                arah = "naik" if delta > 0 else "turun"
                mean_shift_str = f"Mean 7 data terakhir {arah} {abs(delta):.4f} mm dari rata-rata keseluruhan"

        # ── 3. Pola SPC ───────────────────────────────────────────
        RULE_DESC = {
            1: "titik di luar batas kendali (outlier)",
            2: "8 titik berurutan di satu sisi rata-rata (pergeseran proses)",
            3: "7 titik naik/turun berurutan (drift)",
            4: "14 titik bergantian naik-turun (osilasi)",
            5: "2 dari 3 titik di zona A (pergeseran awal)",
            6: "4 dari 5 titik di zona B (drift halus)",
            7: "15 titik dalam zona C (proses terlalu konsisten/stratifikasi)",
        }
        vbr = {r: set() for r in range(1, 8)}
        if sigma_v > 0 and n >= 2:
            for i, v in enumerate(y):
                if abs(v - mean_v) > 3 * sigma_v: vbr[1].add(i)
            for i in range(n - 7):
                w = y[i:i+8]
                if all(v > mean_v for v in w) or all(v < mean_v for v in w):
                    for j in range(i, i+8): vbr[2].add(j)
            for i in range(n - 6):
                w = y[i:i+7]
                if all(w[j] < w[j+1] for j in range(6)) or all(w[j] > w[j+1] for j in range(6)):
                    for j in range(i, i+7): vbr[3].add(j)
            for i in range(n - 13):
                w = y[i:i+14]
                if all((w[j] < w[j+1]) != (w[j+1] < w[j+2]) for j in range(12)):
                    for j in range(i, i+14): vbr[4].add(j)
            for i in range(n - 2):
                w = y[i:i+3]
                if (sum(1 for v in w if v > mean_v + 2*sigma_v) >= 2 or
                        sum(1 for v in w if v < mean_v - 2*sigma_v) >= 2):
                    for j in range(i, i+3): vbr[5].add(j)
            for i in range(n - 4):
                w = y[i:i+5]
                if (sum(1 for v in w if v > mean_v + sigma_v) >= 4 or
                        sum(1 for v in w if v < mean_v - sigma_v) >= 4):
                    for j in range(i, i+5): vbr[6].add(j)
            for i in range(n - 14):
                w = y[i:i+15]
                if all(abs(v - mean_v) < sigma_v for v in w):
                    for j in range(i, i+15): vbr[7].add(j)
        triggered_rules = [r for r in range(1, 8) if vbr[r]]

        # ── 4. Root Cause historis ────────────────────────────────
        REKOM = {
            "Mesin / Machine":  "Cek kalibrasi probe dan kondisi mesin sebelum shift berikutnya",
            "Setup / Fixture":  "Verifikasi posisi fixture dan datum reference",
            "Material":         "Lakukan incoming inspection — pisahkan material suspect",
            "Operator":         "Brief operator terkait SOP setup titik ini",
            "Program CMM":      "Update program CMM sesuai revisi drawing terbaru",
            "Tooling":          "Cek tool wear dan ganti insert jika perlu",
            "Lainnya":          "Investigasi lebih lanjut bersama engineer",
        }
        PARAM_REKOM = {
            "posisi": "Cek fixture dan datum reference",
            "position": "Cek fixture dan datum reference",
            "distance": "Verifikasi tool wear dan probe approach",
            "diameter": "Cek tool wear dan kondisi tooling",
            "flatness": "Cek surface condition dan material",
        }

        top_rc_cat  = None
        top_rc_pct  = None
        all_rcs = get_root_causes()
        if all_rcs:
            import pandas as _pd_rc
            df_rc = _pd_rc.DataFrame(all_rcs)
            # Filter ke part+model+ref+param ini
            part_val  = df["PartName"].iloc[0]  if "PartName"  in df.columns else ""
            model_val = df["ModelName"].iloc[0] if "ModelName" in df.columns else ""
            mask = (
                (df_rc["part"]      == str(part_val)) &
                (df_rc["model"]     == str(model_val)) &
                (df_rc["ref"]       == str(ref)) &
                (df_rc["parameter"] == str(param))
            )
            df_rc_titik = df_rc[mask]
            if not df_rc_titik.empty:
                vc = df_rc_titik["category"].value_counts()
                top_rc_cat = vc.index[0]
                top_rc_pct = round(vc.iloc[0] / len(df_rc_titik) * 100)

        rekom_str = (
            REKOM.get(top_rc_cat, "Investigasi lebih lanjut bersama engineer")
            if top_rc_cat else
            next((v for k, v in PARAM_REKOM.items() if k in param.lower()),
                 "Investigasi penyebab bersama engineer")
        )

        # ── Render card ───────────────────────────────────────────
        sample_label = f"Sample {sel}" if sel != "Semua" else "Semua Sample"

        # Warna header berdasarkan kondisi terburuk
        if cpk is not None and cpk < 1.0 or ng_rate > 15:
            hdr_bg, hdr_clr, hdr_icon = "#FEF2F2", "#991B1B", "🔴"
        elif cpk is not None and cpk < 1.33 or ng_rate > 5:
            hdr_bg, hdr_clr, hdr_icon = "#FFFBEB", "#92400E", "🟡"
        else:
            hdr_bg, hdr_clr, hdr_icon = "#F0FDF4", "#14532D", "🟢"

        # ── Susun poin-poin insight ───────────────────────────────
        poin = []

        # Kapabilitas
        if cpk is not None:
            if cpk >= 1.67:
                cap_str = f"Proses <b>sangat kapabel</b> (Cpk {cpk})"
            elif cpk >= 1.33:
                cap_str = f"Proses <b>kapabel</b> (Cpk {cpk})"
            elif cpk >= 1.0:
                cap_str = f"Proses <b>mendekati batas</b>, perlu dipantau (Cpk {cpk})"
            else:
                cap_str = f"Proses <b>tidak kapabel</b>, tindakan segera diperlukan (Cpk {cpk})"
            mean_delta = round(mean_v - nominal, 4)
            arah_mean  = "di atas" if mean_delta > 0 else "di bawah"
            sign       = "+" if mean_delta >= 0 else ""
            cap_str   += f". Mean aktual <b>{round(mean_v,4)}</b> ({sign}{mean_delta} mm {arah_mean} nominal)"
            poin.append(("📊 Kapabilitas", cap_str))
        else:
            poin.append(("📊 Kapabilitas", "Data tidak cukup untuk menghitung Cpk."))

        # NG Rate
        ng_str = f"<b>{n_ng} NG dari {n_tot} pengukuran ({ng_rate}%)</b>"
        if shift_ng:
            ng_str += f", dominan di <b>Shift {shift_ng}</b> ({shift_ng_pct}%)"
        if n_ng == 0:
            ng_str = f"<b>Tidak ada NG</b> — semua {n_tot} pengukuran OK ✓"
        poin.append(("🔢 Hasil Pengukuran", ng_str))

        # Tren
        if abs(slope) < 1e-6:
            tren_str = "Proses <b>stabil</b>, tidak ada drift signifikan"
        elif slope > 0:
            tren_str = (f"Nilai cenderung <b>naik</b> ({slope_per_shift:+.5f} mm/shift)"
                        + (f", diprediksi menyentuh <b>USL dalam ±{est_shifts} shift</b> "
                           f"(berdasarkan tren linear)" if est_shifts else ""))
        else:
            tren_str = (f"Nilai cenderung <b>turun</b> ({slope_per_shift:+.5f} mm/shift)"
                        + (f", diprediksi menyentuh <b>LSL dalam ±{est_shifts} shift</b> "
                           f"(berdasarkan tren linear)" if est_shifts else ""))
        if mean_shift_str:
            tren_str += f". {mean_shift_str}."
        poin.append(("📈 Tren", tren_str))

        # Pola SPC
        if triggered_rules:
            rule_parts = [f"<b>Rule {r}</b> — {RULE_DESC[r]}" for r in triggered_rules]
            spc_str = "; ".join(rule_parts)
        else:
            spc_str = "Tidak ada pola SPC yang terpicu — proses dalam kendali statistik ✓"
        poin.append(("⚡ Pola SPC", spc_str))

        # Rekomendasi
        if top_rc_cat:
            rek_str = (f"Berdasarkan <b>{len(df_rc_titik)} histori root cause</b>, "
                       f"penyebab dominan adalah <b>{top_rc_cat} ({top_rc_pct}%)</b>. "
                       f"→ {rekom_str}")
        else:
            rek_str = f"Belum ada root cause tercatat. → {rekom_str}"
        poin.append(("💡 Rekomendasi", rek_str))

        # ── Render HTML ───────────────────────────────────────────
        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
        rows_html = "".join([
            f'<div style="display:flex;gap:12px;align-items:flex-start;'
            f'padding:10px 0;border-bottom:1px solid #F1F5F9;">'
            f'<div style="font-size:11px;font-weight:700;color:#64748B;'
            f'white-space:nowrap;min-width:130px;padding-top:1px;">{label}</div>'
            f'<div style="font-size:12px;color:#334155;line-height:1.6;">{text}</div>'
            f'</div>'
            for label, text in poin
        ])
        st.markdown(
            f'<div style="background:white;border:1px solid #E2E8F0;'
            f'border-radius:12px;overflow:hidden;margin-top:4px;">'
            f'<div style="background:{hdr_bg};padding:12px 20px;'
            f'display:flex;align-items:center;gap:8px;">'
            f'<span style="font-size:16px;">{hdr_icon}</span>'
            f'<span style="font-size:14px;font-weight:700;color:{hdr_clr};">'
            f'Hasil Analisa & Kesimpulan</span>'
            f'<span style="font-size:11px;color:{hdr_clr};margin-left:4px;'
            f'font-weight:500;opacity:0.8;">— {ref} · {param} · {sample_label}</span>'
            f'</div>'
            f'<div style="padding:4px 20px 12px;">{rows_html}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    def _render_point_detail(
        self,
        df_detail: "pd.DataFrame",
        ref: str,
        param: str,
        key_suffix: str = "shared",
    ):
        """
        Render detail satu titik ukur — dipakai Quick Level 5 dan Deep Kondisi 4.
        Konten: toleransi card → sample picker → overview semua sampel atau detail 1 sampel.
        """
        if df_detail.empty:
            st.warning(f"Tidak ada data untuk {ref} · {param}.")
            return

        # ── Toleransi ─────────────────────────────────────────────
        nominal  = float(df_detail["Nominal"].dropna().iloc[0])  if not df_detail["Nominal"].dropna().empty  else 0.0
        uppertol = float(df_detail["Uppertol"].dropna().iloc[0]) if not df_detail["Uppertol"].dropna().empty else 0.0
        lowertol = float(df_detail["Lowertol"].dropna().iloc[0]) if not df_detail["Lowertol"].dropna().empty else 0.0
        usl      = round(nominal + uppertol, 4)
        lsl      = round(nominal + lowertol, 4)

        # ── Sample picker — di atas Target Nominal ────────────────
        samples = sorted(df_detail["SampleNo"].dropna().astype(str).unique(), key=lambda s: [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", str(s))])
        if len(samples) > 1:
            pill_opts = ["Semua"] + samples
            st.markdown('<div style="font-size:12px;font-weight:600;color:#0F172A;margin-bottom:4px;">Filter No. Sample</div>', unsafe_allow_html=True)
            sel = st.pills(
                "No. Sample",
                pill_opts,
                default="Semua",
                key=f"rpd_samp_{key_suffix}",
                selection_mode="single",
                label_visibility="collapsed",
            ) or "Semua"
        else:
            sel = samples[0] if samples else "Semua"

        # ── Badge sampel (muncul kalau sel != "Semua") ───────────────
        if sel != "Semua":
            st.markdown(
                f'<div style="display:inline-block;background:#DBEAFE;color:#1D4ED8;'
                f'font-size:12px;font-weight:700;padding:4px 14px;border-radius:20px;'
                f'margin-bottom:12px;">📍 Sampel: {sel}</div>',
                unsafe_allow_html=True
            )

        # ── Toleransi ─────────────────────────────────────────────
        _is_angle = any(k in param.lower() for k in ["angle","angular","deg","°","sudut"])
        _unit     = "°" if _is_angle else " mm"
        st.markdown(
            f'<div style="background:white;border:0.5px solid #E2E8F0;border-radius:10px;'
            f'padding:16px 24px;display:flex;justify-content:space-around;'
            f'text-align:center;margin-bottom:16px;">'
            f'<div><div style="font-size:11px;color:#64748B;font-weight:600;'
            f'text-transform:uppercase;letter-spacing:.5px;">Target Nominal</div>'
            f'<div style="font-size:22px;font-weight:700;color:#3B82F6;">{nominal}{_unit}</div></div>'
            f'<div style="width:1px;background:#F1F5F9;"></div>'
            f'<div><div style="font-size:11px;color:#64748B;font-weight:600;'
            f'text-transform:uppercase;letter-spacing:.5px;">Upper Tolerance</div>'
            f'<div style="font-size:22px;font-weight:700;color:#EF4444;">+{uppertol}{_unit}</div></div>'
            f'<div style="width:1px;background:#F1F5F9;"></div>'
            f'<div><div style="font-size:11px;color:#64748B;font-weight:600;'
            f'text-transform:uppercase;letter-spacing:.5px;">Lower Tolerance</div>'
            f'<div style="font-size:22px;font-weight:700;color:#EF4444;">{lowertol}{_unit}</div></div>'
            f'</div>',
            unsafe_allow_html=True
        )

        if sel == "Semua":
            self._render_sample_overview(df_detail, ref, param, usl, lsl, nominal, key_suffix)
            self._render_analisa(
                df=df_detail, ref=ref, param=param,
                usl=usl, lsl=lsl, nominal=nominal,
                uppertol=uppertol, lowertol=lowertol,
                sel="Semua", key_suffix=key_suffix,
            )
        else:
            df_s = df_detail[df_detail["SampleNo"].astype(str) == sel].copy()
            self._render_single_detail(df_s, ref, param, usl, lsl, nominal, sel, key_suffix)
            self._render_analisa(
                df=df_s, ref=ref, param=param,
                usl=usl, lsl=lsl, nominal=nominal,
                uppertol=uppertol, lowertol=lowertol,
                sel=sel, key_suffix=key_suffix,
            )