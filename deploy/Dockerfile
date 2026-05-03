FROM public.ecr.aws/lambda/python:3.11

# 작업 디렉토리 (Lambda base 이미지에 시스템 패키지 추가 불필요)
WORKDIR ${LAMBDA_TASK_ROOT}

# 의존성 (slim — Lambda Lambda 컨테이너 한계 250MB unpacked)
COPY deploy/requirements-lambda.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && \
    rm -rf /tmp/* /root/.cache

# 코드
COPY core/ ${LAMBDA_TASK_ROOT}/core/
COPY mcp_law/ ${LAMBDA_TASK_ROOT}/mcp_law/
COPY web/ ${LAMBDA_TASK_ROOT}/web/

# 데이터 (양형기준 청크 + FAISS 인덱스만 — embeddings.npy는 빌드 시점만 필요, 런타임 불필요)
COPY data/sentencing_chunks.json ${LAMBDA_TASK_ROOT}/data/
COPY data/faiss_index.bin ${LAMBDA_TASK_ROOT}/data/
COPY data/index_meta.json ${LAMBDA_TASK_ROOT}/data/
COPY data/mock_fixtures/ ${LAMBDA_TASK_ROOT}/data/mock_fixtures/

# 환경변수 기본값
ENV INDEX_DIR=/var/task/data
ENV LAW_API_MODE=real

# Lambda handler
COPY deploy/lambda_handler.py ${LAMBDA_TASK_ROOT}/

CMD ["lambda_handler.handler"]
