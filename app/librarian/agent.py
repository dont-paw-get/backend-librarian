"""Strands Agent 빌더 — Bedrock 모델 연동.

librarian_id에 따라 적절한 페르소나와 도구를 조합한 Strands Agent를 생성합니다.
"""

from strands import Agent
from strands.models import BedrockModel

from app.librarian.personas.cat import get_cat_system_prompt
from app.librarian.personas.stork import get_stork_system_prompt

# 기본 모델 설정
DEFAULT_MODEL_ID = "us.anthropic.claude-3-haiku-20240307-v1:0"
DEFAULT_REGION = "us-west-2"


def _create_model(model_id: str | None = None, region: str | None = None) -> BedrockModel:
    """Bedrock 모델 인스턴스를 생성합니다."""
    return BedrockModel(
        model_id=model_id or DEFAULT_MODEL_ID,
        region_name=region or DEFAULT_REGION,
    )


def build_cat_agent(model=None, tools: list | None = None) -> Agent:
    """cat 사서 에이전트를 생성합니다."""
    system_prompt = get_cat_system_prompt()
    if model is None:
        model = _create_model()

    kwargs: dict = {"system_prompt": system_prompt, "model": model}
    if tools:
        kwargs["tools"] = tools
    return Agent(**kwargs)


def build_stork_agent(model=None, tools: list | None = None) -> Agent:
    """stork 사서 에이전트를 생성합니다."""
    system_prompt = get_stork_system_prompt()
    if model is None:
        model = _create_model()

    kwargs: dict = {"system_prompt": system_prompt, "model": model}
    if tools:
        kwargs["tools"] = tools
    return Agent(**kwargs)
