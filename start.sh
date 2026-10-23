#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "=========================================="
echo "  CertHub 启动脚本"
echo "=========================================="

if [ ! -d "backend/.venv" ]; then
  echo "[1/4] 创建 Python 虚拟环境 ..."
  python3 -m venv backend/.venv
fi

echo "[2/4] 安装后端依赖 ..."
backend/.venv/bin/python -m pip install -q -r backend/requirements.txt

if [ ! -d "frontend/node_modules" ]; then
  echo "[3/4] 安装前端依赖 ..."
  (cd frontend && (pnpm install || npm install --legacy-peer-deps))
fi

if [ ! -f "frontend/dist/index.html" ]; then
  echo "[4/4] 构建前端 ..."
  (cd frontend && (pnpm build || npm run build))
else
  echo "[4/4] 前端产物已存在，跳过构建（如需重建请删除 frontend/dist）"
fi

echo "启动后端服务 http://127.0.0.1:8000"
cd backend && .venv/bin/python run.py
