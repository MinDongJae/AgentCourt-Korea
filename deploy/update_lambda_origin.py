"""CF distribution의 lambda origin DomainName을 새 Function URL로 갱신."""
import boto3, sys

DIST_ID = "E2HI2L8N0ZAIBZ"
NEW_LAMBDA_URL_HOST = "tqykv4as5vlda5fgpuruphgsfe0gwysg.lambda-url.ap-northeast-2.on.aws"

s = boto3.Session(profile_name="default", region_name="us-east-1")
cf = s.client("cloudfront", region_name="us-east-1")

resp = cf.get_distribution_config(Id=DIST_ID)
etag = resp["ETag"]
config = resp["DistributionConfig"]

found = False
for origin in config["Origins"]["Items"]:
    if origin["Id"] == "lambda-api":
        old = origin["DomainName"]
        origin["DomainName"] = NEW_LAMBDA_URL_HOST
        # OAC 떼고 (NONE 모드)
        origin["OriginAccessControlId"] = ""
        print(f"lambda origin: {old} → {NEW_LAMBDA_URL_HOST}")
        found = True

if not found:
    print("ERROR: no lambda-api origin")
    sys.exit(1)

resp = cf.update_distribution(Id=DIST_ID, IfMatch=etag, DistributionConfig=config)
print(f"updated, status: {resp['Distribution']['Status']}")
