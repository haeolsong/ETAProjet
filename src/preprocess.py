"""METAR·항공편 원본을 분석용 형태로 정리하고 병합한다.

Iowa State 아카이브는 미국 단위(°F, knot, mile, inch)로 내려주므로 미터법으로 바꾸고,
결측 표기(M/T)를 정리한 뒤 시간 단위 인덱스를 만든다.

항공편은 도착편만 골라 코드쉐어 중복을 제거하고 delay_minutes 를 계산한 뒤,
계획도착시각의 시(hour) 를 키로 METAR 와 JOIN 한다.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_PROCESSED, DATA_RAW, ICAO  # noqa: E402

# 기상현상 코드 중 지연과 직결되는 것들
# 김해공항 활주로 진방위(TRUE BRG). 18L·18R 이 평행이라 하나로 계산한다.
# 출처: 국토교통부 eAIP RKPK AD 2.12 (18L/18R = 173.95°, 36L/36R = 353.95°)
# METAR 풍향도 진북 기준이므로 자기편차 보정이 필요 없다.
RUNWAY_BEARING = 173.95

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

    # 활주로에 수직인 바람 성분(횡풍). 좌풍·우풍 모두 착륙을 어렵게 하므로 절댓값을 쓴다.
    # 무풍(풍속 0)이면 풍향이 0 으로 기록되지만 곱해져 0 이 되므로 따로 걸러내지 않는다.
    angle = np.radians(out["wind_dir"] - RUNWAY_BEARING)
    out["crosswind_ms"] = (out["wind_ms"] * np.sin(angle)).abs()

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


def load_flights() -> pd.DataFrame:
    """일자별 CSV를 모두 읽어 김해 도착편만 남긴다."""
    files = sorted(DATA_RAW.glob("flights_*.csv"))
    if not files:
        raise FileNotFoundError(
            f"{DATA_RAW}에 항공편 파일이 없다. 먼저 실행: python src/collect_flights.py"
        )

    df = pd.concat((pd.read_csv(f, dtype=str) for f in files), ignore_index=True)
    return df[df["io"] == "I"].reset_index(drop=True)


def clean_flights(df: pd.DataFrame) -> pd.DataFrame:
    """코드쉐어·미확정편을 걸러내고 지연시간을 계산한다."""
    # 코드쉐어는 한 대의 항공기가 여러 편명으로 중복 계상된다.
    # masterflightid 는 코드쉐어 행에만 채워지므로, 단독편(결측)과
    # 코드쉐어의 주편명(flightid == masterflightid)만 남긴다.
    keep = df["masterflightid"].isna() | (df["flightid"] == df["masterflightid"])
    df = df[keep]

    # 같은 fid 가 그대로 두 번 내려오는 경우가 있다.
    df = df.drop_duplicates(subset="fid")

    # 도착이 확정된 편만 쓴다. 결항편은 estimateddatetime 이 계획시각과 같아
    # 지연 0분으로 보이고, 미도착편의 시각은 실적이 아니라 예정값이다.
    df = df[df["rmkKor"] == "도착"]

    sched = pd.to_datetime(df["scheduledatetime"], format="%Y%m%d%H%M")
    actual = pd.to_datetime(df["estimateddatetime"], format="%Y%m%d%H%M")

    out = pd.DataFrame(
        {
            "sched_time": sched,
            "actual_time": actual,
            "delay_minutes": (actual - sched).dt.total_seconds() / 60,
            "airline": df["airline"],
            "flight_no": df["flightid"],
            "origin": df["depAirportCode"],
            "line": df["line"],
        }
    )

    out["hour_key"] = out["sched_time"].dt.floor("h")
    out["dow"] = out["sched_time"].dt.dayofweek
    out["hour"] = out["sched_time"].dt.hour
    out["month"] = out["sched_time"].dt.month
    return out.sort_values("sched_time").reset_index(drop=True)


def load_dep_delay() -> pd.DataFrame:
    """출발지 공항 자료에서 편명·운항일별 출발지연을 만든다.

    한국공항공사 API 는 국내선 출발지(GMP·CJU)만 조회할 수 있어
    김해 도착편의 약 30% 에만 붙는다. 나머지는 NaN 으로 남는다.
    """
    files = sorted(DATA_RAW.glob("flights_origin_*.csv"))
    if not files:
        return pd.DataFrame(columns=["flight_no", "flight_date", "dep_delay"])

    df = pd.concat((pd.read_csv(f, dtype=str) for f in files), ignore_index=True)

    # 도착편과 동일한 정제 규칙을 적용한다.
    keep = df["masterflightid"].isna() | (df["flightid"] == df["masterflightid"])
    df = df[keep].drop_duplicates(subset="fid")
    df = df[df["rmkKor"] == "출발"]

    sched = pd.to_datetime(df["scheduledatetime"], format="%Y%m%d%H%M")
    actual = pd.to_datetime(df["estimateddatetime"], format="%Y%m%d%H%M")

    return pd.DataFrame(
        {
            "flight_no": df["flightid"],
            "flight_date": sched.dt.date,
            "dep_delay": (actual - sched).dt.total_seconds() / 60,
        }
    ).drop_duplicates(subset=["flight_no", "flight_date"])


def merge(flights: pd.DataFrame, metar: pd.DataFrame) -> pd.DataFrame:
    """계획도착시각의 시(hour) 를 키로 기상 관측을 붙인다."""
    # hour·month 는 항공편 쪽에서 이미 만들었다. 기상 관측 쪽 것을 쓰면
    # 매칭 실패한 행에서 NaN 이 된다.
    weather = metar.drop(columns=["obs_time", "hour", "month"])
    return flights.merge(weather, on="hour_key", how="left")


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

    raw_f = load_flights()
    flights = clean_flights(raw_f)
    print(f"\n항공편 도착 {len(raw_f):,}행 → 정제 {len(flights):,}행")

    merged = merge(flights, df)
    matched = merged["temp_c"].notna().mean() * 100
    print(f"기상 매칭 {matched:.1f}%")

    dep = load_dep_delay()
    merged["flight_date"] = merged["sched_time"].dt.date
    merged = merged.merge(dep, on=["flight_no", "flight_date"], how="left")
    merged = merged.drop(columns="flight_date")
    filled = merged["dep_delay"].notna().mean() * 100
    print(f"출발지연 매칭 {filled:.1f}% (국내선 한정이라 30% 내외가 정상)")

    out = DATA_PROCESSED / "dataset.parquet"
    merged.to_parquet(out, index=False)
    print(f"병합 {len(merged):,}행 → {out.name}")
    print(f"\ndelay_minutes:\n{merged['delay_minutes'].describe()}")


if __name__ == "__main__":
    main()
