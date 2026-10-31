"""社区账号、签到与扫码登录接口。"""

from fastapi import APIRouter

from .accounts import router as accounts_router
from .miyoushe import router as miyoushe_router
from .skland import router as skland_router

router = APIRouter()
router.include_router(accounts_router)
router.include_router(miyoushe_router)
router.include_router(skland_router)
