# ---------- 前端构建（webui：React + Vite） ----------
FROM node:22-alpine AS web
WORKDIR /app/webui
COPY webui/package.json webui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY webui/ ./
RUN npm run build

# ---------- 后端运行 ----------
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    CERTD_DATA_DIR=/app/backend/data \
    CERTD_PORT=8000

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
# 后端从 frontend/dist 托管静态资源：把 webui 的构建产物放到这个目录
COPY --from=web /app/webui/dist frontend/dist

WORKDIR /app/backend
EXPOSE 8000
VOLUME ["/app/backend/data"]
CMD ["python", "run.py"]
