"""CloudFront distribution에서 lambda origin의 OAC 제거.
Lambda Function URL을 NONE+Public으로 운영 (POST SigV4 이슈 회피).
"""
import boto3, json

DIST_ID = "E2HI2L8N0ZAIBZ"
s = boto3.Session(profile_name="default", region_name="us-east-1")
cf = s.client("cloudfront", region_name="us-east-1")

# 현재 config + ETag
resp = cf.get_distribution_config(Id=DIST_ID)
etag = resp["ETag"]
config = resp["DistributionConfig"]

# lambda-api origin에서 OAC 제거
changed = False
for origin in config["Origins"]["Items"]:
    if origin["Id"] == "lambda-api":
        if origin.get("OriginAccessControlId"):
            print(f"removing OAC from lambda-api: {origin['OriginAccessControlId']}")
            origin["OriginAccessControlId"] = ""
            changed = True

if not changed:
    print("nothing to change")
else:
    resp = cf.update_distribution(Id=DIST_ID, IfMatch=etag, DistributionConfig=config)
    print(f"✅ updated, new status: {resp['Distribution']['Status']}")
