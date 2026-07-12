"""运维管理接口：配置热更新与报告模式查询。"""
from fastapi import APIRouter, HTTPException

from app.config.config_loader import (
    get_expert_manager,
    get_limits_manager,
    get_prompt_manager,
    get_report_manager,
    get_validation_manager,
)

router = APIRouter()


@router.post("/admin/reload_config")
async def reload_config():
    """配置热更新接口"""
    try:
        get_prompt_manager().reload()
        get_report_manager().reload()
        get_expert_manager().reload()
        get_validation_manager().reload()
        get_limits_manager().reload()
        return {"status": "ok", "message": "配置已热更新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/report_modes")
async def list_report_modes():
    """获取可用报告模式接口"""
    mgr = get_report_manager()
    modes = mgr.list_modes()
    return {
        "modes": [
            {"key": m, "name": mgr.get_template_name(m)}
            for m in modes
        ]
    }
