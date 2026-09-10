# notebooks/ — EDA · 오차 분석

루트 `CLAUDE.md` 의 지침을 따르되, 이 폴더에서는 아래를 추가로 지킨다.

## 이 폴더의 노트북은 보고서 자료다

최종 산출물(12월 보고서)에 그대로 들어간다. 그래서:

- **출력을 포함한 채 커밋한다.** 지우면 GitHub 에서 빈 셀만 보인다. 기존 노트북도 그렇게 되어 있다.
- 저장소 크기는 걱정하지 않아도 된다(전체 1MB 수준). nbstripout 같은 도구를 넣지 않는다.
- **재실행할 때마다 커밋하지 않는다.** 그림이 전부 새 바이너리가 되어 diff 가 무의미해진다.
  데이터 마일스톤(월 단위 축적, 보고서 직전)에서만 커밋하고, 메시지에 표본 크기를 적는다.

## 해석을 먼저 쓰고 실행하지 말 것

markdown 해석을 미리 써 두고 나중에 실행하면 **실제 출력과 어긋난다.**
실제로 2026-09-10 작업에서 세 군데가 틀렸고, 그중 하나는 결론이 반대로 갈 뻔했다
("큰 지연일수록 세 모델 모두 오차가 커진다" → 이륙후 모델만은 예외였다).

**반드시 실행한 뒤 출력과 대조하고 해석을 고친다.**

```bash
cd notebooks && ../venv/bin/jupyter nbconvert --to notebook --execute --inplace 파일.ipynb
```

## 학습 조건 재현

모델을 다시 학습하는 노트북은 `src/train.py` 에서 상수와 함수를 가져와 조건을 맞춘다.
복붙하면 조용히 어긋난다.

```python
from src.train import CATEGORICAL, FEATURES_PRE, PARAMS, TARGET, split_by_time
```

`train.py` 는 지표만 돌려주고 예측값은 주지 않는다. 잔차를 보려면 노트북에서 fit/predict 를
한 번 더 한다 — **그걸 위해 `train.py` 를 고치지 않는다.**

## 한글 폰트

```python
plt.rcParams["font.family"] = "AppleGothic"
plt.rcParams["axes.unicode_minus"] = False
```

AppleGothic 에는 **유니코드 마이너스(U+2212 `−`)가 없다.** 축 라벨·제목 문자열에 직접 쓰면
"Glyph missing" 경고가 뜨고 글자가 깨진다. 문자열에는 ASCII 하이픈(`-`)을 쓴다.

## 표본이 작다는 사실을 문서에 남긴다

항공편은 2026-09-09 부터 하루씩 쌓인다. 현재 수치는 전부 잠정이므로 노트북 첫머리와
각 절에 **인용하면 안 된다는 것**을 명시한다. 각 칸의 편수(n)를 표와 그림에 함께 적는다.
