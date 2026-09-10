#!/usr/bin/env python3
"""PreToolUse 훅: API 키와 원본 데이터가 저장소에 새어나가는 것을 막는다.

.gitignore는 실수로 -f 옵션을 주거나 경로를 직접 지정하면 뚫린다.
이 훅은 도구 호출 단계에서 차단한다.

차단 대상을 만나면 exit 2 + stderr 로 사유를 알린다.
"""

import json
import re
import sys

# 파일 쓰기를 막을 경로 패턴
BLOCKED_WRITE = [
    (re.compile(r"(^|/)\.env$"), ".env 는 API 키가 담기는 파일이라 직접 수정하지 않는다"),
    (re.compile(r"(^|/)\.secrets$"), "~/.secrets 는 셸 시크릿 파일이라 직접 수정하지 않는다"),
    (re.compile(r"/data/raw/"), "data/raw/ 는 수집기만 쓰는 원본 데이터 영역이다"),
]

# Bash 명령에서 막을 패턴
BLOCKED_BASH = [
    (re.compile(r"git\s+add\b[^\n;|&]*\.env"), "커밋 대상에 .env 가 포함됐다"),
    # 항공편 CSV 는 D-3 이 지나면 재취득이 불가능해 백업 목적으로 커밋한다(.gitignore 참조).
    # 그 외 data/raw 원본(METAR·로그)은 재수집 가능하므로 계속 막는다.
    (
        re.compile(r"git\s+add\b[^\n;|&]*data/raw/(?!flights_)"),
        "data/raw 의 원본 데이터가 커밋 대상에 포함됐다 (항공편 CSV 만 예외)",
    ),
    (re.compile(r">>?\s*[^\s;|&]*\.env\b"), ".env 로의 리다이렉션 쓰기"),
    (re.compile(r">>?\s*[^\s;|&]*\.secrets\b"), ".secrets 로의 리다이렉션 쓰기"),
]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0  # 훅 오류로 작업을 막지는 않는다

    tool = payload.get("tool_name", "")
    args = payload.get("tool_input", {}) or {}

    if tool in ("Write", "Edit", "NotebookEdit"):
        path = str(args.get("file_path", ""))
        for pattern, reason in BLOCKED_WRITE:
            if pattern.search(path):
                print(f"차단: {path}\n사유: {reason}", file=sys.stderr)
                return 2

    elif tool == "Bash":
        command = str(args.get("command", ""))
        for pattern, reason in BLOCKED_BASH:
            if pattern.search(command):
                print(f"차단: {reason}\n명령: {command[:200]}", file=sys.stderr)
                return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
