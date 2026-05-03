"""CloudFront 배포 생성 — wedding 패턴 미러링.
- Origin 1: S3 (정적 페이지)
- Origin 2: Lambda Function URL (api/*)
- ACM 인증서 + Alternate domain: sentencing.aptbaechi.com
- AuthType IAM + OAC SigV4
"""
import json, time, sys
import boto3
from pathlib import Path

ROOT = Path(__file__).parent.parent
ACCOUNT = "${AWS_ACCOUNT_ID}"
REGION = "ap-northeast-2"
PROFILE = "default"

DOMAIN = "sentencing.aptbaechi.com"
ACM_ARN = "arn:aws:acm:us-east-1:${AWS_ACCOUNT_ID}:certificate/76901b13-37f3-49d0-b087-9de0fbfdbbdd"
LAMBDA_NAME = "${LAMBDA_NAME}"
LAMBDA_FN_URL_DOMAIN = "d3ggaiw2ibw257jbzz2vdsbma40jwjwl.lambda-url.ap-northeast-2.on.aws"
S3_BUCKET = "aptbaechi-sentencing-frontend"
S3_DOMAIN = f"{S3_BUCKET}.s3.{REGION}.amazonaws.com"

s = boto3.Session(profile_name=PROFILE, region_name=REGION)
lam = s.client("lambda")
cf = s.client("cloudfront", region_name="us-east-1")  # CF는 global
s3 = s.client("s3")

print("=" * 60)
print("CloudFront 배포 생성")
print("=" * 60)

# 0. ACM 상태 재확인
acm = s.client("acm", region_name="us-east-1")
acm_status = acm.describe_certificate(CertificateArn=ACM_ARN)["Certificate"]["Status"]
print(f"\n[0] ACM 상태: {acm_status}")
if acm_status != "ISSUED":
    print(f"   ⚠️ ACM 아직 PENDING_VALIDATION — CF는 PENDING 상태로 만들고, ISSUED 후 CF 자동 활성화")

# 1. Lambda Function URL을 IAM 모드로 변경 + CORS
print(f"\n[1] Lambda Function URL → AWS_IAM 모드 + CORS")
try:
    lam.update_function_url_config(
        FunctionName=LAMBDA_NAME,
        AuthType="AWS_IAM",
        Cors={"AllowOrigins": ["*"], "AllowMethods": ["GET","POST"], "AllowHeaders": ["*"], "MaxAge": 86400},
        InvokeMode="BUFFERED",
    )
    print(f"   ✅ AWS_IAM 모드로 변경")
except Exception as e:
    print(f"   ⚠️ {e}")

# 2. 기존 Public 정책 삭제 (wedding 패턴 따름)
print(f"\n[2] Public 정책 삭제 (CF OAC만 허용)")
try:
    lam.remove_permission(
        FunctionName=LAMBDA_NAME,
        StatementId="AllowFunctionUrlInvoke",
    )
    print(f"   ✅ Public 정책 제거")
except Exception as e:
    print(f"   ⚠️ {e} (이미 없음)")

# 3. S3 OAC 정책 — CF가 S3 읽기
print(f"\n[3] S3 bucket policy — CF OAC 허용 (CF 생성 후 갱신)")
# CF 생성 후 distribution ARN으로 갱신 예정

# 4. CloudFront OAC (Origin Access Control) 생성 — idempotent
print(f"\n[4] CloudFront OAC 생성 / 재사용")

def _ensure_oac(name: str, origin_type: str, desc: str) -> str:
    # 기존 OAC 검색
    paginator = cf.get_paginator("list_origin_access_controls")
    for page in paginator.paginate():
        for item in page.get("OriginAccessControlList", {}).get("Items", []):
            if item["Name"] == name:
                print(f"   ↺ 재사용 {name}: {item['Id']}")
                return item["Id"]
    # 없으면 생성
    resp = cf.create_origin_access_control(
        OriginAccessControlConfig={
            "Name": name,
            "Description": desc,
            "SigningProtocol": "sigv4",
            "SigningBehavior": "always",
            "OriginAccessControlOriginType": origin_type,
        }
    )
    oid = resp["OriginAccessControl"]["Id"]
    print(f"   ✅ 생성 {name}: {oid}")
    return oid

s3_oac_id = _ensure_oac(f"{LAMBDA_NAME}-oac-s3", "s3", "OAC for sentencing S3")
lam_oac_id = _ensure_oac(f"{LAMBDA_NAME}-oac-lambda", "lambda", "OAC for sentencing Lambda Function URL")

