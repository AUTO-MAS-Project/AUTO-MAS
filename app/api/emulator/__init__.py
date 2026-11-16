"""模拟器配置与实例操作接口。"""

from fastapi import APIRouter

from .config import router as config_router
from .instances import router as instances_router

router = APIRouter()
router.include_router(config_router)
router.include_router(instances_router)
