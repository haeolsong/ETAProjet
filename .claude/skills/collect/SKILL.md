---
name: collect
description: 김해공항 ETA 프로젝트의 데이터 수집 절차. METAR 기상 자료 내려받기, 항공편 일일 수집기 실행·스케줄 확인, 수집 누락일 점검을 다룬다. 데이터를 받거나 수집 상태를 확인할 때 사용한다.
---

# 데이터 수집 절차

## 기상 (METAR) — 키 불필요, 언제든 실행 가능

```bash
source venv/bin/activate
python src/collect_metar.py --start-year 2019
```

- 출처: Iowa State Mesonet ASOS 아카이브 (RKPK, 1954년~현재)
- 저장 위치: `data/raw/metar_RKPK_{연도}.csv`
- 연 단위로 나눠 받으며, **지난 연도 파일은 이미 있으면 건너뛴다**
- 올해 파일은 실행할 때마다 갱신된다 (자료가 계속 늘어나므로)
- 전체를 다시 받으려면 `--force`

정상 수집 시 연간 약 8,000~8,800행(시간당 1건)이다. 크게 모자라면 아카이브 장애를 의심한다.

## 항공편 — 공공데이터포털 키 필요

```bash
python src/collect_flights.py                    # 복구 창 점검 + 누락분 자동 수집
python src/collect_flights.py --date 2026-09-08  # 특정일 강제 재수집
```

**인자 없이 실행하면 D-1 ~ D-3 을 스스로 점검한다.** 맥이 자고 있어 스케줄러가 며칠을
걸렀어도 다음 실행에서 따라잡는다. 이미 받은 날은 건너뛰므로 몇 번을 돌려도 결과가 같다.
복구 창을 넘겨 영구히 받을 수 없게 된 날짜가 생기면 `⚠ 복구 불가` 로 로그에 남는다.

하루치가 '완결' 로 인정되려면 **본 파일과 출발지 파일이 둘 다** 있고 데이터가 한 줄 이상
있어야 한다. 헤더만 있는 파일은 미완결로 보고 다시 받는다.

- `.env`의 `DATA_GO_KR_KEY` 필요. Encoding/Decoding 키 아무거나 넣어도 된다
  (수집기가 `unquote` 로 정규화한다)
- 저장 위치: `data/raw/flights_{YYYY-MM-DD}.csv` — **운항일 기준**
- 출발지연용: `data/raw/flights_origin_{YYYY-MM-DD}.csv` (GMP·CJU 출발 김해행)
- 자동 실행: 매일 04:00 (`scripts/install_scheduler.sh` 로 등록)
- 정상 수집 시 하루 약 400~430건(도착 ~200 + 출발 ~220)

### 조회 범위가 D-3 까지다

API 는 `searchday` 기준 **D-3 ~ D+6** 만 응답한다. D-4 부터는 0건이다.

- 그래서 다음날 조회로 **확정된** 실제도착시각을 받는다. 상시 폴링은 필요 없다.
- 하루이틀 빠져도 `--date` 로 복구된다. **단 나흘을 놓치면 영구 손실이다.**
- 즉 "매일 돌아가는지"보다 **"3일 안에 알아채는지"** 가 중요하다.

### 알아둘 API 제약

- `numOfRows` 최대 **100** (문서에 없음, 초과 시 `HTTP_ERROR`)
- **오류도 HTTP 200 으로 온다.** 본문에 `response` 대신 `OpenAPI_ServiceResponse` 가
  오면 실패다 — `raise_for_status()` 로는 안 잡힌다

## 수집 상태 점검

```bash
# 스케줄러 등록 확인 (두 번째 열이 마지막 종료코드 — 0 이어야 정상)
launchctl list | grep eta

# 수집기 로그
tail -20 data/raw/collect.log

# 최근 수집 현황 — 빠진 날짜가 3일 이내인지 확인 (그 이상이면 복구 불가)
ls data/raw/flights_*.csv | tail -7

# 어제치 건수 (400건 내외가 정상)
wc -l data/raw/flights_$(date -v-1d +%F).csv
```

누락일이 **3일 이내면 `--date` 로 즉시 복구한다.** 그보다 오래됐으면 복구 불가이므로
원인(맥 절전·네트워크·키 한도 초과)을 확인하고 재발을 막는 것으로 넘어간다.
