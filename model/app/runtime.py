"""全局运行时资源与鉴权。

resources 在 main.py 的 lifespan 中完成初始化，各 router 通过本模块访问，
避免路由模块反向依赖 main.py。
"""
import os

import jwt
from fastapi import HTTPException

from app.utils.task_manager import AsyncTaskManager

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"

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
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
