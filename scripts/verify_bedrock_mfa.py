"""MFA 세션으로 Bedrock 호출 가능 여부만 검증합니다 (자격증명은 출력하지 않음)."""

import sys

import boto3
from botocore.exceptions import ClientError

CANDIDATE_MODELS = [
    # 현재 기본값 (global 크로스리전 inference profile)
    ("ap-northeast-2", "global.anthropic.claude-haiku-4-5-20251001-v1:0"),
    ("ap-northeast-2", "global.anthropic.claude-sonnet-5"),
    ("ap-northeast-2", "apac.anthropic.claude-sonnet-5"),
    ("ap-northeast-2", "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"),
    ("ap-northeast-2", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
    ("ap-northeast-2", "anthropic.claude-3-5-sonnet-20240620-v1:0"),
    ("ap-northeast-2", "anthropic.claude-3-haiku-20240307-v1:0"),
]


def main() -> int:
    if len(sys.argv) < 2:
        print("사용법: python scripts/verify_bedrock_mfa.py <MFA코드>")
        return 1

    token_code = sys.argv[1]

    devices = boto3.client("iam").list_mfa_devices().get("MFADevices", [])
    if not devices:
        print("MFA 디바이스를 찾을 수 없습니다.")
        return 1
    serial = devices[0]["SerialNumber"]

    try:
        creds = boto3.client("sts").get_session_token(
            DurationSeconds=43200,
            SerialNumber=serial,
            TokenCode=token_code,
        )["Credentials"]
    except ClientError as e:
        print(f"세션 토큰 발급 실패: {e.response['Error']['Code']}")
        return 1

    print(f"세션 발급 성공 (만료: {creds['Expiration'].isoformat()})")
    print("-" * 60)

    session = boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )

    available = []
    for region, model_id in CANDIDATE_MODELS:
        client = session.client("bedrock-runtime", region_name=region)
        try:
            client.converse(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": "hi"}]}],
                inferenceConfig={"maxTokens": 8},
            )
            print(f"[OK]     {region} / {model_id}")
            available.append((region, model_id))
        except ClientError as e:
            print(f"[{e.response['Error']['Code']}] {region} / {model_id}")

    print("-" * 60)
    if available:
        region, model_id = available[0]
        print("사용 가능한 조합:")
        print(f"  DEFAULT_REGION   = {region}")
        print(f"  DEFAULT_MODEL_ID = {model_id}")
    else:
        print("사용 가능한 모델이 없습니다. 계정 정책 또는 모델 액세스를 확인하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
