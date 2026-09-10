# scripts/ — 스케줄러 등록

루트 `CLAUDE.md` 의 지침을 따르되, 이 폴더에서는 아래를 추가로 지킨다.

## 구조

`com.eta.collect.plist` 는 템플릿이다. `__ROOT__` 를 실제 경로로 치환해
`~/Library/LaunchAgents/` 에 설치한다. 설치·재설치는 이것 하나면 된다(재실행해도 안전).

```bash
bash scripts/install_scheduler.sh    # 매일 04:00 등록 + 원복용으로도 쓴다
```

**저장소의 plist 를 직접 고치지 말고**, 임시 실험은 설치본
(`~/Library/LaunchAgents/com.eta.collect.plist`)에서 하고 위 스크립트로 되돌린다.

## launchd 실행 환경은 셸과 다르다

`PATH` 가 `/usr/bin:/bin:/usr/sbin:/sbin` 뿐이고 셸 프로필을 읽지 않는다.
그래서 다음 두 가지가 필수다 — 건드리지 말 것.

- `ProgramArguments` 의 파이썬을 **venv 절대경로**로 지정
- `WorkingDirectory` 를 루트로 지정 (`load_dotenv()` 가 `.env` 를 찾으려면 필요)

## 자동 실행 검증 방법

**`launchctl kickstart` 는 강제 실행이라 `StartCalendarInterval` 경로를 검증하지 못한다.**
자동 트리거를 확인하려면 설치본의 시각을 몇 분 뒤로 바꿔 등록하고 기다린다.

```bash
P=~/Library/LaunchAgents/com.eta.collect.plist
/usr/libexec/PlistBuddy -c "Set :StartCalendarInterval:Hour 16" -c "Set :StartCalendarInterval:Minute 41" "$P"
launchctl bootout gui/$(id -u)/com.eta.collect; launchctl bootstrap gui/$(id -u) "$P"
# 기다린 뒤 확인
launchctl print gui/$(id -u)/com.eta.collect | grep -E "runs|last exit"
tail data/raw/collect.log
bash scripts/install_scheduler.sh    # 반드시 04:00 으로 원복
```

`bootout`/`bootstrap` 은 `runs` 카운터를 0 으로 되돌리므로 깨끗한 검증 조건이 된다.

**exit 0 이면 `.env` 로딩까지 통과한 것이다** — `collect_flights.py` 는 키가 없으면
`sys.exit`(코드 1)로 끝나기 때문이다. 2026-09-10 에 이 방법으로 검증했다.

## 맥이 꺼져 있으면

launchd 는 놓친 `StartCalendarInterval` 을 깨어난 뒤 따라잡아 실행한다.
그래도 못 돌면 `collect_flights.py` 가 복구 창(D-1~D-3)을 스스로 점검해 채운다.
**나흘을 연속으로 놓치면 복구 불가다** — `data/CLAUDE.md` 참고.