# 5. CloudFront 배포 생성
print(f"\n[5] CloudFront 배포 생성")
caller_ref = f"sentencing-{int(time.time())}"
dist_config = {
    "CallerReference": caller_ref,
    "Comment": "aptbaechi sentencing — RAG 양형기준 검색 어시스턴트",
    "Enabled": True,
    "PriceClass": "PriceClass_200",  # asia + us
    "Aliases": {"Quantity": 1, "Items": [DOMAIN]},
    "ViewerCertificate": {
        "ACMCertificateArn": ACM_ARN,
        "SSLSupportMethod": "sni-only",
        "MinimumProtocolVersion": "TLSv1.2_2021",
    },
    "Origins": {
        "Quantity": 2,
        "Items": [
            {
                "Id": "s3-frontend",
                "DomainName": S3_DOMAIN,
                "OriginAccessControlId": s3_oac_id,
                "S3OriginConfig": {"OriginAccessIdentity": ""},
            },
            {
                "Id": "lambda-api",
                "DomainName": LAMBDA_FN_URL_DOMAIN,
                "OriginAccessControlId": lam_oac_id,
                "CustomOriginConfig": {
                    "HTTPPort": 80,
                    "HTTPSPort": 443,
                    "OriginProtocolPolicy": "https-only",
                    "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]},
                    "OriginReadTimeout": 60,
                    "OriginKeepaliveTimeout": 5,
                },
            },
        ],
    },
    "DefaultCacheBehavior": {
        "TargetOriginId": "s3-frontend",
        "ViewerProtocolPolicy": "redirect-to-https",
        "AllowedMethods": {
            "Quantity": 2,
            "Items": ["GET", "HEAD"],
            "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]},
        },
        "Compress": True,
        # CachingOptimized managed policy
        "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",
    },
    "CacheBehaviors": {
        "Quantity": 1,
        "Items": [
            {
                "PathPattern": "/api/*",
                "TargetOriginId": "lambda-api",
                "ViewerProtocolPolicy": "redirect-to-https",
                "AllowedMethods": {
                    "Quantity": 7,
                    "Items": ["GET","HEAD","OPTIONS","PUT","POST","PATCH","DELETE"],
                    "CachedMethods": {"Quantity": 2, "Items": ["GET","HEAD"]},
                },
                "Compress": True,
                # CachingDisabled
                "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
                # AllViewerExceptHostHeader (Lambda Function URL은 host 헤더 필터)
                "OriginRequestPolicyId": "b689b0a8-53d0-40ab-baf2-68738e2966ac",
            }
        ],
    },
    "DefaultRootObject": "index.html",
    "CustomErrorResponses": {
        "Quantity": 1,
        "Items": [
            {"ErrorCode": 404, "ResponsePagePath": "/index.html", "ResponseCode": "200", "ErrorCachingMinTTL": 60},
        ],
    },
    "HttpVersion": "http2and3",
    "IsIPV6Enabled": True,
}

try:
    create_resp = cf.create_distribution(DistributionConfig=dist_config)
    dist = create_resp["Distribution"]
    dist_id = dist["Id"]
    cf_domain = dist["DomainName"]
    print(f"   ✅ CF 생성 완료")
    print(f"      Distribution ID: {dist_id}")
    print(f"      CF 도메인:       {cf_domain}")
    print(f"      Aliases:         {DOMAIN}")
except Exception as e:
    print(f"   ❌ {e}")
    raise

# 6. S3 bucket policy — CF OAC 허용
print(f"\n[6] S3 bucket policy — CF OAC")
s3_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowCloudFrontServicePrincipal",
            "Effect": "Allow",
            "Principal": {"Service": "cloudfront.amazonaws.com"},
            "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{S3_BUCKET}/*",
            "Condition": {"StringEquals": {"AWS:SourceArn": f"arn:aws:cloudfront::{ACCOUNT}:distribution/{dist_id}"}},
        }
    ],
}
try:
    s3.put_bucket_policy(Bucket=S3_BUCKET, Policy=json.dumps(s3_policy))
    print(f"   ✅ S3 bucket policy 설정")
except Exception as e:
    print(f"   ⚠️ {e}")

# 7. Lambda OAC 정책 — wedding 패턴: InvokeFunctionUrl + InvokeFunction 둘 다 필요
print(f"\n[7] Lambda OAC 정책 (InvokeFunctionUrl + InvokeFunction)")
for sid, action in [
    ("AllowCloudFrontOAC", "lambda:InvokeFunctionUrl"),
    ("CloudFrontInvokeFunction", "lambda:InvokeFunction"),
]:
    try:
        lam.add_permission(
            FunctionName=LAMBDA_NAME,
            StatementId=sid,
            Action=action,
            Principal="cloudfront.amazonaws.com",
            SourceArn=f"arn:aws:cloudfront::{ACCOUNT}:distribution/{dist_id}",
        )
        print(f"   ✅ {sid} ({action})")
    except Exception as e:
        print(f"   ⚠️ {sid}: {e}")

# 8. 결과
print(f"\n{'='*60}")
print(f"✅ CloudFront 배포 완료")
print(f"{'='*60}")
print(f"\nDistribution ID: {dist_id}")
print(f"CF 도메인:       https://{cf_domain}")
print(f"Custom 도메인:   https://{DOMAIN} (가비아 CNAME 등록 필요)")
print(f"\n다음 가비아 CNAME:")
print(f"  호스트:  sentencing")
print(f"  타입:    CNAME")
print(f"  값:      {cf_domain}")

# 결과 저장
(ROOT / "deploy" / "cf_result.json").write_text(json.dumps({
    "distribution_id": dist_id,
    "cf_domain": cf_domain,
    "alias": DOMAIN,
    "s3_oac_id": s3_oac_id,
    "lambda_oac_id": lam_oac_id,
}, indent=2), encoding="utf-8")
print(f"\n💾 결과: deploy/cf_result.json")
