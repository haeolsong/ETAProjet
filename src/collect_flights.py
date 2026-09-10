"""김해공항 항공편 운항 정보 수집 (공공데이터포털 · 한국공항공사).

API 는 searchday 기준 D-3 ~ D+6 을 조회할 수 있다(D-4 부터는 0건).
따라서 **다음날 한 번만 조회하면 확정된 실제도착시각**을 받을 수 있고,
수집에 실패해도 3일 안에 다시 돌리면 복구된다.

    python src/collect_flights.py                  # 어제치
    python src/collect_flights.py --date 2026-09-08  # 누락일 복구 (D-3 까지)

타겟 변수: delay_minutes = estimateddatetime - scheduledatetime
"""

import argparse
import csv
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_RAW, IATA  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
BASE = "https://apis.data.go.kr/B551178/flight-status"
ROWS = 100  # 문서에 없지만 100 초과 시 HTTP_ERROR 가 난다
MAX_BACKFILL_DAYS = 3  # API 가 D-3 까지만 준다

# 김해 도착편의 출발지연을 얻으려면 출발지 공항에서 따로 조회해야 한다.
# 이 API 는 한국공항공사 소관이라 국내선 출발지만 가능하다(해외·인천 제외).
ORIGINS = ("GMP", "CJU")


def fetch(kind: str, key: str, searchday: str, airport: str = IATA) -> list[dict]:
    """arrival | depart 한 종류를 전체 페이지 조회한다."""
    items: list[dict] = []
    page = 1
    while True:
        resp = requests.get(
            f"{BASE}/{kind}",
            params={
                "serviceKey": key,
                "pageNo": page,
                "numOfRows": ROWS,
                "searchday": searchday,
                "airport_code": airport,
                "type": "json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()

        # 이 API 는 오류도 HTTP 200 으로 내려보낸다. 본문을 봐야 알 수 있다.
        if "response" not in payload:
            err = payload.get("OpenAPI_ServiceResponse", {}).get("cmmMsgHeader", {})
            raise RuntimeError(f"{kind} {searchday} 조회 실패: {err}")

        body = payload["response"]["body"]

        chunk = body.get("items") or {}
        chunk = chunk.get("item", []) if isinstance(chunk, dict) else chunk
        if isinstance(chunk, dict):
            chunk = [chunk]
        items.extend(chunk)

        if len(items) >= int(body.get("totalCount", 0)) or not chunk:
            return items
        page += 1


def collect(key: str, day: date) -> None:
    searchday = f"{day:%Y%m%d}"
    now = datetime.now(KST).isoformat(timespec="seconds")

    rows = []
    for kind in ("arrival", "depart"):
        for item in fetch(kind, key, searchday):
            item["_collected_at"] = now
            rows.append(item)

    if not rows:
        print(f"{day} 수집된 항공편 없음 — D-3 을 넘겼거나 API 장애")
        return

    write_csv(rows, DATA_RAW / f"flights_{day:%Y-%m-%d}.csv")
    print(f"{day} {len(rows)}건 → flights_{day:%Y-%m-%d}.csv")

    # 출발지 공항에서 김해행 편만 골라 따로 저장한다(출발지연 산출용).
    origin_rows = []
    for origin in ORIGINS:
        for item in fetch("depart", key, searchday, airport=origin):
            if item.get("arrvAirportCode") == IATA:
                item["_collected_at"] = now
                origin_rows.append(item)

    if origin_rows:
        write_csv(origin_rows, DATA_RAW / f"flights_origin_{day:%Y-%m-%d}.csv")
        print(f"{day} 출발지 {len(origin_rows)}건 → flights_origin_{day:%Y-%m-%d}.csv")


def write_csv(rows: list[dict], out: Path) -> None:
    """확정된 하루치 전량이므로 덮어쓴다(재실행해도 결과가 같다)."""
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    fields = sorted({k for r in rows for k in r})
    with out.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="김해공항 항공편 수집")
    parser.add_argument("--date", help="조회일 YYYY-MM-DD (기본: 어제)")
    args = parser.parse_args()

    today = datetime.now(KST).date()
    day = date.fromisoformat(args.date) if args.date else today - timedelta(days=1)

    if not 0 <= (today - day).days <= MAX_BACKFILL_DAYS:
        sys.exit(f"{day} 는 조회 범위 밖이다. API 는 D-{MAX_BACKFILL_DAYS} ~ 오늘만 준다.")

    load_dotenv()
    key = os.getenv("DATA_GO_KR_KEY")
    if not key:
        sys.exit(
            "DATA_GO_KR_KEY 가 없다.\n"
            "  1. https://data.go.kr — '한국공항공사_실시간 항공기 운항정보 조회_GW' 활용신청\n"
            "  2. cp .env.example .env\n"
            "  3. .env 에 발급받은 키 입력"
        )

    # Encoding/Decoding 키 어느 쪽을 넣어도 되게 한다.
    # requests 가 params 를 다시 인코딩하므로 Encoding 키는 %2B → %252B 로 깨진다.
    collect(unquote(key), day)


if __name__ == "__main__":
    main()
