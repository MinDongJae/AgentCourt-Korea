"""CF distribution의 lambda origin을 API Gateway로 전환."""
import boto3, sys

DIST_ID = "E2HI2L8N0ZAIBZ"
APIGW_HOST = "g10rxgc4yd.execute-api.ap-northeast-2.amazonaws.com"

s = boto3.Session(profile_name="default", region_name="us-east-1")
cf = s.client("cloudfront", region_name="us-east-1")

resp = cf.get_distribution_config(Id=DIST_ID)
etag = resp["ETag"]
config = resp["DistributionConfig"]

found = False
for origin in config["Origins"]["Items"]:
    if origin["Id"] == "lambda-api":
        old = origin["DomainName"]
        origin["DomainName"] = APIGW_HOST
        origin["OriginAccessControlId"] = ""  # API GW는 OAC 없음
        # API GW는 HTTPS-only on 443
        origin["CustomOriginConfig"] = {
            "HTTPPort": 80,
            "HTTPSPort": 443,
            "OriginProtocolPolicy": "https-only",
            "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]},
            "OriginReadTimeout": 60,
            "OriginKeepaliveTimeout": 5,
        }
        print(f"origin: {old} → {APIGW_HOST}")
        found = True

if not found:
    print("ERROR: no lambda-api origin")
    sys.exit(1)

resp = cf.update_distribution(Id=DIST_ID, IfMatch=etag, DistributionConfig=config)
print(f"updated, status: {resp['Distribution']['Status']}")
