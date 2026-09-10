# data/ — 되돌릴 수 없는 데이터

루트 `CLAUDE.md` 의 지침을 따르되, 이 폴더에서는 아래를 추가로 지킨다.

## 가장 중요한 것

**`data/raw/flights_*.csv` 는 다시 구할 수 없다.**
공공데이터포털 API 는 D-3 까지만 응답한다. 나흘을 놓치면 그 날짜는 영구히 사라진다.
그래서 이 파일들만 예외적으로 git 에 커밋한다(`.gitignore` 에 `!data/raw/flights_*.csv`).

**절대 하지 말 것**
- `data/raw/flights_*.csv` 삭제·덮어쓰기
- `data/raw/` 를 통째로 비우는 정리 작업
- 커밋되지 않은 수집분이 있는 상태에서 `git clean`

이 폴더의 파일을 지우거나 덮어쓰기 전에는 **git 에 추적 중인지 먼저 확인한다.**

```bash
git ls-files --error-unmatch data/raw/파일명 && echo "복구 가능"
```

추적되지 않는 파일(METAR 원본 등)을 덮어쓸 때는 스크래치패드에 백업부터 한다.

## 재취득 가능 여부

| 경로 | 재취득 | git |
|------|--------|-----|
| `raw/flights_*.csv` | **불가 (D-3 경과)** | 추적 |
| `raw/flights_origin_*.csv` | **불가** | 추적 |
| `raw/metar_RKPK_*.csv` | 가능 (Iowa 아카이브, 언제든) | 제외 |
| `processed/*.parquet` | 가능 (`src/preprocess.py`) | 제외 |
| `processed/metrics.csv` | 가능 (`src/train.py`) | 제외 |

## 알려진 정상 상태

- **METAR 결측 0.18%** — 아카이브 원본에 산발적 구멍이 있다. 몇 년에 몇 번은 하루 5~10시간이
  통째로 빈다(2026-02-08 10시간, 2026-09-07 8시간). **재수집해도 채워지지 않는다.**
  고장이 아니므로 보간하지 않는다. XGBoost 가 NaN 을 그대로 학습한다.
- **출발지연 매칭 29%** — `dep_delay` 는 국내선(GMP·CJU)에만 붙는다. 해외 출발편은 취득 경로가
  없다. 30% 내외가 정상이다.
- **`precip_mm` 항상 0** — RKPK 가 시간당 강수량을 보고하지 않는다.

## collect.log

`data/raw/collect.log` 에 수집 이력이 쌓인다(launchd 가 stdout/stderr 를 여기로 보낸다).
수집이 돌았는지 확인하는 1차 자료다.

```
2026-09-09 413건 → flights_2026-09-09.csv     ← 실제 수집
2026-09-10 점검: 복구 창(D-1~D-3) 이상 없음    ← 이미 다 있어 건너뜀
```
