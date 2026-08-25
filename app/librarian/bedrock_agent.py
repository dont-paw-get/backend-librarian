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


def _build_prompt(message: str, context: dict) -> str:
    """사용자 메시지와 컨텍스트를 결합한 프롬프트를 생성합니다."""
    parts = []

    # 날씨 정보
    weather = context.get("weather", {})
    if weather.get("condition"):
        temp_str = f", 기온 {weather['temperature']}°C" if weather.get("temperature") else ""
        parts.append(f"[현재 날씨: {weather.get('description', weather['condition'])}{temp_str}]")

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
    prompt = _build_prompt(message, context)

    try:
        result = agent(prompt)
        response_text = str(result)
        response_text = _strip_thinking(response_text)
        return response_text
    except Exception as e:
        logger.error(f"Bedrock cat agent 호출 실패: {e}")
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
    prompt = _build_prompt(message, context)

    try:
        result = agent(prompt)
        response_text = str(result)
        response_text = _strip_thinking(response_text)
        return response_text
    except Exception as e:
        logger.error(f"Bedrock stork agent 호출 실패: {e}")
        return "죄송합니다, 잠시 생각을 정리하고 있어요 🪿 다시 말씀해주시겠어요?"
