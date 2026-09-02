# backend-librarian

동물 사서 캐릭터가 날씨/시간대/장르에 어울리는 책을 추천하는 백엔드 에이전트

## 개요

MSA 구조의 "Don't Paw-get Your Book" 프로젝트에서 **캐릭터 페르소나 + 큐레이션 오케스트레이션** 레이어를 담당합니다.

- **고양이 사서 (블루)**: 친근한 반말(~냥) 말투. 전 장르 추천 가능하며 **미스터리·추리·탐정·스릴러**에 특화되어 더 깊이 있게 추천 및 상담
- **황새 사서 (슈빌)**: 차분하고 정중한 존댓말(공손체). 전 장르 추천 가능하며 **비즈니스·경영·경제·투자**에 특화되어 더 깊이 있게 추천 및 상담
- **공통 도구**: 두 사서 모두 실시간 날씨(Open-Meteo)와 시간대를 활용하여 상황과 분위기에 맞는 큐레이션을 제공합니다.

## 기술 스택

| 계층 | 기술 |
|---|---|
| Language | Python 3.13+, uv |
| Agent | Strands Agents SDK |
| Model | Amazon Bedrock (Claude 3.5 Sonnet, ap-northeast-2) / Fake Agent fallback |
| 날씨 API | Open-Meteo (무키, 무료) |
| 웹 서버 | FastAPI + Uvicorn |
| 테스트 | pytest, ruff, respx |

## 저장소 구조

```text
backend-librarian/
├── app/librarian/
│   ├── main.py              # handle_chat 오케스트레이션 엔트리포인트 (signals & switch_to 다중 안전망)
│   ├── server.py            # FastAPI 서버 (mock/bedrock 전환, CORS, X-Signals 헤더)
│   ├── agent.py             # Strands Agent 빌더 (Bedrock 연동)
│   ├── bedrock_agent.py     # 실제 LLM 호출 + 프롬프트 조립 + fake graceful fallback
│   ├── fake_agent.py        # fake 에이전트 (역할 기반 결정론적 라우팅)
│   ├── schemas.py           # 요청/응답 Pydantic 스키마 (LibrarianSignals, SwitchTo)
│   ├── librarians.py        # 사서 레지스트리 (블루/슈빌 메타데이터)
│   ├── personas/
│   │   ├── base.py          # 공통 프롬프트 규칙
│   │   ├── cat.py           # 고양이 사서(블루) 시스템 프롬프트
│   │   └── stork.py         # 황새 사서(슈빌) 시스템 프롬프트
│   ├── curation/
│   │   └── mood.py          # 시간대×날씨 → 무드 → 장르 매핑
│   ├── tools/
│   │   └── weather.py       # Open-Meteo 날씨 조회
│   └── memory/
│       ├── base.py          # MemoryStore 인터페이스
│       └── local.py         # 인메모리 구현
├── docs/
│   └── INTEGRATION_MANUAL.md # 사서 연동 & 트러블슈팅 매뉴얼
├── tests/                   # 163 tests (100% passed)
├── scripts/
│   ├── run_server.sh        # 서버 실행 (--host 0.0.0.0, 외부 접속용)
│   ├── mfa_session.py       # MFA 세션 자격증명 발급
│   ├── smoke_bedrock_chat.py # Bedrock end-to-end 스모크
│   └── verify_bedrock_mfa.py # 모델/리전 접근 진단
├── pyproject.toml
└── uv.lock
```

## 실행 방법

### 환경 준비

```bash
uv sync --frozen
```

### fake 모드 (AWS 불필요, 기본 개발용)

```bash
uv run uvicorn app.librarian.server:app --reload --port 8000
```

### Bedrock 모드 (AWS 자격증명 필요)

```bash
# 1. MFA 세션 발급 (12시간 유효)
uv run python scripts/mfa_session.py <MFA 6자리 코드>

# 2. 서버 실행
USE_BEDROCK=true AWS_PROFILE=mfa uv run uvicorn app.librarian.server:app --reload --port 8000
```

### 외부(오케스트레이터/다른 기기)에서 접속해야 할 때

기본값(`127.0.0.1`)은 **내 컴퓨터에서만** 접근됩니다. 오케스트레이터가 다른 기기(예: 팀원 맥북)에서
이 서버로 요청을 보내야 하면 **반드시 `--host 0.0.0.0`** 을 붙여 모든 인터페이스에 바인딩해야 합니다.

```bash
USE_BEDROCK=true AWS_PROFILE=mfa uv run uvicorn app.librarian.server:app --host 0.0.0.0 --port 8000 --reload
```

편의 스크립트로도 실행할 수 있습니다 (`--host 0.0.0.0 --port 8000` 기본 포함):

