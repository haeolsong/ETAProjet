# ✈️ 김해공항 항공편 ETA 정밀 예측 모델

> 날씨 데이터를 활용한 김해공항(PUS) 항공편 도착예정시간(ETA) 정밀 예측 모델 개발
> 동아대학교 도전학기제 2026학년도 2학기

---

## 프로젝트 소개

공항 전광판·항공사 앱의 ETA는 기상 악화 상황에서도 사전 지연 예측을 제공하지 못한다.
본 프로젝트는 **기상 데이터(METAR)와 항공편 이력을 결합한 XGBoost 회귀 모델**로 지연시간을 예측하고, Streamlit 대시보드로 시각화한다.

**목표 성능:** 테스트 데이터 기준 MAE ≤ 15분 (단, 베이스라인 대비 유의미한 개선이 전제)

---

## 팀

| 이름 | 학번 | 역할 |
|------|------|------|
| 송하얼 | 2337310 | PM · 데이터 수집/전처리 · XGBoost 모델링 |
| 박성준 | 2118512 | 백엔드 · Streamlit 대시보드 · 기상 API 연동 |

---

## 기술 스택

- **모델:** XGBoost (회귀)
- **대시보드:** Streamlit
- **데이터 처리:** pandas, numpy
- **시각화:** matplotlib, seaborn
- **환경:** Python 3.11, venv

---

## 폴더 구조

```
ETA/
├── config.py         # 경로 상수 · 출력 설정
├── data/
│   ├── raw/          # API 원본 데이터 (git 제외)
│   └── processed/    # 전처리 완료 데이터
├── notebooks/        # EDA · 실험용 주피터 노트북
├── src/
│   ├── collect_metar.py    # METAR 수집 (Iowa State 아카이브)
│   ├── collect_flights.py  # 항공편 수집 (공공데이터포털)
│   ├── preprocess.py       # METAR 정리 · 항공편 정제 · 병합
│   └── train.py            # 베이스라인 + XGBoost 학습/평가
├── dashboard/        # Streamlit 앱
├── scripts/          # 스케줄러 등록 스크립트
├── .claude/          # 프로젝트 스킬 · 훅
├── .env              # API 키 (git 제외)
└── requirements.txt
```

---

## 데이터 소스

### 기상 (확보 완료)

**Iowa State Mesonet ASOS 아카이브** — RKPK(김해) METAR
- `https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py`
- **API 키 불필요**, 1954-07-19 ~ 현재
- 시간당 1건 / 기온 · 이슬점 · 풍향 · 풍속 · 돌풍 · 시정 · 운량 · 운고 · 기상현상코드
- ⚠️ 강수량(`p01i`)은 RKPK 가 보고하지 않아 **항상 0** 이다. 비의 유무는 기상현상코드
  (`wx_ra`)로만 알 수 있고 **강도는 알 수 없다.** → `notebooks/01_metar_eda.ipynb`

> 기상청 API허브(apihub.kma.go.kr)도 METAR를 제공하나 키 발급이 필요하고 과거 조회 범위가
> 제한적이어서, 동일 원천(ICAO METAR 전문)을 무료·장기간 제공하는 위 아카이브를 채택했다.

### 항공편 (확보 완료)

**공공데이터포털** — 한국공항공사_실시간 항공기 운항정보 조회_GW
- 도착: `https://apis.data.go.kr/B551178/flight-status/arrival`
- 출발: `https://apis.data.go.kr/B551178/flight-status/depart`
- 인증키 필요 (`.env`의 `DATA_GO_KR_KEY`)

**조회 범위는 D-3 ~ D+6.** 실시간 전용이 아니다. 다음날 한 번만 조회하면 확정된
실제도착시각을 받을 수 있고, 수집에 실패해도 사흘 안에 복구된다.
그래서 상시 폴링이 아니라 **매일 04:00 에 어제치 하루분을 조회**하는 방식을 쓴다.
(D-4 부터는 응답이 0건이므로, 나흘을 놓치면 그 날짜는 영구히 복구 불가다.)

주요 응답 필드:

| 필드 | 예시 | 용도 |
|------|------|------|
| `scheduledatetime` | `202609090605` | 계획시각 |
| `estimateddatetime` | `202609090623` | **실제/변경 시각** |
| `rmkKor` | 도착 / 출발 / 지연 / 사전결항 | 상태 |
| `depAirportCode` | `CXR` | 노선 |
| `line` | 국내 / 국제 | 편 구분 |
| `codeshare`·`masterflightid` | `Y` / `BX8813` | 코드쉐어 판별 |

> API 제약: `numOfRows` 최대 100(문서에 없음, 초과 시 `HTTP_ERROR`).
> 오류도 HTTP 200 으로 내려오므로 본문의 `OpenAPI_ServiceResponse` 유무로 판별해야 한다.

**전처리에서 반드시 처리할 것** (2026-09-09 실측 기준):

