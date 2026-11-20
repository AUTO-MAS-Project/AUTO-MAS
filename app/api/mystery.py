#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""神秘入口 API 路由。

解锁状态由后端校验并持久化，前端只负责提交口令与展示结果；附属插件据此判断能否安装。
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core import Mystery
from app.models.schema import OutBase
from app.utils import get_logger

router = APIRouter(prefix="/api/mystery", tags=["神秘入口"])
logger = get_logger("神秘入口 API")


class MysteryStatusOut(OutBase):
    """神秘入口当前解锁状态。"""

    unlocked: bool = Field(default=False, description="当日是否已解锁")
    unlockedDate: str = Field(default="", description="上次解锁的北京日期")


class MysteryUnlockIn(BaseModel):
    """解锁请求。"""

    accessCode: str = Field(..., repr=False, description="当日访问口令")


class MysteryUnlockOut(MysteryStatusOut):
    """解锁结果。"""


class MysteryLockOut(MysteryStatusOut):
    """重新锁定结果。"""


@router.get("/status", summary="获取神秘入口解锁状态", response_model=MysteryStatusOut)
async def get_mystery_status() -> MysteryStatusOut:
    try:
        return MysteryStatusOut(
            unlocked=Mystery.is_unlocked(), unlockedDate=Mystery.unlocked_date()
        )
    except Exception as e:
        logger.exception("读取神秘入口解锁状态失败")
        return MysteryStatusOut(code=500, status="error", message=str(e))


@router.post("/unlock", summary="解锁神秘入口", response_model=MysteryUnlockOut)
async def unlock_mystery(body: MysteryUnlockIn) -> MysteryUnlockOut:
    try:
        date = await Mystery.unlock(body.accessCode)
    except ValueError as e:
        logger.warning(f"神秘入口解锁失败: {type(e).__name__}")
        return MysteryUnlockOut(code=400, status="error", message=str(e))
    except OSError as e:
        logger.error(f"神秘入口解锁状态写入失败: {e}")
        return MysteryUnlockOut(code=500, status="error", message=str(e))
    return MysteryUnlockOut(unlocked=True, unlockedDate=date, message="神秘入口已解锁")


@router.post("/lock", summary="重新锁定神秘入口", response_model=MysteryLockOut)
async def lock_mystery() -> MysteryLockOut:
    try:
        await Mystery.lock()
    except OSError as e:
        logger.error(f"神秘入口锁定失败: {e}")
        return MysteryLockOut(code=500, status="error", message=str(e))
    return MysteryLockOut(unlocked=False, unlockedDate="", message="神秘入口已锁定")
