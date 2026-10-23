"""开发/生产启动入口： python run.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT,
                reload=os.getenv("CERTD_RELOAD") == "1", log_level="info")
