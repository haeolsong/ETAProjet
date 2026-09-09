"""김해공항 ETA 예측 대시보드 (뼈대).

현재는 수집된 기상 자료를 확인하는 수준이다.
모델 예측 화면은 항공편 데이터가 축적된 뒤(11월) 추가한다.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_PROCESSED, ICAO  # noqa: E402

st.set_page_config(page_title="김해공항 ETA 예측", page_icon="✈️", layout="wide")

st.title("✈️ 김해공항 항공편 ETA 예측")
st.caption("동아대학교 도전학기제 · 송하얼 · 박성준")

metar_path = DATA_PROCESSED / f"metar_{ICAO}.parquet"

if not metar_path.exists():
    st.warning(
        "전처리된 기상 자료가 없습니다.\n\n"
        "```\npython src/collect_metar.py --start-year 2019\n"
        "python src/preprocess.py\n```"
    )
    st.stop()

df = pd.read_parquet(metar_path)

st.subheader("수집 현황")
c1, c2, c3 = st.columns(3)
c1.metric("관측 건수", f"{len(df):,}")
c2.metric("시작", f"{df['obs_time'].min():%Y-%m-%d}")
c3.metric("최근", f"{df['obs_time'].max():%Y-%m-%d}")

st.subheader("기상 추이")
metric = st.selectbox(
    "항목",
    ["visibility_km", "wind_ms", "precip_mm", "temp_c", "dewpoint_spread"],
)
st.line_chart(df.set_index("obs_time")[metric].tail(2000))

st.subheader("저시정 발생 빈도 (시정 < 1.6km)")
low = df.assign(low_vis=(df["visibility_km"] < 1.6).astype(int))
st.bar_chart(low.groupby("month")["low_vis"].mean())

st.info("모델 예측 화면은 항공편 데이터 축적 후 추가됩니다.")
