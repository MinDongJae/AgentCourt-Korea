"""API Gateway HTTP API + Lambda Integration — Function URL propagation 우회.
빠른 대안: HTTP API는 보통 1~2분 propagation.
"""
import boto3, json

REGION = "ap-northeast-2"
LAMBDA_NAME = "${LAMBDA_NAME}"
ACCOUNT = "${AWS_ACCOUNT_ID}"
API_NAME = "aptbaechi-sentencing-api"

s = boto3.Session(profile_name="default", region_name=REGION)
apigw = s.client("apigatewayv2", region_name=REGION)
lam = s.client("lambda", region_name=REGION)

print("[1] HTTP API 생성")
api = apigw.create_api(
    Name=API_NAME,
    ProtocolType="HTTP",
    Target=f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{LAMBDA_NAME}",
    CorsConfiguration={
        "AllowOrigins": ["*"],
        "AllowMethods": ["*"],
        "AllowHeaders": ["*"],
        "MaxAge": 600,
    },
)
api_id = api["ApiId"]
api_endpoint = api["ApiEndpoint"]
print(f"   API ID: {api_id}")
print(f"   Endpoint: {api_endpoint}")

print("\n[2] Lambda 권한 부여 (apigateway invoke)")
try:
    lam.add_permission(
        FunctionName=LAMBDA_NAME,
        StatementId="AllowApiGatewayHTTP",
        Action="lambda:InvokeFunction",
        Principal="apigateway.amazonaws.com",
        SourceArn=f"arn:aws:execute-api:{REGION}:{ACCOUNT}:{api_id}/*/*",
    )
    print(f"   ✅ permission added")
except Exception as e:
    print(f"   ⚠️ {e}")

print(f"\n[3] 결과")
print(f"   API Endpoint: {api_endpoint}")
print(f"   호출 예: curl {api_endpoint}/api/health")

# 결과 저장
from pathlib import Path
ROOT = Path(__file__).parent.parent
(ROOT / "deploy" / "apigw_result.json").write_text(
    json.dumps({"api_id": api_id, "endpoint": api_endpoint}, indent=2),
    encoding="utf-8",
)
