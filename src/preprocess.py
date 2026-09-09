"""METAR 원본을 분석용 형태로 정리한다.

Iowa State 아카이브는 미국 단위(°F, knot, mile, inch)로 내려주므로 미터법으로 바꾸고,
결측 표기(M/T)를 정리한 뒤 시간 단위 인덱스를 만든다.

항공편 데이터와의 병합은 API 응답 스키마가 확정된 뒤에 추가한다.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_PROCESSED, DATA_RAW, ICAO  # noqa: E402

# 기상현상 코드 중 지연과 직결되는 것들
SIGNIFICANT_WX = {
    "TS": "뇌전",
    "FG": "안개",
    "SN": "눈",
    "FZ": "착빙",
    "RA": "비",
    "BR": "박무",
}


def load_metar(station: str = ICAO) -> pd.DataFrame:
    """연도별 CSV를 모두 읽어 하나로 합친다."""
    files = sorted(DATA_RAW.glob(f"metar_{station}_*.csv"))
    if not files:
        raise FileNotFoundError(
            f"{DATA_RAW}에 METAR 파일이 없다. 먼저 실행: python src/collect_metar.py"
        )

    df = pd.concat(
        (pd.read_csv(f, na_values=["M", "T", ""], low_memory=False) for f in files),
        ignore_index=True,
    )
    df["valid"] = pd.to_datetime(df["valid"])
    return df.sort_values("valid").reset_index(drop=True)


def to_metric(df: pd.DataFrame) -> pd.DataFrame:
    """미국 단위를 미터법으로 변환한다."""
    out = pd.DataFrame({"obs_time": df["valid"]})

    out["temp_c"] = (df["tmpf"] - 32) * 5 / 9
    out["dewpoint_c"] = (df["dwpf"] - 32) * 5 / 9
    out["wind_dir"] = df["drct"]
    out["wind_ms"] = df["sknt"] * 0.514444
    out["gust_ms"] = df["gust"] * 0.514444
    out["precip_mm"] = df["p01i"] * 25.4
    out["visibility_km"] = df["vsby"] * 1.60934
    out["cloud_base_ft"] = df["skyl1"]
    out["cloud_cover"] = df["skyc1"]

    # 기온-이슬점 차. 작을수록 안개 위험이 크다.
    out["dewpoint_spread"] = out["temp_c"] - out["dewpoint_c"]

    wx = df["wxcodes"].fillna("")
    for code, name in SIGNIFICANT_WX.items():
        out[f"wx_{code.lower()}"] = wx.str.contains(code).astype(int)
        out[f"wx_{code.lower()}"].attrs["label"] = name

    return out


def add_time_keys(df: pd.DataFrame) -> pd.DataFrame:
    """항공편과 시간 단위로 JOIN 하기 위한 키를 만든다."""
    df = df.copy()
    df["hour_key"] = df["obs_time"].dt.floor("h")
    df["month"] = df["obs_time"].dt.month
    df["hour"] = df["obs_time"].dt.hour
    return df


def main() -> None:
    raw = load_metar()
    print(f"원본 {len(raw):,}행 ({raw['valid'].min()} ~ {raw['valid'].max()})")

    df = add_time_keys(to_metric(raw))

    # 같은 시간대에 관측이 여러 건이면 마지막 것을 쓴다
    df = df.drop_duplicates(subset="hour_key", keep="last")

    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    out = DATA_PROCESSED / f"metar_{ICAO}.parquet"
    df.to_parquet(out, index=False)

    print(f"정리 후 {len(df):,}행 → {out.name}")
    print(f"\n결측률 상위:\n{(df.isna().mean() * 100).sort_values(ascending=False).head(8)}")


if __name__ == "__main__":
    main()
