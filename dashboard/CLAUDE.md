# dashboard/ — Streamlit 대시보드

루트 `CLAUDE.md` 의 지침을 따르되, 이 폴더에서는 아래를 추가로 지킨다.

## 실행

```bash
venv/bin/streamlit run dashboard/app.py
```

셸의 `streamlit` 은 Homebrew 것이라 다른 파이썬을 물고 있다(현재 깨져 있음). **venv 것을 쓴다.**

## 캐시 — 가장 조용한 함정

`st.cache_data` 는 **인자가 같으면 파일이 바뀌어도 캐시된 값을 돌려준다.**
수집기가 매일 04:00 에 도는 프로젝트라, 대시보드를 켜 둔 채 데이터가 갱신되는 일이 흔하다.

새 로더를 추가할 때는 **반드시 `stamp()` 또는 `raw_stamp()` 을 캐시 키로 넘긴다.**

```python
@st.cache_data
def load_something(key: tuple) -> pd.DataFrame:   # key 는 캐시 무효화 전용
    return pd.read_csv(SOMETHING_PATH)

data = load_something(stamp(SOMETHING_PATH))
```

- 파일 하나면 `stamp(경로)`, 디렉터리를 훑으면 `raw_stamp()` (새 파일이 생겨도 값이 달라져야 한다).
- 경로는 모듈 상수(`METRICS_PATH` 등)로 두고 로더와 호출부가 같은 것을 보게 한다.
- 이 버그는 예외 없이 옛 데이터를 보여주므로 **증상이 조용하다.** 눈으로는 못 잡는다.

## 검증

**`curl` 로 200 이 와도 검증이 아니다.** Streamlit 은 브라우저가 WebSocket 으로 붙기 전에는
스크립트를 실행하지 않으므로, 셸만 받고 예외를 놓친다. 스크립트를 직접 돌려 확인한다.

```bash
venv/bin/python dashboard/app.py >/dev/null 2>&1; echo $?   # 0 이면 끝까지 실행됨
```

경고(`No runtime found`, `ScriptRunContext`)는 bare mode 라 정상이다.

**레이아웃은 코드로 검증되지 않는다.** 차트 폭·라벨 잘림·색 대비는 실제로 띄워서 봐야 한다.
사용자에게 확인을 요청한다.

## 차트

- 팔레트는 `SERIES` 를 고정 순서로만 쓴다. 상태색(`STATUS_*`)은 예약 슬롯이라 계열색과 섞지 않는다.
- 색만으로 뜻을 전하지 않는다. 범례 라벨과 본문 메시지를 함께 둔다.
- 모델별 막대는 `model_bar()` 를 쓴다. 작을수록 좋은 지표는 `sort="x"`, 클수록 좋으면 `"-x"`.
- 2열로 나누면 y축 라벨 기본 폭(180px)에서 모델 이름이 잘린다 → `labelLimit` 을 올린다.
- 비율을 보여줄 때는 **분모를 캡션에 밝힌다.** 표본이 작아 "100%" 가 3편 중 3편일 수 있다.
