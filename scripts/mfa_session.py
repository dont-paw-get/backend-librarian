"""MFA 세션 자격증명 발급 스크립트.

교육 계정(kosa-edu-mfa-pol 정책)은 MFA 인증 없는 API 호출을 거부합니다.
이 스크립트로 임시 세션 자격증명을 발급받습니다.

기본 동작: ~/.aws/credentials 의 [mfa] 프로필에 저장합니다.
터미널을 새로 열어도 유지되므로 권장하는 방식입니다.

    uv run python scripts/mfa_session.py 123456
    USE_BEDROCK=true AWS_PROFILE=mfa uv run uvicorn app.librarian.server:app --reload

--export 옵션을 주면 셸 환경변수용 export 구문을 출력합니다.
이 경우 자격증명은 해당 셸에서만 유효합니다.

    eval $(uv run python scripts/mfa_session.py 123456 --export)

세션은 기본 12시간 유효합니다.
"""

import argparse
import configparser
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

DEFAULT_DURATION_SECONDS = 43200  # 12시간
DEFAULT_PROFILE = "mfa"
CREDENTIALS_PATH = Path.home() / ".aws" / "credentials"


def get_mfa_serial() -> str:
    """등록된 첫 번째 MFA 디바이스 ARN을 조회합니다."""
    devices = boto3.client("iam").list_mfa_devices().get("MFADevices", [])
    if not devices:
        raise RuntimeError("등록된 MFA 디바이스가 없습니다.")
    return devices[0]["SerialNumber"]


def issue_session(token_code: str, serial: str, duration: int) -> dict:
    """STS 세션 토큰을 발급합니다."""
    return boto3.client("sts").get_session_token(
        DurationSeconds=duration,
        SerialNumber=serial,
        TokenCode=token_code,
    )["Credentials"]


def write_profile(creds: dict, profile: str) -> None:
    """~/.aws/credentials 에 프로필로 저장합니다."""
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)

    config = configparser.ConfigParser()
    if CREDENTIALS_PATH.exists():
        config.read(CREDENTIALS_PATH)

    if not config.has_section(profile):
        config.add_section(profile)

    config[profile]["aws_access_key_id"] = creds["AccessKeyId"]
    config[profile]["aws_secret_access_key"] = creds["SecretAccessKey"]
    config[profile]["aws_session_token"] = creds["SessionToken"]

    with CREDENTIALS_PATH.open("w", encoding="utf-8") as f:
        config.write(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="MFA 세션 자격증명 발급")
    parser.add_argument("token_code", help="MFA 앱에 표시된 6자리 코드")
    parser.add_argument(
        "--export",
        action="store_true",
        help="프로필 저장 대신 셸 export 구문을 출력 (eval 과 함께 사용)",
    )
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help=f"저장할 프로필명 (기본: {DEFAULT_PROFILE})")
    parser.add_argument("--serial", default=None, help="MFA 디바이스 ARN (미지정 시 자동 조회)")
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION_SECONDS,
        help=f"세션 유효 기간(초). 기본 {DEFAULT_DURATION_SECONDS}",
    )
    args = parser.parse_args()

    try:
        serial = args.serial or get_mfa_serial()
    except (ClientError, RuntimeError) as e:
        print(f"MFA 디바이스 조회 실패: {e}", file=sys.stderr)
        return 1

    try:
        creds = issue_session(args.token_code, serial, args.duration)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "AccessDenied":
            print("MFA 코드가 올바르지 않거나 이미 사용되었습니다. 새 코드로 다시 시도하세요.", file=sys.stderr)
        else:
            print(f"세션 토큰 발급 실패 ({code}): {e}", file=sys.stderr)
        return 1

    expiry = creds["Expiration"].astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    if args.export:
        # eval 로 바로 적용할 수 있도록 export 구문만 stdout 에 출력
        print(f"export AWS_ACCESS_KEY_ID={creds['AccessKeyId']}")
        print(f"export AWS_SECRET_ACCESS_KEY={creds['SecretAccessKey']}")
        print(f"export AWS_SESSION_TOKEN={creds['SessionToken']}")
        print(f"[성공] 세션 유효 기간: {expiry} 까지", file=sys.stderr)
        return 0

    write_profile(creds, args.profile)
    print(f"[성공] '{args.profile}' 프로필에 저장했습니다. 유효 기간: {expiry} 까지")
    print()
    print("이제 아래 명령으로 서버를 실행하세요 (터미널 상관없이 동작):")
    print(f"  USE_BEDROCK=true AWS_PROFILE={args.profile} uv run uvicorn app.librarian.server:app --reload")
    return 0


if __name__ == "__main__":
    sys.exit(main())
