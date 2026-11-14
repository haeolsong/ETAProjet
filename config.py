"""프로젝트 공통 설정: 경로 상수와 출력 가독성 설정."""

from pathlib import Path

import pandas as pd
from rich.traceback import install as _install_traceback

# --- 경로 ---
ROOT = Path(__file__).parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"

# --- 김해공항 ---
ICAO = "RKPK"
IATA = "PUS"

# --- 출발지 공항 (김해 도착편의 약 80%, 2026-11-13 기준 편수 상위 15곳) ---
# IATA → ICAO. 출발지 기상(METAR)을 붙이는 데 쓴다. 목록 밖 출발지는 NaN 으로 남는다.
ORIGIN_ICAO = {
    "CJU": "RKPC",
    "GMP": "RKSS",
    "TPE": "RCTP",
    "FUK": "RJFF",
    "KIX": "RJBB",
    "NRT": "RJAA",
    "ICN": "RKSI",
    "PVG": "ZSPD",
    "DAD": "VVDN",
    "CXR": "VVCR",
    "CTS": "RJCC",
    "HKG": "VHHH",
    "KHH": "RCKH",
    "BKK": "VTBS",
    "HAN": "VVNB",
}

# --- 출력 가독성 ---
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)
pd.set_option("display.max_rows", 100)
pd.set_option("display.float_format", lambda v: f"{v:,.2f}")

_install_traceback(show_locals=False)
