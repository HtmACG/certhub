@echo off
chcp 65001 >nul
setlocal

echo ==========================================
echo   CertHub 启动脚本
echo ==========================================

cd /d "%~dp0"

if not exist "backend\.venv" (
    echo [1/4] 创建 Python 虚拟环境 ...
    python -m venv backend\.venv
)

echo [2/4] 安装后端依赖 ...
backend\.venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt

if not exist "frontend\node_modules" (
    echo [3/4] 安装前端依赖 ...
    cd frontend
    call pnpm install || call npm install --legacy-peer-deps
    cd ..
)

if not exist "frontend\dist\index.html" (
    echo [4/4] 构建前端 ...
    cd frontend
    call pnpm build || call npm run build
    cd ..
) else (
    echo [4/4] 前端产物已存在，跳过构建（如需重建请删除 frontend\dist）
)

echo 启动后端服务 http://127.0.0.1:8000
cd backend
.venv\Scripts\python.exe run.py
