#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "=========================================="
echo "  CertHub 启动脚本"
echo "=========================================="

if [ ! -d "backend/.venv" ]; then
  echo "[1/3] 创建 Python 虚拟环境 ..."
  python3 -m venv backend/.venv
fi

echo "[2/3] 安装后端依赖 ..."
backend/.venv/bin/python -m pip install -q -r backend/requirements.txt

if [ ! -d "webui/node_modules" ]; then
  echo "[3/3] 安装前端依赖 ..."
  (cd webui && (npm install || pnpm install))
fi

echo "[3/3] 构建前端并发布到 frontend/dist ..."
(cd webui && npm run deploy)

echo "启动后端服务 http://127.0.0.1:8000"
cd backend && .venv/bin/python run.py