```bash
# fake 모드
bash scripts/run_server.sh

# Bedrock 모드
USE_BEDROCK=true AWS_PROFILE=mfa bash scripts/run_server.sh
```

> 팀원은 `http://<내-IP>:8000/api/v1/chat` 으로 접속합니다.
> 내 IP 확인: Windows `ipconfig` / macOS·Linux `ifconfig` 또는 `ip addr`.
> 같은 네트워크(Wi-Fi)에 있어야 하며, 방화벽에서 8000 포트 인바운드를 허용해야 할 수 있습니다.

### 헬스체크

```bash
curl http://localhost:8000/api/v1/health
# → {"status": "ok", "mode": "mock"}
```

## API 계약

### POST /api/v1/chat (별칭: /chat)

**요청:**
```json
{
  "message": "SF 소설 추천해줘",
  "librarian_id": "cat",
  "session_id": "optional-session-id",
  "stream": false,
  "latitude": 37.5665,
  "longitude": 126.9780
}
```

| 필드 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| message | O | - | 사용자 메시지 (1~2000자) |
| librarian_id | X | "cat" | 현재 사서 선택 ("cat" / "stork") |
| session_id | X | 자동 생성 | 멀티턴 대화 유지용 UUID |
| stream | X | false | true면 text/plain 스트리밍 응답 |
| latitude/longitude | X | 37.5665, 126.9780 | 날씨 조회용 위도/경도 (생략 시 서울 기본값) |

**응답 (stream=false):**
```json
{
  "message": "비즈니스나 경영, 경제 관련 전문 지식은 우리 황새 사서 슈빌이 훨씬 더 해박하고 깊이 있는 통찰을 준다냥! 🪿\n\n슈빌한테 가면 훨씬 더 자세하고 전문적으로 알려줄 거다냥!\n\n내가 황새 사서한테 연결해줄게냥~ 😺 [전환제안: stork]",
  "session_id": "sess-1234-abcd",
  "text": "비즈니스나 경영, 경제 관련 전문 지식은 우리 황새 사서 슈빌이 훨씬 더 해박하고 깊이 있는 통찰을 준다냥! 🪿\n\n슈빌한테 가면 훨씬 더 자세하고 전문적으로 알려줄 거다냥!\n\n내가 황새 사서한테 연결해줄게냥~ 😺 [전환제안: stork]",
  "librarian_id": "cat",
  "switch_to": {
    "id": "stork",
    "name": "황새 사서",
    "icon": "🪿",
    "genres": ["비즈니스", "경영", "경제", "투자", "자기계발", "SF", "과학", "역사"],
    "reason": "황새 사서 전문 분야 추천"
  },
  "signals": {
    "weather": {
      "weather": "맑음",
      "condition": "clear",
      "temperature": 27.5,
      "is_rainy": false,
      "description": "맑음",
      "location_source": "user"
    },
    "time_of_day": "day",
    "mood": "adventurous",
    "genre_focus": ["판타지", "SF", "여행", "모험"]
  }
}
```

**응답 (stream=true):**
- Content-Type: `text/plain; charset=utf-8` (본문은 텍스트 청크 스트리밍)
- 헤더: `X-Session-Id`, `X-Librarian-Id`, `X-Switch-To` (전환 시), `X-Signals` (JSON 문자열)

## 사서 역할 분담 및 스위칭 규칙

| 사서 | 이름 | 말투 | 특화 주제 | 기본 추천 범위 | switchTo 트리거 |
|---|---|---|---|---|---|
| **cat (고양이)** | 블루 | 친근한 반말, 문장 끝 "~냥" | 🔍 미스터리·추리·탐정·스릴러 | 전 장르 100% 추천 가능 | 비즈니스/경영/경제 심층 질문 또는 "황새", "슈빌" 호칭 시 ➔ `stork` 제안 |
| **stork (황새)** | 슈빌 | 차분하고 정중한 존댓말(공손체 '두둥!'), 추임새 '두둥!'/'두둥...' | 📈 비즈니스·경영·경제·투자 | 전 장르 100% 추천 가능 | 미스터리/추리 심층 질문 또는 "고양이", "블루" 호칭 시 ➔ `cat` 제안 |

### signals (응답에 포함)

```json
"signals": {
  "weather": {
    "condition": "rainy",
    "temperature": 15.0,
    "description": "가벼운 비",
    "location_source": "user"
  },
  "time_of_day": "evening",
  "mood": "cozy",
  "genre_focus": "미스터리"
}
```

**location_source** — 이 날씨가 어디 기준인지 구분 (UI에서 신뢰도 표시에 활용):

