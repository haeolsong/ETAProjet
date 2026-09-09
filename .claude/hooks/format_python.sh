#!/usr/bin/env bash
# PostToolUse 훅: 편집된 파이썬 파일에 ruff 를 적용한다.
# 2인 협업에서 스타일 차이로 diff 가 지저분해지는 것을 막는다.

set -uo pipefail

command -v ruff >/dev/null 2>&1 || exit 0

FILE=$(python3 -c 'import json,sys; print((json.load(sys.stdin).get("tool_input") or {}).get("file_path",""))' 2>/dev/null)

[[ "$FILE" == *.py && -f "$FILE" ]] || exit 0

ruff check --fix --quiet "$FILE" 2>/dev/null
ruff format --quiet "$FILE" 2>/dev/null
exit 0
