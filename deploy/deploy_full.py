"""전체 배포 자동화 — wedding 패턴 미러링.

순서:
1. ECR push (Docker 이미지)
2. Lambda 함수 생성/갱신 + 환경변수
3. Lambda Function URL 생성
4. S3 frontend 업로드
5. CloudFront 배포 생성 (또는 갱신)
6. ACM 인증서 (us-east-1) 신청 + DNS validation 안내
7. 가비아 DNS CNAME 안내

전제: docker build ${LAMBDA_NAME}:v1 완료된 상태
"""
from __future__ import annotations
import sys
import json
import time
import subprocess
import os
import mimetypes
from pathlib import Path

import boto3

ROOT = Path(__file__).parent.parent
ACCOUNT = "${AWS_ACCOUNT_ID}"
REGION = "ap-northeast-2"
PROFILE = "default"

NAME = "${LAMBDA_NAME}"
FRONT_BUCKET = "aptbaechi-sentencing-frontend"
ECR_URI = f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{NAME}"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/aptbaechi-sentencing-lambda-role"
DOMAIN = "sentencing.aptbaechi.com"

s = boto3.Session(profile_name=PROFILE, region_name=REGION)
lam = s.client("lambda")
s3 = s.client("s3")
cf = s.client("cloudfront")

LOG = ROOT / "deploy" / "deploy_log.txt"
log_lines = []
def log(s_):
    print(s_, flush=True)
    log_lines.append(str(s_))
    LOG.write_text("\n".join(log_lines), encoding="utf-8")


# .env 로드 — Lambda 환경변수로 사용
env_vars = {}
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env_vars[k.strip()] = v.strip()
# Lambda 컨테이너 내부 경로
env_vars["INDEX_DIR"] = "/var/task/data"
env_vars["LAW_API_MODE"] = "real"


def step(num, title, fn):
    log(f"\n{'='*60}\n[{num}] {title}\n{'='*60}")
    try:
        return fn()
    except Exception as e:
        import traceback
        log(f"❌ {type(e).__name__}: {e}")
        log(traceback.format_exc()[:1500])
        return None


def step_ecr_push():
    """Docker tag + push v1 → ECR."""
    cmds = [
        ["docker", "tag", f"{NAME}:v1", f"{ECR_URI}:v1"],
        ["docker", "tag", f"{NAME}:v1", f"{ECR_URI}:latest"],
        ["docker", "push", f"{ECR_URI}:v1"],
        ["docker", "push", f"{ECR_URI}:latest"],
    ]
    for c in cmds:
        log(f"   $ {' '.join(c)}")
        r = subprocess.run(c, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=600)
        if r.returncode != 0:
            log(f"   FAIL: {r.stderr[:300]}")
            return False
    log("   ✅ ECR push 완료")
    return True


def step_lambda_create():
    """Lambda 함수 생성 또는 갱신."""
    try:
        existing = lam.get_function(FunctionName=NAME)
        log(f"   기존 Lambda 발견 — update mode (현재 ImageUri: {existing['Code']['ImageUri'][:80]}...)")
        r = lam.update_function_code(FunctionName=NAME, ImageUri=f"{ECR_URI}:v1", Publish=True)
        log(f"   updated: {r.get('Version')}")
        # 환경변수 갱신
        lam.update_function_configuration(
            FunctionName=NAME,
            Environment={"Variables": env_vars},
            Timeout=300,  # LLM 호출 ~36초 + 버퍼
            MemorySize=2048,
        )
    except lam.exceptions.ResourceNotFoundException:
        log(f"   신규 Lambda 생성")
        r = lam.create_function(
            FunctionName=NAME,
            PackageType="Image",
            Code={"ImageUri": f"{ECR_URI}:v1"},
            Role=ROLE_ARN,
            Timeout=300,
            MemorySize=2048,
            Environment={"Variables": env_vars},
            Architectures=["x86_64"],
        )
        log(f"   created: {r['FunctionArn']}")

    # LastUpdateStatus polling
    for i in range(60):
        time.sleep(5)
        cfg = lam.get_function_configuration(FunctionName=NAME)
        status = cfg.get("LastUpdateStatus")
        log(f"   ... {i*5}s LastUpdateStatus={status}")
        if status == "Successful":
            log(f"   ✅ Lambda active, sha={cfg.get('CodeSha256','')[:30]}...")
            break
        if status == "Failed":
            log(f"   ❌ FAIL: {cfg.get('LastUpdateStatusReason')}")
            return False
    return True


