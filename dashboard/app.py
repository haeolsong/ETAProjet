"""김해공항 ETA 예측 대시보드.

수집 현황 · 지연 분석 · 기상 · 모델 성능 네 화면으로 구성한다.
모델 예측 화면은 표본이 모여 예측이 의미를 가질 때(11월) 추가한다.

    streamlit run dashboard/app.py
"""

import sys
from datetime import timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_PROCESSED, DATA_RAW, ICAO  # noqa: E402

# 검증된 기본 팔레트 (dataviz 지침). 범주형은 고정 순서로만 쓴다.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
# 모델명에는 중앙값이 박혀 있어(베이스라인(중앙값 -9분)) 표본마다 문자열이 달라진다.
# 색을 model 에 직접 걸면 domain 이 차트마다 새로 잡혀 같은 모델이 다른 색을 받는다
# (모델 비교에서 초록이던 베이스라인이 성능 추이에서 주황이었다). 계열명에 고정한다.
# 메인 서사인 사전예측이 첫 색(파랑)을 갖는다. 베이스라인은 기준선일 뿐이다.
SERIES_ORDER = ["사전예측", "베이스라인", "이륙후"]


def series_of(model: str) -> str:
    """모델명에서 색을 고정할 계열명을 뽑는다."""
    for key in SERIES_ORDER:
        if key in model:
            return key
    return model
DIVERGING = ["#2a78d6", "#f0efec", "#e34948"]  # 조기 ← 정시 → 지연
# 상태색은 예약된 슬롯이라 계열색과 섞지 않는다. 색만으로 뜻을 전하지 않도록
# 범례 라벨과 본문 메시지를 항상 함께 둔다.
STATUS_GOOD, STATUS_WARNING, STATUS_CRITICAL = "#0ca30c", "#fab219", "#d03b3b"
# 축·격자. 밝은 회색을 그대로 쓰면 어두운 테마에서 모눈종이처럼 도드라진다.
# 중간 회색을 낮은 불투명도로 깔아 양쪽 테마에서 모두 뒤로 물린다.
AXIS = "#8a8a87"
# 값 라벨용 중간 회색. 대시보드는 라이트·다크 양쪽에서 열리는데 Streamlit 1.41 은
# 브라우저 테마를 서버에서 알 수 없어(st.context.theme 는 1.44+) 한쪽에 맞추면
# 다른 쪽이 묻힌다(#52514e 는 다크에서 2.38:1). 양쪽 모두 4:1 을 넘는 값을 쓴다.
LABEL = "#7b7b79"

MAX_BACKFILL_DAYS = 3

METAR_PATH = DATA_PROCESSED / f"metar_{ICAO}.parquet"
DATASET_PATH = DATA_PROCESSED / "dataset.parquet"
METRICS_PATH = DATA_PROCESSED / "metrics.csv"
FLIGHTS_GLOB = "flights_????-??-??.csv"

st.set_page_config(page_title="김해공항 ETA 예측", page_icon="✈️", layout="wide")


def stamp(*paths: Path) -> tuple:
    """파일 수정시각 묶음. 로더에 캐시 키로 넘긴다.

    st.cache_data 는 인자가 같으면 파일이 바뀌어도 캐시된 값을 돌려준다.
    수집기가 매일 04:00 에 돌므로 대시보드를 켜 둔 채 데이터가 갱신되는 일이
    흔하다. 수정시각을 키로 넘겨야 그때 다시 읽는다.
    """
    return tuple(p.stat().st_mtime if p.exists() else None for p in paths)


def raw_stamp() -> tuple:
    """수집 파일 목록과 수정시각. 새 날짜가 들어오면 값이 달라진다."""
    return tuple((f.name, f.stat().st_mtime) for f in sorted(DATA_RAW.glob(FLIGHTS_GLOB)))


# 아래 로더의 key 인자는 캐시 무효화 전용이다. 함수 안에서 쓰지 않는다.
@st.cache_data
def load_metar(key: tuple) -> pd.DataFrame | None:
    return pd.read_parquet(METAR_PATH) if METAR_PATH.exists() else None


@st.cache_data
def load_dataset(key: tuple) -> pd.DataFrame | None:
    return pd.read_parquet(DATASET_PATH) if DATASET_PATH.exists() else None


@st.cache_data
def load_metrics(key: tuple) -> pd.DataFrame | None:
    return pd.read_csv(METRICS_PATH) if METRICS_PATH.exists() else None


