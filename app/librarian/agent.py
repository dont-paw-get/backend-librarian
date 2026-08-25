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

# 교육 계정(ap-northeast-2)에서 호출 가능한 것으로 확인된 조합
DEFAULT_MODEL_ID = "anthropic.claude-3-5-sonnet-20240620-v1:0"
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
    }
    if tools:
        kwargs["tools"] = tools
    return Agent(**kwargs)


def build_stork_agent(model=None, tools: list | None = None) -> Agent:
    """stork 사서 에이전트를 생성합니다."""
    kwargs: dict = {
        "system_prompt": get_stork_system_prompt(),
        "model": model if model is not None else _create_model(),
    }
    if tools:
        kwargs["tools"] = tools
    return Agent(**kwargs)
