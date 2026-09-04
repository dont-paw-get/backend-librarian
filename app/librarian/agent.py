"""Strands Agent 빌더 — Bedrock 모델 연동.

librarian_id에 따라 적절한 페르소나와 도구를 조합한 Strands Agent를 생성합니다.

모델/리전은 환경변수로 재정의할 수 있습니다.
    BEDROCK_MODEL_ID, AWS_REGION
"""

import os

from strands import Agent
from strands.models import BedrockModel

from app.librarian.personas.cat import get_cat_system_prompt
from app.librarian.personas.stork import get_stork_system_prompt

# 베어 모델 ID 는 ap-northeast-2 on-demand 호출이 거부되므로 크로스리전
# inference profile 을 기본값으로 둔다. global. 프로파일은 전 리전 라우팅.
DEFAULT_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
DEFAULT_REGION = "ap-northeast-2"


def _resolve_model_id(model_id: str | None = None) -> str:
    return model_id or os.environ.get("BEDROCK_MODEL_ID") or DEFAULT_MODEL_ID


def _resolve_region(region: str | None = None) -> str:
    return region or os.environ.get("AWS_REGION") or DEFAULT_REGION


def _create_model(model_id: str | None = None, region: str | None = None) -> BedrockModel:
    """Bedrock 모델 인스턴스를 생성합니다."""
    return BedrockModel(
        model_id=_resolve_model_id(model_id),
        region_name=_resolve_region(region),
    )


def build_cat_agent(model=None, tools: list | None = None) -> Agent:
    """cat 사서 에이전트를 생성합니다."""
    kwargs: dict = {
        "system_prompt": get_cat_system_prompt(),
        "model": model if model is not None else _create_model(),
        # 기본 콜백 핸들러는 응답을 stdout에 출력합니다.
        # Windows 콘솔(cp949)에서 이모지 인코딩 오류가 발생하므로 비활성화합니다.
        "callback_handler": None,
    }
    if tools:
        kwargs["tools"] = tools
    return Agent(**kwargs)


def build_stork_agent(model=None, tools: list | None = None) -> Agent:
    """stork 사서 에이전트를 생성합니다."""
    kwargs: dict = {
        "system_prompt": get_stork_system_prompt(),
        "model": model if model is not None else _create_model(),
        "callback_handler": None,
    }
    if tools:
        kwargs["tools"] = tools
    return Agent(**kwargs)
