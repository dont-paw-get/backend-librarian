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
    """사용자 메시지와 컨텍스트를 결합한 프롬프트를 생성합니다."""
    parts = []

    # 날씨 정보 — stork는 날씨를 강조
    weather = context.get("weather", {})
    if weather.get("condition"):
        temp_str = f", 기온 {weather['temperature']}°C" if weather.get("temperature") else ""
        desc = weather.get("description", weather["condition"])
        if librarian_id == "stork":
            parts.append(
                f"[현재 날씨 정보 — 이 정보를 반드시 활용해 추천해주세요]\n"
                f"  날씨: {desc}{temp_str}\n"
                f"  이 날씨에 어울리는 분위기와 연결해 책을 추천해주세요."
            )
        else:
            parts.append(f"[현재 날씨: {desc}{temp_str}]")

    # 무드 정보
    mood = context.get("mood")
    if mood:
        parts.append(f"[현재 무드: {mood}]")

    # 추천 장르
    genres = context.get("recommended_genres", [])
    if genres:
        parts.append(f"[추천 장르: {', '.join(genres)}]")

    # 이전 대화 맥락
    history = context.get("session_history", [])
    if history:
        recent = history[-4:]  # 최근 4턴만
        history_text = "\n".join(f"{h['role']}: {h['content']}" for h in recent)
        parts.append(f"[이전 대화]\n{history_text}")

    # 선호 장르
    prefs = context.get("preferred_genres", [])
    if prefs:
        parts.append(f"[사용자 선호 장르: {', '.join(prefs)}]")

    # 컨텍스트 + 실제 메시지
    context_block = "\n".join(parts)
    if context_block:
        return f"{context_block}\n\n사용자: {message}"
    return message


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
    agent = _get_cat_agent()
    prompt = _build_prompt(message, context, librarian_id="cat")

    try:
        result = agent(prompt)
        return _strip_thinking(str(result))
    except Exception as e:
        _log_agent_failure("cat", e)
        return "미안하다냥, 지금 잠시 생각이 안 나는 거 같다냥... 🙀 다시 물어봐줄 수 있다냥?"


async def bedrock_stork_agent(message: str, context: dict) -> str:
    """Bedrock 기반 stork 사서 에이전트 호출.

    Args:
        message: 사용자 메시지
        context: handle_chat이 조립한 맥락

    Returns:
        LLM 생성 응답 텍스트
    """
    agent = _get_stork_agent()
    prompt = _build_prompt(message, context, librarian_id="stork")

    try:
        result = agent(prompt)
        return _strip_thinking(str(result))
    except Exception as e:
        _log_agent_failure("stork", e)
        return "죄송합니다, 잠시 생각을 정리하고 있어요 🪿 다시 말씀해주시겠어요?"
