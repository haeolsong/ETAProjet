"""베이스라인·XGBoost 모델을 학습하고 성능을 비교한다.

모델을 같은 코드로 돌린다. 차이는 피처 목록뿐이고, 단계마다 정보가 하나씩 늘어난다.
목표는 예측 성능이다 — 쓸 수 있는 정보는 다 쓴다.

    베이스라인   없음(학습셋 중앙값 고정)  — 기준선
    사전 예측    기상·노선·시간대          — 출발 전에 알 수 있는 정보만
    회전편 후    위 + rot_delay            — 김해발 짝편(편명 −1)이 출발한 뒤. 국제선 포함
    이륙 후      위 + dep_delay            — 출발지에서 이륙한 뒤. 국내선 한정

시계열이므로 랜덤 분할을 쓰지 않는다. 계획도착시각 기준으로 뒤쪽을 테스트셋으로 뗀다.

MAE 만으로는 결론이 왜곡된다. 지연이 0 근처에 몰려 있어 상수 예측이 전체 MAE 를 낮게
받지만, 정작 예측이 필요한 15분 이상 지연 구간에서는 전혀 못 맞힌다
(notebooks/02_error_analysis.ipynb §3). 그래서 적중률·오경보율을 함께 기록한다.

    python src/train.py                    # 전체 표본 · 베이스라인 vs 사전예측
    python src/train.py --dep-delay-only   # 국내선 부분집합 · 이륙 후 모델까지 3종 비교
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBClassifier, XGBRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_PROCESSED  # noqa: E402

TARGET = "delay_minutes"

# '지연' 으로 볼 기준(분). 15분은 보고서의 목표 MAE 와 같은 눈금이다.
DELAY_THRESHOLD = 15

# 출발 전에 알 수 있는 정보만. dep_delay 는 여기 넣지 않는다.
FEATURES_PRE = [
    "temp_c",
    "dewpoint_c",
    "dewpoint_spread",
    "wind_dir",
    "wind_ms",
    "gust_ms",
    "crosswind_ms",  # 활주로에 수직인 성분. 김해는 지형 탓에 횡풍 영향이 크다
    # precip_mm 은 넣지 않는다. RKPK 는 시간당 강수량을 보고하지 않아 항상 0 이다
    # (notebooks/01_metar_eda.ipynb §3). 강수 유무는 wx_ra 로만 알 수 있다.
    "visibility_km",
    "cloud_base_ft",
    "cloud_cover",
    "wx_ts",
    "wx_fg",
    "wx_sn",
    "wx_fz",
    "wx_ra",
    "wx_br",
    "origin",
    "line",
    "airline",
    "hour",
    "dow",
    "month",
]

# 출발지 공항의 도착 1~3시간 전 기상(최악값). 김해 기상만으로는 예측이 되지 않았다.
ORIGIN_WX = ["o_vis", "o_wind", "o_gust", "o_ra", "o_ts"]
FEATURES_PRE += ORIGIN_WX

# 편명별 과거 이력(그날 이전 운항분만). 주간 4폴드에서 MAE 를 평균 0.7분 줄였다.
FLIGHT_HIST = ["fn_med", "fn_late", "fn_n"]
FEATURES_PRE += FLIGHT_HIST

# 김해에서 먼저 나간 짝편의 출발지연. 짝편이 없으면 NaN 이고 XGBoost 가 그대로 처리한다.
FEATURES_ROT = [*FEATURES_PRE, "rot_delay"]

CATEGORICAL = ["origin", "line", "airline", "cloud_cover"]

PARAMS = dict(
    n_estimators=300,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    enable_categorical=True,
    random_state=42,
    # MAE 를 직접 줄인다. 기본(제곱오차)은 평균을 좇아 드문 대형 지연에 끌려가서
    # 평범한 편까지 늦게 예측했다 — ±10분 이내 비율이 베이스라인보다 낮았던 원인이다.
    objective="reg:absoluteerror",
)

# 지연 경고는 회귀값이 아니라 분류기 확률로 낸다. 중앙값을 좇는 회귀는 15분을 거의 넘지 않는다.
# 0.3 은 주간 4폴드에서 적중 47% · 오경보 57% (0.5 면 27% · 39%). 놓침과 헛경보의 교환이다.
WARN_PROB = 0.3

# 이날부터의 수집분은 최종 검증용이다. 피처·설정을 고르는 동안(기본 실행, --weekly)에는 보지 않고,
# --final 로 한 번만 잰다. 고르면서 본 구간의 성능은 낙관적이기 때문이다.
HOLDOUT_START = pd.Timestamp("2026-11-14")


def split_by_time(df: pd.DataFrame, test_frac: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """시간 순으로 뒤쪽 test_frac 을 테스트셋으로 뗀다."""
    df = df.sort_values("sched_time")
    cut = int(len(df) * (1 - test_frac))
    return df.iloc[:cut], df.iloc[cut:]


def evaluate(name: str, y_true, y_pred) -> dict:
    # 15분 이상 지연을 '잡아냈는가' 로 다시 본다. 분모가 0 이면(테스트셋에 지연편이
    # 없거나 모델이 한 번도 경고하지 않으면) 비율이 정의되지 않으므로 NaN 으로 둔다.
    actual = pd.Series(y_true).reset_index(drop=True) >= DELAY_THRESHOLD
    flagged = pd.Series(y_pred).reset_index(drop=True) >= DELAY_THRESHOLD
    hit = (actual & flagged).sum()

    return {
        "model": name,
        "n_test": len(y_true),
        "MAE": mean_absolute_error(y_true, y_pred),
        "RMSE": mean_squared_error(y_true, y_pred) ** 0.5,
        "R2": r2_score(y_true, y_pred),
        # 사람이 읽는 '맞힌 비율'. MAE 가 같아도 이 값은 크게 다를 수 있다.
        "±10분비율": (
            abs(pd.Series(y_true).to_numpy() - pd.Series(y_pred).to_numpy()) <= 10
        ).mean(),
        "실제지연편수": int(actual.sum()),
        "적중률": hit / actual.sum() if actual.any() else float("nan"),
        "오경보율": 1 - hit / flagged.sum() if flagged.any() else float("nan"),
    }


def fit_xgb(features: list[str], train: pd.DataFrame) -> tuple[XGBRegressor, dict]:
    """학습셋으로 모델을 맞춘다. 예측 입력에도 같은 범주를 입혀야 하므로 함께 돌려준다."""
    x_train = train[features].copy()
    cats = {}
    for col in set(CATEGORICAL) & set(features):
        cats[col] = pd.CategoricalDtype(x_train[col].dropna().unique())
        x_train[col] = x_train[col].astype(cats[col])

    model = XGBRegressor(**PARAMS)
    model.fit(x_train, train[TARGET])
    return model, cats


def run_xgb(name: str, features: list[str], train: pd.DataFrame, test: pd.DataFrame) -> dict:
    model, cats = fit_xgb(features, train)
    x_test = test[features].astype(cats)
    return evaluate(name, test[TARGET], model.predict(x_test))


def fit_warning(features: list[str], train: pd.DataFrame) -> tuple[XGBClassifier, dict]:
    """15분 이상 지연 확률 분류기를 맞춘다. fit_xgb 처럼 범주도 함께 돌려준다."""
    x_train = train[features].copy()
    cats = {}
    for col in set(CATEGORICAL) & set(features):
        cats[col] = pd.CategoricalDtype(x_train[col].dropna().unique())
        x_train[col] = x_train[col].astype(cats[col])

    params = {k: v for k, v in PARAMS.items() if k != "objective"}
    clf = XGBClassifier(**params)
    clf.fit(x_train, train[TARGET] >= DELAY_THRESHOLD)
    return clf, cats


def run_warning(features: list[str], train: pd.DataFrame, test: pd.DataFrame) -> dict:
    """15분 이상 지연 확률 분류기. 적중률·오경보율만 의미가 있다."""
    clf, cats = fit_warning(features, train)
    flagged = clf.predict_proba(test[features].astype(cats))[:, 1] >= WARN_PROB
    actual = test[TARGET].to_numpy() >= DELAY_THRESHOLD
    hit = (actual & flagged).sum()
    return {
        "model": f"XGBoost 지연경고(p≥{WARN_PROB})",
        "n_test": len(test),
        "실제지연편수": int(actual.sum()),
        "적중률": hit / actual.sum() if actual.any() else float("nan"),
        "오경보율": 1 - hit / flagged.sum() if flagged.any() else float("nan"),
    }


def weekly(df: pd.DataFrame, subset: str) -> None:
    """마지막 4주를 한 주씩 테스트셋으로 쓴다. 각 주는 그 이전 자료 전부로 학습한다."""
    end = df["sched_time"].max().normalize() + pd.Timedelta(days=1)
    starts = [end - pd.Timedelta(weeks=k) for k in (4, 3, 2, 1)]
    stages = [("XGBoost 사전예측", FEATURES_PRE), ("XGBoost 회전편후", FEATURES_ROT)]
    if subset != "전체":
        stages.append(("XGBoost 이륙후", [*FEATURES_ROT, "dep_delay"]))

    rows = []
    for a in starts:
        train = df[df["sched_time"] < a]
        test = df[(df["sched_time"] >= a) & (df["sched_time"] < a + pd.Timedelta(weeks=1))]
        median = train[TARGET].median()
        rows.append(evaluate("베이스라인", test[TARGET], [median] * len(test)))
        rows += [run_xgb(name, feats, train, test) for name, feats in stages]
        rows.append(run_warning(FEATURES_ROT, train, test))
        print(f"  {a:%m-%d} 주 테스트 {len(test):,}편")

    cols = ["MAE", "RMSE", "±10분비율", "적중률", "오경보율"]
    table = pd.DataFrame(rows).groupby("model", sort=False)[cols].mean()
    print(f"\n[{subset}] 주간 4폴드 평균 ({starts[0]:%m-%d}~{end:%m-%d})")
    print(table.round(3).to_string())


def main() -> None:
    parser = argparse.ArgumentParser(description="ETA 예측 모델 학습·평가")
    parser.add_argument("--test-frac", type=float, default=0.2, help="테스트셋 비율 (기본 0.2)")
    parser.add_argument(
        "--dep-delay-only",
        action="store_true",
        help="출발지연이 있는 행만 남긴다. 세 모델을 같은 표본에서 비교할 때 쓴다.",
    )
    parser.add_argument(
        "--weekly",
        action="store_true",
        help="마지막 4주를 한 주씩 테스트셋으로 돌려 평균을 낸다. 테스트 구간 하나에 맞춘 착시를 막는다.",
    )
    parser.add_argument(
        "--final",
        action="store_true",
        help=f"최종 검증: {HOLDOUT_START:%m-%d} 전 전부로 학습하고 그 뒤 수집분으로 평가한다. 보고서용, 한 번만.",
    )
    args = parser.parse_args()

    path = DATA_PROCESSED / "dataset.parquet"
    if not path.exists():
        sys.exit(f"{path} 가 없다. 먼저 실행: python src/preprocess.py")

    df = pd.read_parquet(path)

    # 사전 예측은 전체 표본, 이륙 후는 출발지연이 있는 행에서만 학습된다.
    # 표본이 다르면 두 MAE 의 차이가 '출발지연 정보의 가치'를 뜻하지 못하므로,
    # 비교할 때는 같은 부분집합으로 좁힌다.
    subset = "전체"
    if args.dep_delay_only:
        df = df[df["dep_delay"].notna()]
        subset = "국내선(출발지연 보유)"
        print(f"부분집합: {subset} {len(df):,}행\n")

    if args.final:
        train, test = df[df["sched_time"] < HOLDOUT_START], df[df["sched_time"] >= HOLDOUT_START]
        if test.empty:
            sys.exit(f"{HOLDOUT_START:%m-%d} 이후 수집분이 없다. 수집·전처리 후 다시 실행한다.")
        subset += " · 최종검증"
    else:
        held = (df["sched_time"] >= HOLDOUT_START).sum()
        if held:
            print(
                f"최종 검증 구간({HOLDOUT_START:%m-%d}~) {held:,}행은 제외한다. 평가는 --final 로.\n"
            )
        df = df[df["sched_time"] < HOLDOUT_START]

        if args.weekly:
            weekly(df, subset)
            return

        train, test = split_by_time(df, args.test_frac)
    print(f"학습 {len(train):,}행 (~{train['sched_time'].max():%Y-%m-%d %H:%M})")
    print(f"테스트 {len(test):,}행 ({test['sched_time'].min():%Y-%m-%d %H:%M}~)\n")

    # 1. 베이스라인 — 학습셋 중앙값을 항상 예측한다.
    median = train[TARGET].median()
    results = [evaluate(f"베이스라인(중앙값 {median:+.0f}분)", test[TARGET], [median] * len(test))]

    # 2. 사전 예측 — 메인 모델.
    results.append(run_xgb("XGBoost 사전예측", FEATURES_PRE, train, test))

    # 3. 회전편 후 — 김해발 짝편이 출발한 상태. 전체 표본에서 돌린다.
    results.append(run_xgb("XGBoost 회전편후", FEATURES_ROT, train, test))

    # 지연 경고 — 회전편후까지의 정보로 15분 이상 지연 확률을 낸다.
    results.append(run_warning(FEATURES_ROT, train, test))

    # 4. 이륙 후 — 출발지연까지 아는 상태. 국내선만 있어 같은 부분집합에서 비교한다.
    if args.dep_delay_only:
        results.append(run_xgb("XGBoost 이륙후", [*FEATURES_ROT, "dep_delay"], train, test))
    else:
        print("이륙 후 모델은 --dep-delay-only 로 같은 표본에서 비교한다.\n")

    table = pd.DataFrame(results)
    print(table.round(2).to_string(index=False))

    pre = table.loc[table.model == "XGBoost 사전예측", "MAE"].iloc[0]
    print(f"\n베이스라인 대비 MAE {table.MAE.iloc[0] - pre:+.2f}분")

    n_delayed = table["실제지연편수"].iloc[0]
    if n_delayed == 0:
        print(f"테스트셋에 {DELAY_THRESHOLD}분 이상 지연편이 없어 적중률을 낼 수 없다.")
    else:
        print(f"{DELAY_THRESHOLD}분 이상 지연 {n_delayed}편 중 잡아낸 비율:")
        for row in results:
            rate = row["적중률"]
            shown = f"{rate:.0%}" if pd.notna(rate) else "— (한 번도 경고하지 않음)"
            print(f"  {row['model']:22s} {shown}")

    table.insert(0, "run_at", datetime.now().isoformat(timespec="seconds"))
    table.insert(1, "subset", subset)
    table.insert(2, "n_train", len(train))
    # 지표를 추가하면 열 수가 달라져 header 없는 append 는 깨진다.
    # 파일이 작으므로(연말까지 수백 행) 통째로 읽어 concat 한 뒤 다시 쓴다.
    # 기존 행은 dtype=str 로 읽는다 — float 로 되읽으면 다시 쓸 때 끝자리가
    # 잘려 과거 기록이 매 실행마다 바뀐다.
    out = DATA_PROCESSED / "metrics.csv"
    if out.exists():
        table = pd.concat([pd.read_csv(out, dtype=str), table], ignore_index=True)
    table.to_csv(out, index=False)
    print(f"→ {out.name} 에 누적 기록")


if __name__ == "__main__":
    main()