1. **코드쉐어 중복** — 도착 196편 중 89편이 코드쉐어이고 `fid`가 52건 겹친다.
   동일 항공기가 여러 편명으로 중복 계상된다. 단, `masterflightid`는 **코드쉐어 행에만**
   채워지므로(단독편 107건은 전부 결측) `flightid == masterflightid` 만으로 거르면
   정상 항공편이 모두 날아간다. 조건은 **결측이거나 주편명인 행**이다.
   정제 후에도 동일 `fid`가 그대로 두 번 내려오는 경우가 있어 `fid` 중복 제거가 더 필요하다.
2. **미확정편 제외** — `rmkKor == '도착'` 인 행만 쓴다. `사전결항`은
   `estimateddatetime`이 계획시각과 같아 **지연 0분으로 보이고**, 아직 도착하지 않은 편의
   시각은 실적이 아니라 예정값이다(당일 조회분에서 다수 발생).
3. **필드명 불일치** — 도착은 `arrAirportCode`, 출발은 `arrvAirportCode`다.

**병합 기준:** 시간 단위 JOIN (항공편 계획시각의 시(hour) ↔ METAR 관측시각)

**타겟 변수:** `delay_minutes` = 도착시각 − 계획도착시각 (분)

---

## 설치 및 실행

```bash
# 1. 가상환경 세팅
python3.11 -m venv venv
source venv/bin/activate

# 2. 의존성 설치
pip install -r requirements.txt

# 3. API 키 설정
cp .env.example .env
# .env에 공공데이터포털 키 입력

# 4. 기상 데이터 수집 (키 불필요, 즉시 실행 가능)
python src/collect_metar.py --start-year 2019

# 5. 항공편 수집 (어제치) · 자동화는 scripts/install_scheduler.sh
python src/collect_flights.py

# 6. 전처리 · 병합 (→ data/processed/dataset.parquet)
python src/preprocess.py

# 7. 학습·평가 (→ data/processed/metrics.csv)
python src/train.py

# 8. 대시보드 실행
streamlit run dashboard/app.py
```

---

## 모델 설계

세 모델을 동일한 코드로 학습해 비교한다. 차이는 피처 목록 한 줄뿐이다.

| 모델 | 피처 | 목적 |
|------|------|------|
| 베이스라인 | 없음 (학습셋 중앙값 고정 예측) | **필수 기준선.** 지연은 0 근처에 몰려 있어 이 모델도 MAE 12~15분이 흔하다 |
| XGBoost 사전 예측 | 기상 + 노선 + 시간대 | 메인 서사. 출발 전에 알 수 있는 정보만 사용 |
| XGBoost 이륙 후 | 위 + 출발지연 | 성능 상한선 참고 (국내선 한정) |

**출발지연(`dep_delay`)은 국내선에만 붙는다.** 김해 도착편의 출발지연은 출발지 공항에서
조회해야 하는데, 이 API 는 한국공항공사 소관이라 GMP·CJU 만 가능하다(전체 도착편의 약 29%).
해외 출발편은 취득 경로가 없다.

> **표본이 다르면 MAE 를 직접 빼지 말 것.** 사전 예측은 전체, 이륙 후는 29% 에서 학습된다.
> `python src/train.py --dep-delay-only` 로 같은 부분집합에서 세 모델을 비교해야
> (X−Y) 가 '출발지연 정보의 가치'를 뜻한다.

**이륙 후 모델의 이론적 하한선은 약 4~5분이다.** 실측(150편) 결과 다음 항등식이 모든 행에서
성립한다.

```
도착지연 − 출발지연 = 실제 비행시간 − 계획 비행시간
```

계획 비행시간은 노선별로 사실상 고정(60/65분)이고 실제 비행시간의 표준편차는 5.7분뿐이다.
즉 출발지연을 알면 남는 불확실성이 그 5.7분에 갇힌다. 계획에 약 25분의 여유가 들어 있어
**20분 늦게 출발해도 5분 일찍 도착하는 것이 정상**이다.

**분할:** 시계열이므로 랜덤 분할 금지 — 시간 기준 분할
**지표:** MAE(주지표) · RMSE · R²

최종 결론: *"출발 전 MAE X분 → 출발지연 정보 추가 시 Y분. 해당 정보의 가치는 (X−Y)분."*

---

## 개발 일정

| 단계 | 내용 | 완료 시점 |
|------|------|----------|
| 1 | 기상 데이터 수집·EDA · 항공편 수집 파이프라인 가동 | 9월 말 |
| 2 | 항공편 데이터 축적 · 전처리 · XGBoost 학습 | 10~11월 |
| 3 | Streamlit 대시보드 개발 | 11월 말 |
| 4 | 재검증 · 오차 분석 · 최종 보고서 | 12월 12일 |

> 항공편 이력은 2026-09-09 부터 축적한다(API 가 D-3 까지만 주므로 그 이전은 확보 불가).
> 데이터가 하루씩만 쌓이므로 1단계 범위는 기상 EDA + 수집 파이프라인 가동까지다.
