"""Lambda handler — Mangum으로 FastAPI 래핑.

배포 후 호출 경로:
  CloudFront → /api/* → Lambda Function URL → Mangum → FastAPI
  CloudFront → /* → S3 (정적 페이지)

따라서 본 Lambda는 /api/health, /api/analyze, /api/sample-cases만 처리.
"""
from __future__ import annotations
import sys
import os
from pathlib import Path

# 작업 디렉토리 sys.path 추가
sys.path.insert(0, "/var/task")

os.environ.setdefault("INDEX_DIR", "/var/task/data")
os.environ.setdefault("LAW_API_MODE", "real")

# FastAPI 앱 import (web/app.py에서 정의)
import importlib.util
spec = importlib.util.spec_from_file_location("web_app", "/var/task/web/app.py")
web_app_module = importlib.util.module_from_spec(spec)

# uvicorn.run() 부분이 import 시 실행 안 되게 __main__ 우회
_original_name = "__main__"
spec.loader.exec_module(web_app_module)

app = web_app_module.app

# Mangum 어댑터 — Lambda Function URL 모드
from mangum import Mangum
handler = Mangum(app, lifespan="off")
