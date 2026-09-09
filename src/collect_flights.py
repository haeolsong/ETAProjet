"""김해공항 항공편 운항 정보 수집 (공공데이터포털).

국내 항공편의 편별 과거 이력은 공개 API로 대량 조회가 불가능하다.
이 수집기를 상시 가동해 이력을 직접 축적한다.

키 발급 직후에는 먼저 --probe 로 응답 필드를 확인한다.
어떤 시각 필드가 오는지에 따라 타겟 변수(delay_minutes) 정의가 달라진다.
"""

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_RAW, IATA  # noqa: E402

KST = ZoneInfo("Asia/Seoul")

# 한국공항공사_항공기 운항정보 (공공데이터포털 15000126)
# 활용신청 승인 후 상세 문서에서 엔드포인트가 바뀌었다면 --url 로 덮어쓴다.
DEFAULT_URL = "http://openapi.airport.co.kr/service/rest/FlightStatusList/getFlightStatusList"


def request_flights(url: str, key: str, io_type: str, rows: int = 500) -> requests.Response:
    """운항 정보를 조회한다. io_type: I(도착) / O(출발)."""
    params = {
        "serviceKey": key,
        "schAirCode": IATA,
        "schLineType": "D",  # 국내선
        "schIOType": io_type,
        "numOfRows": rows,
        "pageNo": 1,
        "_type": "json",
    }
    return requests.get(url, params=params, timeout=60)


def probe(url: str, key: str) -> None:
    """응답 원문을 그대로 출력한다. 필드 구조 파악용."""
    print("=" * 70)
    print("응답 필드 확인 — 아래 항목을 반드시 눈으로 확인할 것")
    print("  1. 계획시각 필드가 있는가")
    print("  2. 변경/실제 도착시각 필드가 함께 오는가  ← 타겟 변수를 좌우한다")
    print("  3. 지연·결항 상태 코드가 있는가")
    print("=" * 70)

    for io_type, label in (("I", "도착"), ("O", "출발")):
        resp = request_flights(url, key, io_type, rows=3)
        print(f"\n--- {label} (schIOType={io_type}) ---")
        print(f"HTTP {resp.status_code}")
        print(resp.text[:3000])


def collect(url: str, key: str) -> None:
    """도착·출발 편을 오늘 날짜 파일에 append 한다."""
    now = datetime.now(KST)
    out = DATA_RAW / f"flights_{now:%Y-%m-%d}.csv"
    DATA_RAW.mkdir(parents=True, exist_ok=True)

    rows = []
    for io_type in ("I", "O"):
        resp = request_flights(url, key, io_type)
        resp.raise_for_status()
        payload = resp.json()

        items = payload["response"]["body"]["items"]
        items = items.get("item", []) if isinstance(items, dict) else items
        if isinstance(items, dict):
            items = [items]

        for item in items:
            item["_io_type"] = io_type
            item["_collected_at"] = now.isoformat(timespec="seconds")
            rows.append(item)

    if not rows:
        print("수집된 항공편 없음")
        return

    fields = sorted({k for r in rows for k in r})
    write_header = not out.exists()
    with out.open("a", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)}건 → {out.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="김해공항 항공편 수집")
    parser.add_argument("--probe", action="store_true", help="응답 원문만 출력 (필드 확인용)")
    parser.add_argument("--url", default=DEFAULT_URL, help="엔드포인트 덮어쓰기")
    args = parser.parse_args()

    load_dotenv()
    key = os.getenv("DATA_GO_KR_KEY")
    if not key:
        sys.exit(
            "DATA_GO_KR_KEY 가 없다.\n"
            "  1. https://data.go.kr 에서 '한국공항공사_항공기 운항정보' 활용신청\n"
            "  2. cp .env.example .env\n"
            "  3. .env 에 발급받은 키 입력"
        )

    if args.probe:
        probe(args.url, key)
    else:
        collect(args.url, key)


if __name__ == "__main__":
    main()