@st.cache_data
def load_collection_days(key: tuple) -> pd.DataFrame:
    """운항일별 수집 건수. 파일이 없는 날은 0 으로 채워 구멍을 드러낸다."""
    counts = {}
    for f in sorted(DATA_RAW.glob(FLIGHTS_GLOB)):
        day = pd.to_datetime(f.stem.removeprefix("flights_")).date()
        counts[day] = sum(1 for _ in f.open(encoding="utf-8")) - 1

    if not counts:
        return pd.DataFrame(columns=["date", "n", "status"])

    span = pd.date_range(min(counts), max(counts), freq="D").date
    today = pd.Timestamp.now().date()
    rows = [
        {
            "date": d,
            "n": counts.get(d, 0),
            "status": (
                "수집됨"
                if counts.get(d, 0) > 0
                else ("복구 가능" if (today - d).days <= MAX_BACKFILL_DAYS else "복구 불가")
            ),
        }
        for d in span
    ]
    return pd.DataFrame(rows)


def base(chart: alt.Chart) -> alt.Chart:
    """눈금을 뒤로 물리고 테두리를 없앤다."""
    return chart.configure_axis(
        grid=True,
        gridColor=AXIS,
        gridOpacity=0.22,
        gridWidth=1,
        domainColor=AXIS,
        domainOpacity=0.45,
        tickColor=AXIS,
        tickOpacity=0.45,
    ).configure_view(strokeWidth=0)


def model_bar(data: pd.DataFrame, field: str, title: str, fmt: str, sort: str) -> alt.Chart:
    """모델별 가로 막대. 값이 작을수록 좋은 지표는 sort='x', 클수록 좋으면 '-x'."""
    # 값 라벨을 막대 오른쪽 바깥에 찍으므로, 축 상한이 최댓값에 딱 맞으면 라벨이
    # 차트 밖으로 밀려 잘린다. 여유를 15% 고정으로 뒀더니 다시 잘렸다("11.76" 이
    # "11.7" 로 보였다) - 잘림은 값의 크기가 아니라 라벨의 글자 수에서 온다.
    # 최댓값 라벨이 4자(9.71)일 때 우연히 맞았을 뿐이다. 글자당 6% 로 잡는다.
    hi = data[field].max()
    x_scale = alt.Undefined
    if pd.notna(hi) and hi > 0:
        x_scale = alt.Scale(domain=[0, hi * (1 + 0.06 * len(format(hi, fmt)))])

    data = data.assign(계열=data.model.map(series_of))
    chart = (
        alt.Chart(data)
        .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
        .encode(
            # 막대마다 값을 직접 찍으므로 세로 격자선은 정보를 더하지 않는다. 오히려 값
            # 라벨과 겹쳐("75%" 의 % 를 80% 선이 관통) 지저분해지므로 이 차트만 끈다.
            x=alt.X(
                f"{field}:Q",
                title=title,
                axis=alt.Axis(format=fmt, grid=False),
                scale=x_scale,
            ),
            # 2열로 좁아지면 기본 폭(180px)에서 "베이스라인(중앙값 -6분)" 이 잘린다.
            y=alt.Y("model:N", sort=sort, title=None, axis=alt.Axis(labelLimit=250)),
            color=alt.Color(
                "계열:N", scale=alt.Scale(domain=SERIES_ORDER, range=SERIES), legend=None
            ),
            tooltip=[
                "model:N",
                alt.Tooltip("MAE:Q", format=".2f"),
                alt.Tooltip("RMSE:Q", format=".2f"),
                alt.Tooltip("R2:Q", format=".3f"),
                alt.Tooltip("적중률:Q", format=".0%"),
                alt.Tooltip("오경보율:Q", format=".0%"),
            ],
        )
    )
    # aqua 슬롯이 밝은 배경에서 대비 3:1 미만이라 값을 직접 표기한다.
    # color 를 mark 속성으로만 주면 막대에서 상속된 color 인코딩이 덮어써서 라벨이
    # 계열색으로 찍힌다(초록은 밝은 배경에서 2.82:1). 인코딩으로 덮어야 한다.
    labels = chart.mark_text(align="left", dx=6).encode(
        text=alt.Text(f"{field}:Q", format=fmt), color=alt.value(LABEL)
    )
    return base(alt.layer(chart, labels).properties(height=170))


st.title("✈️ 김해공항 항공편 ETA 예측")
st.caption("동아대학교 도전학기제 · 송하얼 · 박성준")

metar = load_metar(stamp(METAR_PATH))
dataset = load_dataset(stamp(DATASET_PATH))
metrics = load_metrics(stamp(METRICS_PATH))

if metar is None:
    st.warning(
        "전처리된 자료가 없습니다.\n\n"
        "```\npython src/collect_metar.py --start-year 2019\n"
        "python src/preprocess.py\n```"
    )
    st.stop()

