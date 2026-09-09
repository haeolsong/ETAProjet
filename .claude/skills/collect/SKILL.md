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
python src/collect_flights.py            # 1회 수집
python src/collect_flights.py --probe    # 응답 필드 확인용 (키 발급 직후 1번)
```

- `.env`의 `DATA_GO_KR_KEY` 필요 (`.env.example` 참고)
- 저장 위치: `data/raw/flights_{YYYY-MM-DD}.csv` — 같은 날 파일에 append
- **하루 여러 번 찍어야** 계획시각 → 최종시각 변화를 포착할 수 있다

### 왜 매일 쌓아야 하나

국내 항공편의 편별 과거 이력은 공개 API로 대량 조회가 **불가능하다**.
한국공항공사 API는 실시간 전용이고, 에어포탈 통계는 집계값뿐이다.
따라서 이력은 직접 축적하는 수밖에 없다. **수집기가 멈추면 그 기간 데이터는 영구히 없다.**

## 수집 상태 점검

```bash
# 스케줄러 등록 확인
launchctl list | grep eta-collect

# 최근 7일 수집 현황 (빠진 날짜 확인)
ls data/raw/flights_*.csv | tail -7

# 오늘 수집된 건수
wc -l data/raw/flights_$(date +%F).csv
```

누락일을 발견하면 그 날짜는 복구할 수 없다. 원인(맥 절전·네트워크·키 한도 초과)을
확인하고 재발을 막는 것이 우선이다.
