"""Bedrock 모드 end-to-end 스모크 테스트.

두 가지 방법으로 실행할 수 있습니다.

1) 이미 MFA 세션이 적용된 셸에서:
    eval $(uv run python scripts/mfa_session.py <MFA코드>)
    uv run python scripts/smoke_bedrock_chat.py

2) MFA 코드를 인자로 넘겨 이 스크립트가 직접 세션을 발급:
    uv run python scripts/smoke_bedrock_chat.py <MFA코드>
"""

import asyncio
import os
import sys

# Windows 콘솔(cp949)에서 이모지 출력 시 UnicodeEncodeError가 발생하므로 UTF-8로 강제합니다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CASES = [
    ("cat", "비 오는 날에 어울리는 책 추천해줘"),
    ("stork", "오늘 날씨에 맞는 책 추천해줘"),
    ("cat", "미스터리 소설 추천해줘"),
]


def apply_mfa_session(token_code: str) -> None:
    """MFA 세션 자격증명을 발급해 현재 프로세스 환경변수에 적용합니다."""
    import boto3

    devices = boto3.client("iam").list_mfa_devices().get("MFADevices", [])
    if not devices:
        raise RuntimeError("등록된 MFA 디바이스가 없습니다.")

    creds = boto3.client("sts").get_session_token(
        DurationSeconds=43200,
        SerialNumber=devices[0]["SerialNumber"],
        TokenCode=token_code,
    )["Credentials"]

    os.environ["AWS_ACCESS_KEY_ID"] = creds["AccessKeyId"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = creds["SecretAccessKey"]
    os.environ["AWS_SESSION_TOKEN"] = creds["SessionToken"]
    print(f"MFA 세션 적용 완료 (만료: {creds['Expiration'].isoformat()})\n")


async def run_cases() -> None:
    # 자격증명 적용 이후에 임포트해야 모델 클라이언트가 올바른 세션을 사용합니다.
    from app.librarian.bedrock_agent import bedrock_cat_agent, bedrock_stork_agent
    from app.librarian.main import handle_chat
    from app.librarian.memory.local import LocalMemoryStore
    from app.librarian.schemas import ChatRequest

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


def main() -> int:
    if len(sys.argv) > 1:
        try:
            apply_mfa_session(sys.argv[1])
        except Exception as e:  # noqa: BLE001
            print(f"MFA 세션 발급 실패: {e}")
            return 1

    asyncio.run(run_cases())
    return 0


if __name__ == "__main__":
    sys.exit(main())