tab_collect, tab_delay, tab_wx, tab_model = st.tabs(
    ["📥 수집 현황", "⏱ 지연 분석", "🌦 기상", "📊 모델 성능"]
)

# ---------------------------------------------------------------- 수집 현황
with tab_collect:
    st.subheader("항공편 수집")
    days = load_collection_days(raw_stamp())

    if days.empty:
        st.info("아직 수집된 항공편이 없습니다. `python src/collect_flights.py`")
    else:
        lost = int((days.status == "복구 불가").sum())
        recoverable = int((days.status == "복구 가능").sum())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("수집일", f"{int((days.n > 0).sum())}일")
        c2.metric("총 항공편", f"{int(days.n.sum()):,}건")
        c3.metric("최근 수집", f"{days.loc[days.n > 0, 'date'].max()}")
        c4.metric("복구 불가", f"{lost}일", delta=None if lost == 0 else "영구 손실")

        if lost:
            st.error(
                f"**{lost}일이 영구 손실됐습니다.** API 는 D-{MAX_BACKFILL_DAYS} 까지만 "
                "조회를 허용해 되돌릴 수 없습니다."
            )
        if recoverable:
            st.warning(
                f"**{recoverable}일이 아직 복구 가능합니다.** 지금 "
                "`python src/collect_flights.py` 를 실행하세요."
            )
        if not lost and not recoverable:
            st.success("구멍 없이 연속 수집되고 있습니다.")

        st.altair_chart(
            base(
                alt.Chart(days)
                .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=18)
                .encode(
                    x=alt.X("date:T", title=None),
                    y=alt.Y("n:Q", title="항공편 수"),
                    color=alt.Color(
                        "status:N",
                        title="상태",
                        scale=alt.Scale(
                            domain=["수집됨", "복구 가능", "복구 불가"],
                            range=[STATUS_GOOD, STATUS_WARNING, STATUS_CRITICAL],
                        ),
                    ),
                    tooltip=["date:T", "n:Q", "status:N"],
                )
                .properties(height=220)
            ),
            use_container_width=True,
        )

    st.subheader("기상 관측")
    c1, c2, c3 = st.columns(3)
    c1.metric("관측 건수", f"{len(metar):,}")
    c2.metric("시작", f"{metar['obs_time'].min():%Y-%m-%d}")
    c3.metric("최근", f"{metar['obs_time'].max():%Y-%m-%d}")

    stale = pd.Timestamp.now() - metar["obs_time"].max()
    if stale > timedelta(days=2):
        st.warning(
            f"기상 자료가 {stale.days}일 뒤처져 있습니다. 스케줄러는 항공편만 받습니다.\n\n"
            "```\npython src/collect_metar.py --start-year 2026\n```"
        )

