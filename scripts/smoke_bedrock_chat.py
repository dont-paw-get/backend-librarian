"""Bedrock 모드 end-to-end 스모크 테스트.

MFA 세션 자격증명이 설정된 셸에서 실행하세요.
    eval $(uv run python scripts/mfa_session.py <MFA코드>)
    uv run python scripts/smoke_bedrock_chat.py
"""

import asyncio
import sys

from app.librarian.bedrock_agent import bedrock_cat_agent, bedrock_stork_agent
from app.librarian.main import handle_chat
from app.librarian.memory.local import LocalMemoryStore
from app.librarian.schemas import ChatRequest

CASES = [
    ("cat", "비 오는 날에 어울리는 책 추천해줘"),
    ("stork", "오늘 날씨에 맞는 책 추천해줘"),
    ("cat", "미스터리 소설 추천해줘"),
]


async def main() -> int:
    memory = LocalMemoryStore()
    agents = {"cat": bedrock_cat_agent, "stork": bedrock_stork_agent}

    for librarian_id, message in CASES:
        request = ChatRequest(
            message=message,
            librarian_id=librarian_id,
            session_id=f"smoke-{librarian_id}",
        )
        result = await handle_chat(
            request=request,
            memory=memory,
            weather_provider=None,
            agent_callable=agents[librarian_id],
        )
        print("=" * 70)
        print(f"[{librarian_id}] {message}")
        print("-" * 70)
        print(result.text)
        if result.switch_to:
            print(f"\n>>> switchTo: {result.switch_to.id} ({result.switch_to.name})")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
