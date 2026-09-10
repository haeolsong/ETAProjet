"""베이스라인·XGBoost 모델을 학습하고 성능을 비교한다.

세 모델을 같은 코드로 돌린다. 차이는 피처 목록뿐이다.

    베이스라인   없음(학습셋 중앙값 고정)  — 기준선
    사전 예측    기상·노선·시간대          — 메인. 출발 전에 알 수 있는 정보만
    이륙 후      위 + dep_delay            — 성능 상한선 참고

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
from xgboost import XGBRegressor

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

CATEGORICAL = ["origin", "line", "airline", "cloud_cover"]

PARAMS = dict(
    n_estimators=300,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    enable_categorical=True,
    random_state=42,
)


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
        "실제지연편수": int(actual.sum()),
        "적중률": hit / actual.sum() if actual.any() else float("nan"),
        "오경보율": 1 - hit / flagged.sum() if flagged.any() else float("nan"),
    }


def run_xgb(name: str, features: list[str], train: pd.DataFrame, test: pd.DataFrame) -> dict:
    x_train = train[features].copy()
    x_test = test[features].copy()
    for col in set(CATEGORICAL) & set(features):
        cats = pd.CategoricalDtype(x_train[col].dropna().unique())
        x_train[col] = x_train[col].astype(cats)
        x_test[col] = x_test[col].astype(cats)

    model = XGBRegressor(**PARAMS)
    model.fit(x_train, train[TARGET])
    return evaluate(name, test[TARGET], model.predict(x_test))


def main() -> None:
    parser = argparse.ArgumentParser(description="ETA 예측 모델 학습·평가")
    parser.add_argument("--test-frac", type=float, default=0.2, help="테스트셋 비율 (기본 0.2)")
    parser.add_argument(
        "--dep-delay-only",
        action="store_true",
        help="출발지연이 있는 행만 남긴다. 세 모델을 같은 표본에서 비교할 때 쓴다.",
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

    train, test = split_by_time(df, args.test_frac)
    print(f"학습 {len(train):,}행 (~{train['sched_time'].max():%Y-%m-%d %H:%M})")
    print(f"테스트 {len(test):,}행 ({test['sched_time'].min():%Y-%m-%d %H:%M}~)\n")

    # 1. 베이스라인 — 학습셋 중앙값을 항상 예측한다.
    median = train[TARGET].median()
    results = [evaluate(f"베이스라인(중앙값 {median:+.0f}분)", test[TARGET], [median] * len(test))]

    # 2. 사전 예측 — 메인 모델.
    results.append(run_xgb("XGBoost 사전예측", FEATURES_PRE, train, test))

    # 3. 이륙 후 — 출발지연을 아는 상태. 현재 수집 범위로는 만들 수 없다.
    if args.dep_delay_only:
        results.append(run_xgb("XGBoost 이륙후", [*FEATURES_PRE, "dep_delay"], train, test))
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
    out = DATA_PROCESSED / "metrics.csv"
    if out.exists():
        table = pd.concat([pd.read_csv(out), table], ignore_index=True)
    table.to_csv(out, index=False)
    print(f"→ {out.name} 에 누적 기록")


if __name__ == "__main__":
    main()
