#!/usr/bin/env bash
# 사서 에이전트 서버 실행 스크립트.
#
# 외부(오케스트레이터/다른 기기)에서 접속할 수 있도록 --host 0.0.0.0에 바인딩합니다.
# 127.0.0.1(기본값)은 로컬에서만 접근되므로, 팀원 기기에서 호출하려면 이 스크립트를 쓰세요.
#
# 사용법:
#   # fake 모드 (AWS 불필요)
#   bash scripts/run_server.sh
#
#   # Bedrock 모드 (MFA 세션 필요)
#   USE_BEDROCK=true AWS_PROFILE=mfa bash scripts/run_server.sh
#
# 환경변수:
#   HOST   바인딩 호스트 (기본 0.0.0.0 — 모든 인터페이스)
#   PORT   포트 (기본 8000)
#   RELOAD 코드 변경 시 자동 재시작 (기본 1, 끄려면 RELOAD=0)

set -euo pipefail

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-1}"

RELOAD_FLAG=""
if [ "$RELOAD" = "1" ]; then
  RELOAD_FLAG="--reload"
fi

echo "[run_server] http://${HOST}:${PORT} 에서 서버를 시작합니다 (mode: ${USE_BEDROCK:+bedrock}${USE_BEDROCK:-mock})"

# shellcheck disable=SC2086
exec uv run uvicorn app.librarian.server:app --host "$HOST" --port "$PORT" $RELOAD_FLAG
