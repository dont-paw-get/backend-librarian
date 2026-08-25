"""MFA 세션 자격증명 발급 스크립트.

교육 계정(kosa-edu-mfa-pol 정책)은 MFA 인증 없는 API 호출을 거부합니다.
이 스크립트로 임시 세션 자격증명을 발급받아 환경변수로 export 합니다.

사용법:
    # 1. MFA 코드로 세션 발급 (bash)
    eval $(uv run python scripts/mfa_session.py 123456)

    # 2. 발급 확인
    aws sts get-caller-identity

    # 3. 서버 실행 (같은 셸에서)
    USE_BEDROCK=true uv run uvicorn app.librarian.server:app --reload

세션은 기본 12시간 유효합니다.
"""

import argparse
import sys

import boto3
from botocore.exceptions import ClientError

DEFAULT_DURATION_SECONDS = 43200  # 12시간


def get_mfa_serial(iam_client, user_name: str | None = None) -> str:
    """사용자의 MFA 디바이스 ARN을 조회합니다."""
    kwargs = {"UserName": user_name} if user_name else {}
    devices = iam_client.list_mfa_devices(**kwargs).get("MFADevices", [])
    if not devices:
        raise RuntimeError("등록된 MFA 디바이스가 없습니다.")
    return devices[0]["SerialNumber"]


def main() -> int:
    parser = argparse.ArgumentParser(description="MFA 세션 자격증명 발급")
    parser.add_argument("token_code", help="MFA 앱에 표시된 6자리 코드")
    parser.add_argument("--serial", default=None, help="MFA 디바이스 ARN (미지정 시 자동 조회)")
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION_SECONDS,
        help=f"세션 유효 기간(초). 기본 {DEFAULT_DURATION_SECONDS}",
    )
    args = parser.parse_args()

    try:
        serial = args.serial or get_mfa_serial(boto3.client("iam"))
    except (ClientError, RuntimeError) as e:
        print(f"# MFA 디바이스 조회 실패: {e}", file=sys.stderr)
        print("# --serial 옵션으로 직접 지정해 보세요.", file=sys.stderr)
        return 1

    try:
        response = boto3.client("sts").get_session_token(
            DurationSeconds=args.duration,
            SerialNumber=serial,
            TokenCode=args.token_code,
        )
    except ClientError as e:
        print(f"# 세션 토큰 발급 실패: {e}", file=sys.stderr)
        return 1

    creds = response["Credentials"]
    # eval 로 바로 적용할 수 있도록 export 구문 출력
    print(f"export AWS_ACCESS_KEY_ID={creds['AccessKeyId']}")
    print(f"export AWS_SECRET_ACCESS_KEY={creds['SecretAccessKey']}")
    print(f"export AWS_SESSION_TOKEN={creds['SessionToken']}")
    print(f"# 만료: {creds['Expiration'].isoformat()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