| 값 | 의미 | 기온(temperature) |
|---|---|---|
| `user` | 사용자가 보낸 실제 좌표로 조회 | 있음, 신뢰 가능 |
| `default_seoul` | 좌표 없어 stork가 서울 기본값으로 조회 (사용자 실제 위치 아님) | 있음, 서울 기준 |
| `text_stated` | 사용자가 메시지에 날씨를 직접 언급 ("비 오는 날") | 없음 (null) |
| `none` | 날씨 정보 없음 (시간대만 사용) | 없음 (null) |

## 검증 및 린트

```bash
uv run ruff check .
uv run pytest -q
# 163 passed in 13s
```

## 환경 변수

| 변수 | 용도 | 기본값 |
|---|---|---|
| USE_BEDROCK | true면 Bedrock 호출, 미설정이면 fake 에이전트 | 미설정(mock) |
| AWS_PROFILE | MFA 세션 프로필 | - |
| AWS_REGION | Bedrock 리전 | ap-northeast-2 |
| BEDROCK_MODEL_ID | Bedrock 모델 ID | anthropic.claude-3-5-sonnet-20240620-v1:0 |
| OTEL_SERVICE_NAME | 트레이스/로그의 서비스 이름 **및 `/actuator/prometheus` 의 `application` 라벨** | backend-librarian |
| OTEL_EXPORTER_OTLP_ENDPOINT | OTLP HTTP Collector 엔드포인트. 설정 시에만 트레이스 전송 활성화 | 미설정(exporter 비활성화) |
| OTEL_EXPORTER_OTLP_PROTOCOL | OTLP 전송 프로토콜 (infra Collector 는 `http/protobuf` + 4318) | http/protobuf |
| OTEL_TRACES_SAMPLER_ARG | 트레이스 샘플링 비율 (0.0~1.0) | 1.0 |
| LOG_LEVEL | 루트 로거 레벨 | INFO |

## Prometheus 메트릭 (`/actuator/prometheus`)

- FastAPI 서비스지만 Spring Boot / Micrometer 와 **동일한 메트릭 이름·라벨**로 HTTP 요청 수/지연을
  노출합니다: `http_server_requests_seconds_count` / `_sum` / `_bucket`
  (라벨: `application`, `method`, `uri`, `status`, `outcome`). infra 의 5xx 에러율·p99 레이턴시
  알림 규칙(Micrometer 기준)이 수정 없이 동작합니다.
- `application` 라벨 = `OTEL_SERVICE_NAME` — 메트릭 ↔ 로그 ↔ 트레이스 상관분석 키.
- dev 클러스터에서는 `k8s/overlays/dev/servicemonitor.yaml` 의 `ServiceMonitor` 가 이 경로를
  30초 간격으로 스크레이핑합니다.
- `/health`, `/actuator/prometheus`, `/livez`, `/readyz` 등 probe·스크레이핑 경로는 집계에서 제외됩니다.

```bash
curl -s http://localhost:8000/actuator/prometheus | grep http_server_requests_seconds_count
```

## 분산 트레이싱 / 구조화 로깅

- `OTEL_EXPORTER_OTLP_ENDPOINT`가 설정된 경우에만 OTLP(HTTP/protobuf) exporter가 활성화됩니다. 미설정 시 로컬 개발에서도 정상 동작합니다.
- FastAPI(`/chat`, `/api/v1/chat` 등)와 httpx(Open-Meteo 등 outbound 호출), boto3/botocore(Bedrock) 호출이 자동 계측됩니다. `/health`, `/api/v1/health`는 트레이스에서 제외됩니다.
- httpx 자동 계측을 통해 outbound 요청에 W3C `traceparent` 헤더가 자동 주입되어, 다른 서비스(backend-discovery 등)를 호출할 경우 동일 Trace로 연결됩니다.
- Bedrock 모드에서는 Strands Agent가 전역 TracerProvider를 재사용해 `invoke_agent`, `chat`, `execute_event_loop_cycle` span을 자동 생성합니다. `librarian.recommendation` custom span은 fake 모드처럼 자동 계측이 없는 경우에도 agent 처리 구간의 latency/실패를 관측할 수 있도록 추가되었습니다.
- 로그는 stdout으로 JSON 형식(`timestamp`, `level`, `service`, `logger`, `message`, `trace_id`, `span_id`, `exception`)으로 출력됩니다. Kubernetes에서는 Grafana Alloy가 stdout을 수집해 Loki로 전송하므로 별도 push client는 사용하지 않습니다.
- 사용자 메시지, 프롬프트, LLM 응답 원문은 로그와 span에 기록되지 않습니다. Strands Agent의 `gen_ai.*` 콘텐츠는 redaction이 강제로 활성화되어 `[REDACTED]`로 대체됩니다.
