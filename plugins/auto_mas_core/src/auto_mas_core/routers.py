from __future__ import annotations

from fastapi import APIRouter

from app.api.emulator import router as emulator_router
from app.api.plan import router as plan_router
from app.api.queue import router as queue_router
from app.api.script_types import router as script_types_router
from app.api.scripts import router as scripts_router
from app.api.scripts2 import router as scripts2_router


def get_routers() -> list[APIRouter]:
    return [
        emulator_router,
        scripts_router,
        scripts2_router,
        script_types_router,
        queue_router,
        plan_router,
    ]
