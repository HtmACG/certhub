@echo off
chcp 65001 >nul
setlocal

echo ==========================================
echo   CertHub 启动脚本
echo ==========================================

cd /d "%~dp0"

if not exist "backend\.venv" (
    echo [1/3] 创建 Python 虚拟环境 ...
    python -m venv backend\.venv
)

echo [2/3] 安装后端依赖 ...
backend\.venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt

if not exist "webui\node_modules" (
    echo [3/3] 安装前端依赖 ...
    cd webui
    call npm install || call pnpm install
    cd ..
)

echo [3/3] 构建前端并发布到 frontend\dist ...
cd webui
call npm run deploy
cd ..

echo 启动后端服务 http://127.0.0.1:8000
cd backend
.venv\Scripts\python.exe run.py