# ---------------------------------------------------------------- 지연 분석
with tab_delay:
    if dataset is None:
        st.info("`python src/preprocess.py` 를 먼저 실행하세요.")
    else:
        st.subheader("도착지연 분포")
        st.caption(
            f"{len(dataset):,}편 · {dataset.sched_time.min():%Y-%m-%d} ~ "
            f"{dataset.sched_time.max():%Y-%m-%d} · 음수는 조기 도착"
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("중앙값", f"{dataset.delay_minutes.median():+.0f}분")
        c2.metric("평균", f"{dataset.delay_minutes.mean():+.1f}분")
        c3.metric("15분 초과 지연", f"{(dataset.delay_minutes > 15).mean() * 100:.1f}%")
        c4.metric("최대 지연", f"{dataset.delay_minutes.max():+.0f}분")

        st.altair_chart(
            base(
                alt.Chart(dataset)
                .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                .encode(
                    x=alt.X("delay_minutes:Q", bin=alt.Bin(step=10), title="도착지연 (분)"),
                    y=alt.Y("count():Q", title="항공편 수"),
                    color=alt.Color(
                        "delay_minutes:Q",
                        bin=alt.Bin(step=10),
                        title="지연 (분)",
                        scale=alt.Scale(domain=[-60, 0, 60], range=DIVERGING, type="linear"),
                    ),
                    tooltip=[alt.Tooltip("count():Q", title="항공편")],
                )
                .properties(height=260)
            ),
            use_container_width=True,
        )

        st.subheader("구분별 지연")
        dim = st.selectbox(
            "기준",
            ["origin", "airline", "hour", "line"],
            format_func=lambda c: {
                "origin": "출발지",
                "airline": "항공사",
                "hour": "시간대",
                "line": "국내/국제",
            }[c],
        )
        agg = (
            dataset.groupby(dim)
            .agg(중앙값=("delay_minutes", "median"), 편수=("delay_minutes", "size"))
            .reset_index()
        )
        agg = agg[agg.편수 >= 3].sort_values("중앙값")

        st.altair_chart(
            base(
                alt.Chart(agg)
                .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                .encode(
                    x=alt.X("중앙값:Q", title="지연 중앙값 (분)"),
                    y=alt.Y(f"{dim}:N", sort="x", title=None),
                    color=alt.Color(
                        "중앙값:Q",
                        title="지연 (분)",
                        scale=alt.Scale(domain=[-30, 0, 30], range=DIVERGING, type="linear"),
                    ),
                    tooltip=[f"{dim}:N", "중앙값:Q", "편수:Q"],
                )
                .properties(height=max(240, len(agg) * 22))
            ),
            use_container_width=True,
        )
        st.caption("표본 3편 미만은 제외했습니다.")

        if dataset.dep_delay.notna().any():
            st.subheader("출발지연 → 도착지연")
            sub = dataset[dataset.dep_delay.notna()]
            st.caption(
                f"국내선 {len(sub):,}편 (전체의 {len(sub) / len(dataset) * 100:.0f}%). "
                "계획에 약 25분의 여유가 있어 늦게 떠도 정시 도착하는 편이 많습니다."
            )
            st.altair_chart(
                base(
                    alt.Chart(sub)
                    .mark_circle(size=60, opacity=0.7, stroke="#fcfcfb", strokeWidth=2)
                    .encode(
                        x=alt.X("dep_delay:Q", title="출발지연 (분)"),
                        y=alt.Y("delay_minutes:Q", title="도착지연 (분)"),
                        color=alt.value(SERIES[0]),
                        tooltip=["flight_no:N", "origin:N", "dep_delay:Q", "delay_minutes:Q"],
                    )
                    .properties(height=300)
                ),
                use_container_width=True,
            )

# ---------------------------------------------------------------- 기상
with tab_wx:
    st.subheader("기상 추이")
    # precip_mm 은 넣지 않는다. RKPK 는 시간당 강수량을 보고하지 않아 항상 0 이다.
    label = {
        "visibility_km": "시정 (km)",
        "wind_ms": "풍속 (m/s)",
        "gust_ms": "돌풍 (m/s)",
        "temp_c": "기온 (°C)",
        "dewpoint_spread": "기온-이슬점 차 (°C)",
    }
    metric = st.selectbox("항목", list(label), format_func=label.get)
    recent = metar.tail(2000)

    st.altair_chart(
        base(
            alt.Chart(recent)
            .mark_line(strokeWidth=2, color=SERIES[0])
            .encode(
                x=alt.X("obs_time:T", title=None),
                y=alt.Y(f"{metric}:Q", title=label[metric]),
                tooltip=["obs_time:T", f"{metric}:Q"],
            )
            .properties(height=260)
        ),
        use_container_width=True,
    )

    st.subheader("악기상 발생률")
    st.caption(
        "과거 7년의 같은 달력 창(9/16~12/12, 88일)으로 본 결과 **눈·착빙은 확보할 수 "
        "없습니다** — 눈은 7년을 통틀어 1시간뿐입니다. 반면 비(18.3일)·안개와 박무(11.1일)·"
        "저시정(시정 8km 미만 20.7일)은 충분히 나옵니다. 다만 80%가 9월 하순~11월에 "
        "몰려 있어 12월 초는 거의 비어 있습니다. → `notebooks/03_climate_feasibility.ipynb`"
    )
    names = {
        "wx_ts": "뇌전",
        "wx_fg": "안개",
        "wx_sn": "눈",
        "wx_fz": "착빙",
        "wx_ra": "비",
        "wx_br": "박무",
    }
    monthly = (
        metar.groupby("month")[list(names)]
        .mean()
        .mul(100)
        .rename(columns=names)
        .reset_index()
        .melt("month", var_name="현상", value_name="발생률")
    )
    st.altair_chart(
        base(
            alt.Chart(monthly[monthly.현상.isin(["비", "박무"])])
            .mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=40))
            .encode(
                x=alt.X("month:O", title="월"),
                y=alt.Y("발생률:Q", title="발생률 (%)"),
                color=alt.Color("현상:N", scale=alt.Scale(range=SERIES[:2]), title=None),
                tooltip=["month:O", "현상:N", alt.Tooltip("발생률:Q", format=".2f")],
            )
            .properties(height=240)
        ),
        use_container_width=True,
    )
    st.dataframe(
        metar[list(names)].mean().mul(100).rename(names).round(2).rename("8년 발생률 (%)"),
        use_container_width=True,
    )

