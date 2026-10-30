#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team
#   This file is part of AUTO-MAS.
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#   Contact: DLmaster_361@163.com
"""MSS 用户页的只读扩展路由与端点模型。"""

from typing import List

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.models.schema import OutBase
from app.task.MSS.api_service import defense_status as mss_defense_status


class MssDefenseStatusIn(BaseModel):
    scriptId: str = Field(..., min_length=1, description="MSS 脚本 ID")
    userId: str = Field(..., min_length=1, description="用户 ID")


class MssDefenseStatusData(BaseModel):
    """个人版「灾变防线」这一期的状态：用户页拿它显示「本期未打 / 已打」。"""

    enabled: bool = Field(
        default=False,
        description="个人版总开关（Function.IfPersonalMss）开着吗；没开时用户页连这一块都不渲染",
    )
    period: str = Field(
        default="", description="当前这一期的开始时刻；取不到官网公告时为空"
    )
    known: bool = Field(
        default=False, description="这一期认得出来吗（取不到官网公告时为 false）"
    )
    done: bool = Field(default=False, description="这一期已经打过")
    armed: bool = Field(default=False, description="已经排进队列、在等这一轮的结果")
    failedDays: List[str] = Field(
        default_factory=list, description="这一期编排过但没跑成的日子"
    )
    givenUp: bool = Field(default=False, description="失败日攒够了，这一期不再自动编排")


class MssDefenseStatusOut(OutBase):
    data: MssDefenseStatusData = Field(default_factory=MssDefenseStatusData)


router = APIRouter()


@router.post(
    "/maafw/mss/defense-status",
    tags=["MaaFW"],
    summary="个人版「灾变防线」这一期的状态",
    response_model=MssDefenseStatusOut,
    status_code=200,
)
async def get_mss_defense_status(
    payload: MssDefenseStatusIn = Body(...),
) -> MssDefenseStatusOut:
    """MSS 用户页显示「本期灾变防线打了没」。只读，不改任何配置。

    「这一期」由后端按官网那一篇公告的开始时刻算，前端不复刻同一套口径。
    """

    data = await mss_defense_status(payload.scriptId, payload.userId)
    return MssDefenseStatusOut(data=MssDefenseStatusData(**data))
