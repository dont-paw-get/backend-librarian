#!/bin/zsh
# 로컬에서 서버를 띄우고 /chat을 호출해 JSON 로그가 어떻게 찍히는지 직접 눈으로 확인하는 데모.
#
# 사용법:
#   chmod +x scripts/demo_observability.sh
#   ./scripts/demo_observability.sh
#
# 서버는 포그라운드로 뜨고, 다른 터미널에서 curl로 호출해보면 됩니다.
# 예:
#   curl -X POST http://127.0.0.1:8000/chat \
#     -H "Content-Type: application/json" \
#     -d '{"message":"안녕","librarian_id":"cat"}'
#
# 그러면 이 터미널에 다음과 같은 JSON 한 줄이 찍힙니다:
#   {"timestamp": "...", "level": "INFO", "service": "backend-librarian",
#    "logger": "app.librarian.main", "message": "Chat request completed",
#    "trace_id": "...", "span_id": "...", "exception": null,
#    "librarian_id": "cat", "session_id": "...", "mood": "...", "switch_to": null}
#
# trace_id/span_id가 채워져 있는 것이 이번 작업의 핵심 결과물입니다.
# Ctrl+C로 서버를 종료하세요.

export OTEL_SERVICE_NAME=backend-librarian
export OTEL_TRACES_SAMPLER_ARG=1.0
# OTEL_EXPORTER_OTLP_ENDPOINT를 설정하지 않으면 Collector 없이도 그냥 동작합니다.
# 설정하고 싶으면 아래 줄의 주석을 풀고 실제 Collector 주소를 넣으세요.
# export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

exec uv run uvicorn app.librarian.server:app --host 127.0.0.1 --port 8000