# ---------------------------------------------------------------- 모델 성능
with tab_model:
    if metrics is None or metrics.empty:
        st.info("`python src/train.py` 를 먼저 실행하세요.")
    else:
        st.subheader("모델 비교")
        subset = st.selectbox("표본", sorted(metrics.subset.unique()))
        latest = metrics[metrics.subset == subset]
        latest = latest[latest.run_at == latest.run_at.max()]

        st.caption(
            f"학습 {int(latest.n_train.iloc[0]):,}행 · 테스트 {int(latest.n_test.iloc[0]):,}행 · "
            f"{latest.run_at.iloc[0]}"
        )

        left, right = st.columns(2)
        with left:
            st.altair_chart(
                model_bar(latest, "MAE", "MAE (분) — 낮을수록 좋음", ".2f", "x"),
                use_container_width=True,
            )
        with right:
            if latest["적중률"].notna().any():
                n_delayed = int(latest["실제지연편수"].iloc[0])
                st.altair_chart(
                    model_bar(
                        latest, "적중률", "15분 이상 지연 적중률 — 높을수록 좋음", ".0%", "-x"
                    ),
                    use_container_width=True,
                )
                st.caption(f"테스트셋의 15분 이상 지연 {n_delayed}편 중 경고한 비율입니다.")
            else:
                st.info("이 기록에는 적중률이 없습니다. `python src/train.py` 를 다시 실행하세요.")

        # 표본에 따라 순위가 뒤집힌다. 전체에서는 사전예측이 MAE 도 이기지만 국내선
        # 부분집합에서는 아직 베이스라인이 낮다. 문구를 고정하면 화면과 어긋나므로
        # 선택된 표본의 실제 수치를 보고 고른다.
        # 비교 대상은 메인인 사전예측이다. 이륙후는 출발지연을 쓰는 상한선 참고용이라
        # 최저 MAE 로 고르면 국내선 표본에서 이륙후(4.84)가 뽑혀 문구가 뒤집힌다.
        baseline = latest[latest.model.str.startswith("베이스라인")]
        pre = latest[latest.model.str.contains("사전예측")]
        base_mae = baseline.MAE.iloc[0] if len(baseline) else float("nan")
        pre_mae = pre.MAE.iloc[0] if len(pre) else float("nan")

        if not (pre_mae < base_mae):
            st.info(
                f"**이 표본에서는 MAE 순위를 믿지 마세요.** 지연이 0 근처에 몰려 있어 "
                f"상수 예측인 베이스라인이 MAE {base_mae:.2f}분으로 가장 낮지만, 정작 예측이 "
                f"필요한 15분 이상 지연은 구조적으로 한 건도 잡지 못해 적중률이 0% 입니다. "
                f"적중률만 봐도 안 됩니다 — 막대에 커서를 올리면 오경보율이 같이 나옵니다."
            )
        else:
            st.info(
                f"**사전예측이 MAE {pre_mae:.2f}분으로 베이스라인"
                f"({base_mae:.2f}분)을 앞섭니다.** 베이스라인은 상수 예측이라 MAE 를 낮게 "
                f"받으면서도 15분 이상 지연은 한 건도 잡지 못해 적중률이 0% 입니다 — "
                f"두 지표를 함께 봐야 하는 이유입니다. "
                f"적중률만 봐도 안 됩니다 — 막대에 커서를 올리면 오경보율이 같이 나옵니다."
            )

        st.warning(
            "표본이 다르면 MAE 를 직접 빼지 마세요. 사전 예측은 전체, 이륙 후는 국내선에서만 "
            "학습됩니다. `python src/train.py --dep-delay-only` 로 같은 표본에서 비교하세요."
        )

        st.subheader("성능 추이")
        st.caption("표본이 늘면서 베이스라인 대비 개선폭이 커지는지가 핵심입니다.")
        st.altair_chart(
            base(
                alt.Chart(
                    metrics[metrics.subset == subset].assign(
                        계열=lambda f: f.model.map(series_of)
                    )
                )
                .mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=50))
                .encode(
                    x=alt.X("n_train:Q", title="학습 표본 수"),
                    y=alt.Y("MAE:Q", title="MAE (분)"),
                    color=alt.Color(
                        "계열:N",
                        scale=alt.Scale(domain=SERIES_ORDER, range=SERIES),
                        title=None,
                    ),
                    tooltip=["model:N", "n_train:Q", alt.Tooltip("MAE:Q", format=".2f")],
                )
                .properties(height=260)
            ),
            use_container_width=True,
        )

        with st.expander("전체 기록"):
            st.dataframe(metrics.sort_values("run_at", ascending=False), use_container_width=True)
