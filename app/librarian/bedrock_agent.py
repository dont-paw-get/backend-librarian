"""Bedrock 기반 실제 에이전트 응답기.

fake_agent.py를 대체하여 실제 LLM으로 응답을 생성합니다.
handle_chat의 agent_callable 인터페이스에 맞춥니다.
"""

import logging
import re

from app.librarian.agent import build_cat_agent, build_stork_agent

logger = logging.getLogger(__name__)

# 에이전트 싱글턴 (서버 수명 내 재사용)
_cat_agent = None
_stork_agent = None


def _get_cat_agent():
    global _cat_agent
    if _cat_agent is None:
        _cat_agent = build_cat_agent()
    return _cat_agent


def _get_stork_agent():
    global _stork_agent
    if _stork_agent is None:
        _stork_agent = build_stork_agent()
    return _stork_agent


def _build_prompt(message: str, context: dict, librarian_id: str = "cat") -> str:
    """사용자 메시지와 컨텍스트를 결합한 프롬프트를 생성합니다.

    실제 도서 추천은 검색 사서가 담당하므로, 여기서는 날씨/시간대/무드를 읽어
    분위기를 잡아주는 대화를 유도합니다. 구체적 책 제목은 언급하지 않습니다.
    """
    parts = []

    # 날씨/시간대/무드 신호
    weather = context.get("weather", {})
    if weather.get("condition"):
        temp_str = f", 기온 {weather['temperature']}°C" if weather.get("temperature") else ""
        desc = weather.get("description", weather["condition"])
        parts.append(f"[현재 날씨: {desc}{temp_str}]")

    time_of_day = context.get("time_of_day")
    if time_of_day:
        parts.append(f"[시간대: {time_of_day}]")

    mood = context.get("mood")
    if mood:
        parts.append(f"[무드: {mood}]")

    genre_focus = context.get("genre_focus")
    if genre_focus:
        parts.append(f"[당신의 특화 장르: {genre_focus}]")

    # 이전 대화 맥락
    history = context.get("session_history", [])
    if history:
        recent = history[-4:]  # 최근 4턴만
        history_text = "\n".join(f"{h['role']}: {h['content']}" for h in recent)
        parts.append(f"[이전 대화]\n{history_text}")

    # 응답 지침
    parts.append(
        "[지침] 위 날씨·시간대·무드를 자연스럽게 반영해 대화하세요. "
        "구체적인 책 제목이나 저자는 언급하지 말고, 어떤 분위기·방향의 독서가 어울릴지 "
        "페르소나에 맞게 이야기하며 사용자의 취향을 물어보세요."
    )

    context_block = "\n".join(parts)
    return f"{context_block}\n\n사용자: {message}"


def check_bedrock_access() -> tuple[bool, str]:
    """Bedrock 호출이 가능한지 확인합니다.

    Returns:
        (성공 여부, 상세 메시지)
    """
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    from app.librarian.agent import _resolve_model_id, _resolve_region

    model_id = _resolve_model_id()
    region = _resolve_region()

    try:
        boto3.client("bedrock-runtime", region_name=region).converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": "ping"}]}],
            inferenceConfig={"maxTokens": 8},
        )
        return True, f"{region} / {model_id}"
    except NoCredentialsError:
        return False, "AWS 자격증명을 찾을 수 없습니다."
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "AccessDeniedException":
            return False, "AccessDenied — MFA 세션 자격증명이 필요합니다."
        if code == "ExpiredTokenException":
            return False, "세션이 만료되었습니다. MFA 세션을 재발급하세요."
        if code in ("ValidationException", "ResourceNotFoundException"):
            return False, f"{code} — 모델 ID/리전 확인 필요 ({region} / {model_id})"
        return False, f"{code}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def _log_agent_failure(librarian_id: str, error: Exception) -> None:
    """에이전트 호출 실패를 로깅하고, 흔한 원인에 대한 힌트를 남깁니다."""
    logger.error(f"Bedrock {librarian_id} agent 호출 실패: {error}")

    message = str(error)
    if "AccessDenied" in message or "not authorized" in message:
        logger.error(
            "→ MFA 세션 자격증명이 없을 수 있습니다. "
            "eval $(uv run python scripts/mfa_session.py <MFA코드>) 실행 후 서버를 재시작하세요."
        )
    elif "ValidationException" in message or "ResourceNotFound" in message:
        logger.error(
            "→ 모델 ID가 현재 리전에서 유효하지 않을 수 있습니다. "
            "BEDROCK_MODEL_ID / AWS_REGION 환경변수를 확인하세요."
        )
    elif "ExpiredToken" in message:
        logger.error("→ MFA 세션이 만료되었습니다. 세션을 다시 발급하세요.")


def _strip_thinking(text: str) -> str:
    """모델 응답에서 <thinking> 블록을 제거합니다."""
    # 완결된 thinking 블록 제거
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)
    # 잘린 thinking 블록 (열린 채 끝남) 제거
    thinking_start = text.find("<thinking>")
    if thinking_start != -1:
        text = text[:thinking_start]
    return text.strip()


async def bedrock_cat_agent(message: str, context: dict) -> str:
    """Bedrock 기반 cat 사서 에이전트 호출.

    Args:
        message: 사용자 메시지
        context: handle_chat이 조립한 맥락

    Returns:
        LLM 생성 응답 텍스트
    """
    from app.librarian.fake_agent import fake_cat_agent

    agent = _get_cat_agent()
    prompt = _build_prompt(message, context, librarian_id="cat")

    try:
        result = agent(prompt)
        return _strip_thinking(str(result))
    except Exception as e:
        _log_agent_failure("cat", e)
        # silent failure 방지: fake_agent로 매끄럽게 graceful fallback
        return await fake_cat_agent(message, context)


async def bedrock_stork_agent(message: str, context: dict) -> str:
    """Bedrock 기반 stork 사서 에이전트 호출.

    Args:
        message: 사용자 메시지
        context: handle_chat이 조립한 맥락

    Returns:
        LLM 생성 응답 텍스트
    """
    from app.librarian.fake_agent import fake_stork_agent

    agent = _get_stork_agent()
    prompt = _build_prompt(message, context, librarian_id="stork")

    try:
        result = agent(prompt)
        return _strip_thinking(str(result))
    except Exception as e:
        _log_agent_failure("stork", e)
        # silent failure 방지: fake_agent로 매끄럽게 graceful fallback
        return await fake_stork_agent(message, context)