def step_lambda_url():
    """Function URL 생성 (없으면)."""
    try:
        r = lam.get_function_url_config(FunctionName=NAME)
        log(f"   기존 URL: {r['FunctionUrl']}")
        return r["FunctionUrl"]
    except lam.exceptions.ResourceNotFoundException:
        r = lam.create_function_url_config(
            FunctionName=NAME,
            AuthType="NONE",
            Cors={"AllowOrigins": ["*"], "AllowMethods": ["GET", "POST", "OPTIONS"], "AllowHeaders": ["*"], "MaxAge": 86400},
        )
        # public 권한 추가
        try:
            lam.add_permission(
                FunctionName=NAME,
                StatementId="AllowFunctionUrlInvoke",
                Action="lambda:InvokeFunctionUrl",
                Principal="*",
                FunctionUrlAuthType="NONE",
            )
        except Exception as e:
            log(f"   permission already exists: {e}")
        log(f"   ✅ URL 생성: {r['FunctionUrl']}")
        return r["FunctionUrl"]


def step_s3_upload():
    """web/templates/index.html + web/static/* → S3."""
    web = ROOT / "web"
    files = [
        (web / "templates" / "index.html", "index.html"),
        (web / "static" / "style.css", "static/style.css"),
        (web / "static" / "app.js", "static/app.js"),
    ]
    uploaded = 0
    for src, key in files:
        if not src.exists():
            log(f"   ⚠ skip {src} (없음)")
            continue
        ctype, _ = mimetypes.guess_type(src.name)
        if not ctype:
            ctype = "application/octet-stream"
        cache = "public, max-age=31536000, immutable" if "static/" in key else "no-cache"
        s3.upload_file(
            str(src), FRONT_BUCKET, key,
            ExtraArgs={"ContentType": ctype, "CacheControl": cache},
        )
        uploaded += 1
        log(f"   ↑ {key} ({src.stat().st_size:,} bytes)")
    log(f"   ✅ S3 upload: {uploaded}개")
    return uploaded > 0


def main():
    log(f"=== 본 출품작 배포 시작 — {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    log(f"Account: {ACCOUNT} ({PROFILE})")
    log(f"Region:  {REGION}")
    log(f"Name:    {NAME}")
    log(f"ECR:     {ECR_URI}")
    log(f"Domain:  {DOMAIN}")
    log(f"Env vars: {len(env_vars)}개 (.env에서 로드)")

    if not step("1", "ECR push", step_ecr_push):
        return 1

    if not step("2", "Lambda create/update", step_lambda_create):
        return 2

    fn_url = step("3", "Lambda Function URL", step_lambda_url)
    if not fn_url:
        return 3

    if not step("4", "S3 frontend upload", step_s3_upload):
        return 4

    log(f"\n{'='*60}")
    log("✅ 배포 단계 1~4 완료")
    log(f"{'='*60}")
    log(f"\nLambda Function URL: {fn_url}")
    log(f"S3 frontend bucket:  s3://{FRONT_BUCKET}/")
    log(f"\n다음 수동 단계:")
    log(f"  5. CloudFront 배포 생성 (S3 origin + Lambda Function URL behavior /api/*)")
    log(f"  6. ACM 인증서 us-east-1 신청 ({DOMAIN})")
    log(f"  7. 가비아 DNS CNAME 등록 ({DOMAIN} → CloudFront)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
