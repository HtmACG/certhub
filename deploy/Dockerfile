# CertHub 生产镜像（用本地已构建好的 frontend/dist，服务器上不跑 Node）
#
# 构建：把 backend/、frontend/dist、本文件、docker-compose.yml 放到同一目录，
#      docker compose up -d --build
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CERTD_DATA_DIR=/app/backend/data \
    CERTD_PORT=8000 \
    CERTD_TZ=Asia/Shanghai \
    TZ=Asia/Shanghai

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        -r backend/requirements.txt

COPY backend/ backend/
COPY frontend-dist/ frontend/dist/

WORKDIR /app/backend
EXPOSE 8000
VOLUME ["/app/backend/data"]

HEALTHCHECK --interval=60s --timeout=8s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5).status==200 else 1)"

CMD ["python", "run.py"]
