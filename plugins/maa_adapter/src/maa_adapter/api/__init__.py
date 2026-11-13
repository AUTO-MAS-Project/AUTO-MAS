"""聚合插件专项路由，端点与专用模型按业务归组。"""

from fastapi import APIRouter

from . import copilot, credentials, cultivate, infrastructure, inventory

router = APIRouter()
for module in (infrastructure, inventory, cultivate, copilot, credentials):
    router.include_router(module.router)
