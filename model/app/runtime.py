"""全局运行时资源与鉴权。

resources 在 main.py 的 lifespan 中完成初始化，各 router 通过本模块访问，
避免路由模块反向依赖 main.py。
"""
import os

from dotenv import load_dotenv

# 宝塔等生产环境显式配置的 SECRET_KEY 优先于项目目录中的 .env。
load_dotenv(override=False)

import jwt
from fastapi import HTTPException

from app.utils.task_manager import AsyncTaskManager

# 与 Java 后端 application-prod.yml 的无环境变量回退值保持一致（HS256 要求至少 32 字节）。
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here-please-change-this")
# HS512 用于兼容升级窗口期（jjwt 0.13 曾按 512 位密钥自动签发 HS512）的历史令牌，新令牌统一为 HS256
ALGORITHMS = ["HS256", "HS512"]

resources = {
    "model": None,
    "naming_model": None,
    "executor": None,
    "context_summary": None,
    "vision_service": None,
    "llm_turbo": None,
    "learning_assistant": None,
    "task_manager": AsyncTaskManager(),
}


def verify_token(token: str):
    try:
        jwt.decode(token, SECRET_KEY, algorithms=ALGORITHMS)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
