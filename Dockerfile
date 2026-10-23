# ---------- 前端构建 ----------
FROM node:20-alpine AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile --ignore-scripts
COPY frontend/ ./
RUN pnpm build

# ---------- 后端运行 ----------
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    CERTD_DATA_DIR=/app/backend/data \
    CERTD_PORT=8000

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY --from=web /app/frontend/dist frontend/dist

WORKDIR /app/backend
EXPOSE 8000
VOLUME ["/app/backend/data"]
CMD ["python", "run.py"]
