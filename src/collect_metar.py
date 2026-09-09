"""김해공항(RKPK) METAR 관측 자료 수집.

Iowa State Mesonet ASOS 아카이브에서 연 단위로 내려받아 data/raw/에 저장한다.
API 키가 필요 없으며 1954년부터의 자료를 제공한다.
"""

import argparse
import sys
import time
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_RAW, ICAO  # noqa: E402

URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"

# 지연 예측에 쓸 관측 항목
FIELDS = [
    "tmpf",  # 기온 (°F)
    "dwpf",  # 이슬점 (°F)
    "drct",  # 풍향 (deg)
    "sknt",  # 풍속 (knot)
    "gust",  # 돌풍 (knot)
    "p01i",  # 1시간 강수 (inch)
    "vsby",  # 시정 (mile)
    "skyc1",  # 운량 1층
    "skyl1",  # 운고 1층 (ft)
    "skyc2",
    "skyl2",
    "wxcodes",  # 기상현상 코드 (RA, SN, FG, TS ...)
]


def fetch_year(station: str, year: int) -> str:
    """해당 연도 1년치 METAR를 CSV 문자열로 받는다."""
    params = [
        ("station", station),
        ("year1", year),
        ("month1", 1),
        ("day1", 1),
        ("year2", year + 1),
        ("month2", 1),
        ("day2", 1),
        ("tz", "Asia/Seoul"),
        ("format", "onlycomma"),
        ("latlon", "no"),
        ("missing", "M"),
        ("trace", "T"),
        ("report_type", 3),  # 정시 관측(METAR)
    ]
    params += [("data", f) for f in FIELDS]

    resp = requests.get(URL, params=params, timeout=300)
    resp.raise_for_status()
    return resp.text


def main() -> None:
    parser = argparse.ArgumentParser(description="RKPK METAR 수집")
    parser.add_argument("--station", default=ICAO)
    parser.add_argument("--start-year", type=int, default=2019)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    parser.add_argument("--force", action="store_true", help="이미 받은 연도도 다시 받는다")
    args = parser.parse_args()

    DATA_RAW.mkdir(parents=True, exist_ok=True)

    for year in range(args.start_year, args.end_year + 1):
        out = DATA_RAW / f"metar_{args.station}_{year}.csv"

        # 지난 연도 파일은 더 늘어나지 않으므로 건너뛴다. 올해 파일은 항상 갱신.
        if out.exists() and not args.force and year < date.today().year:
            print(f"[건너뜀] {year} — 이미 있음 ({out.name})")
            continue

        print(f"[수집] {year} ...", end=" ", flush=True)
        text = fetch_year(args.station, year)
        rows = text.count("\n") - 1  # 헤더 제외

        if rows <= 0:
            print("자료 없음")
            continue

        out.write_text(text)
        print(f"{rows:,}행 → {out.name}")
        time.sleep(1)  # 공개 아카이브에 대한 예의

    print("\n완료. 수집된 파일:")
    for f in sorted(DATA_RAW.glob(f"metar_{args.station}_*.csv")):
        print(f"  {f.name}  ({f.stat().st_size / 1024:,.0f} KB)")


if __name__ == "__main__":
    main()
