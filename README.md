# backend-librarian

동물 사서 캐릭터가 날씨/시간대/장르에 어울리는 책을 추천하는 백엔드 에이전트

## 개요

MSA 구조의 "Don't Paw-get Your Book" 프로젝트에서 **캐릭터 페르소나 + 큐레이션 오케스트레이션** 레이어를 담당합니다.

- **고양이 사서 (나비)**: 사용자가 원하는 장르/취향을 기반으로 전 장르 도서 추천
- **황새 사서 (하루)**: 실시간 날씨와 시간대를 기반으로 분위기에 맞는 책 큐레이션

## 기술 스택

| 계층 | 기술 |
|---|---|
| Language | Python 3.13, uv |
| Agent | Strands Agents SDK |
| Model | Amazon Bedrock (Claude 3.5 Sonnet, ap-northeast-2) |
| 날씨 API | Open-Meteo (무키, 무료) |
| 웹 서버 | FastAPI + Uvicorn |
| 테스트 | pytest, ruff, respx |

## 저장소 구조

```text
backend-librarian/
├── app/librarian/
│   ├── main.py              # handle_chat 오케스트레이션 엔트리포인트
│   ├── server.py            # FastAPI 서버 (mock/bedrock 전환)
│   ├── agent.py             # Strands Agent 빌더 (Bedrock 연동)
│   ├── bedrock_agent.py     # 실제 LLM 호출 + 프롬프트 조립
│   ├── fake_agent.py        # fake 에이전트 (Bedrock 없이 테스트용)
│   ├── schemas.py           # 요청/응답 Pydantic 스키마
│   ├── librarians.py        # 사서 레지스트리 (역할/메타데이터)
│   ├── personas/
│   │   ├── base.py          # 공통 프롬프트 규칙
│   │   ├── cat.py           # 고양이 사서 시스템 프롬프트
│   │   └── stork.py         # 황새 사서 시스템 프롬프트
│   ├── curation/
│   │   └── mood.py          # 시간대×날씨 → 무드 → 장르 매핑
│   ├── tools/
│   │   └── weather.py       # Open-Meteo 날씨 조회
│   └── memory/
│       ├── base.py          # MemoryStore 인터페이스
│       └── local.py         # 인메모리 구현
├── tests/                   # 152 tests
├── scripts/
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

### fake 모드 (AWS 불필요)

```bash
uv run uvicorn app.librarian.server:app --reload
```

### Bedrock 모드 (AWS 자격증명 필요)

```bash
# 1. MFA 세션 발급 (12시간 유효)
uv run python scripts/mfa_session.py <MFA 6자리 코드>

# 2. 서버 실행
USE_BEDROCK=true AWS_PROFILE=mfa uv run uvicorn app.librarian.server:app --reload
```

### 헬스체크

```bash
curl http://localhost:8000/api/v1/health
# → {"status": "ok", "mode": "bedrock"}
```

## API 계약

### POST /api/v1/chat

**요청:**
```json
{
  "message": "미스터리 소설 추천해줘",
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
| librarian_id | X | "cat" | 사서 선택 ("cat" / "stork") |
| session_id | X | 자동 생성 | 멀티턴 대화 유지용 |
| stream | X | false | true면 text/plain 스트리밍 |
| latitude/longitude | X | 서울(stork만) | 날씨 조회용 좌표 |

**응답 (stream=false):**
```json
{
  "message": "사서 답변 텍스트",
  "session_id": "세션 ID",
  "text": "사서 답변 텍스트",
  "librarian_id": "cat",
  "switch_to": null
}
```

**switch_to 예시 (다른 사서 전환 시):**
```json
{
  "switch_to": {
    "id": "stork",
    "name": "황새 사서",
    "icon": "🪿",
    "genres": ["날씨 추천", "시간대 추천", "분위기 큐레이션", "계절 추천"]
  }
}
```

**응답 (stream=true):**
- Content-Type: text/plain; charset=utf-8
- 헤더: X-Session-Id, X-Librarian-Id, X-Switch-To(발생 시)

## 사서 역할 분담

실제 도서 추천(웹 검색)은 오케스트레이터의 검색 에이전트가 담당합니다.
이 서비스의 사서는 **페르소나 대화 + 날씨/시간대/기분 분위기 큐레이션**을 맡고,
읽어낸 신호(signals)를 응답에 실어 검색 에이전트가 활용하게 합니다.

| 사서 | 말투 | 특화 | switchTo 트리거 |
|---|---|---|---|
| cat (나비) | 반말 + "~냥" | 미스터리 | 비즈니스/경영/자기계발 주제 → stork |
| stork (하루) | 존댓말·공손 | 비즈니스 | 미스터리/추리/스릴러 주제 → cat |

### signals (응답에 포함)

```json
"signals": {
  "weather": {"condition": "rainy", "temperature": 15.0, "description": "가벼운 비"},
  "time_of_day": "evening",
  "mood": "cozy",
  "genre_focus": "미스터리"
}
```

- 날씨는 (1) 메시지에 직접 언급("비 오는 날") → (2) 좌표 기반 Open-Meteo 조회 → (3) 없으면 시간대만 순으로 결정
- 팀원 검색 에이전트가 이 signals를 활용해 실제 도서를 추천

## 오케스트레이터 연동

이 서비스는 backend-discovery 오케스트레이터에서 호출하는 구조로 설계되어 있습니다.

```
프론트 → 오케스트레이터(backend-discovery) → backend-librarian
```

- 오케스트레이터는 /api/v1/chat 으로 요청을 보냅니다
- 응답의 message/session_id 필드는 discovery 계약과 호환됩니다
- switch_to를 받으면 오케스트레이터가 대상 사서로 라우팅을 변경합니다

## 검증

```bash
uv run ruff check .
uv run pytest -q
# 152 passed
```

## 환경 변수

| 변수 | 용도 | 기본값 |
|---|---|---|
| USE_BEDROCK | true면 Bedrock, 미설정이면 fake | 미설정(mock) |
| AWS_PROFILE | MFA 세션 프로필 | - |
| AWS_REGION | Bedrock 리전 | ap-northeast-2 |
| BEDROCK_MODEL_ID | Bedrock 모델 | anthropic.claude-3-5-sonnet-20240620-v1:0 |
