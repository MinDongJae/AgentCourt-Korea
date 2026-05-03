"""CloudFront에 lambda OAC 복원 + ResponseHeadersPolicy 추가 (wedding 미러)."""
import boto3, json

DIST_ID = "E2HI2L8N0ZAIBZ"
LAMBDA_OAC_ID = "E1BNMY9XBHW9SK"
RESPONSE_HEADERS_POLICY = "5cc3b908-e619-4b99-88e5-2cf7f45965bd"  # wedding 동일

s = boto3.Session(profile_name="default", region_name="us-east-1")
cf = s.client("cloudfront", region_name="us-east-1")

resp = cf.get_distribution_config(Id=DIST_ID)
etag = resp["ETag"]
config = resp["DistributionConfig"]

for origin in config["Origins"]["Items"]:
    if origin["Id"] == "lambda-api":
        origin["OriginAccessControlId"] = LAMBDA_OAC_ID
        print(f"lambda OAC restored: {LAMBDA_OAC_ID}")

for behavior in config["CacheBehaviors"]["Items"]:
    if behavior.get("PathPattern") == "/api/*":
        behavior["ResponseHeadersPolicyId"] = RESPONSE_HEADERS_POLICY
        print(f"ResponseHeadersPolicyId set: {RESPONSE_HEADERS_POLICY}")

resp = cf.update_distribution(Id=DIST_ID, IfMatch=etag, DistributionConfig=config)
print(f"updated, status: {resp['Distribution']['Status']}")
