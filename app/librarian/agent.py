"""Strands Agent 빌더 (모델 주입식).

모델을 외부에서 주입받아 테스트에서는 fake, 프로덕션에서는 Bedrock을 사용합니다.
"""

from strands import Agent

from app.librarian.personas.cat import get_cat_system_prompt


def build_cat_agent(model=None, tools: list | None = None) -> Agent:
    """cat 사서 에이전트를 생성합니다.

    Args:
        model: Strands 모델 인스턴스 (None이면 기본 Bedrock 사용 시도)
        tools: 에이전트에 부여할 도구 목록

    Returns:
        구성된 Strands Agent
    """
    system_prompt = get_cat_system_prompt()

    kwargs: dict = {
        "system_prompt": system_prompt,
    }

    if model is not None:
        kwargs["model"] = model

    if tools:
        kwargs["tools"] = tools

    return Agent(**kwargs)
