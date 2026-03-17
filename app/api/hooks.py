#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""Hook 管理 API。"""

from __future__ import annotations

from fastapi import APIRouter, Body

from app.core import Config
from app.models.schema import HookMetaIn, HookMetaItem, HookMetaOut

router = APIRouter(prefix="/api/hooks", tags=["Hook管理"])


@router.post(
    "/meta",
    summary="读取 Hook 元数据（静态解析）",
    response_model=HookMetaOut,
    status_code=200,
)
async def get_hook_meta(payload: HookMetaIn = Body(...)) -> HookMetaOut:
    try:
        raw_items = await Config.get_hook_meta(payload.hookPaths)
        items = [HookMetaItem(**item) for item in raw_items]
    except Exception as e:
        return HookMetaOut(code=500, status="error", message=f"{type(e).__name__}: {e}")

    return HookMetaOut(data=items)
