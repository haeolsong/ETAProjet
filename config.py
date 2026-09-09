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

# --- 출력 가독성 ---
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)
pd.set_option("display.max_rows", 100)
pd.set_option("display.float_format", lambda v: f"{v:,.2f}")

_install_traceback(show_locals=False)
