#!/usr/bin/env bash
# 항공편 수집기를 launchd 에 10분 주기로 등록한다. 재실행해도 안전하다.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.eta.collect"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"

sed "s|__ROOT__|$ROOT|g" "$ROOT/scripts/$LABEL.plist" > "$TARGET"

# 이미 등록돼 있으면 먼저 내린다 (없으면 실패해도 무시)
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"

echo "등록 완료: $LABEL (매일 04:00)"
echo "  상태 확인: launchctl list | grep eta"
echo "  로그:      tail -f $ROOT/data/raw/collect.log"
echo "  해제:      launchctl bootout gui/\$(id -u)/$LABEL"
