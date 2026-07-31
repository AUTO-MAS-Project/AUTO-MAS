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

"""历史记录 API：直接调用 ``history_store``。"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.core.history import history_store
from app.models.schema import OutBase

router = APIRouter(prefix="/api/history", tags=["历史记录"])


class HistoryIndexItem(BaseModel):
    date: str = Field(..., description="日期")
    status: Literal["DONE", "ERROR"] = Field(..., description="状态")
    jsonFile: str = Field(..., description="对应JSON文件")


class HistoryData(BaseModel):
    index: Optional[List[HistoryIndexItem]] = Field(
        default=None, description="历史记录索引列表"
    )
    data: Dict[str, Any] = Field(
        default_factory=dict, description="合并后的统计数据（2/3 层数字树）"
    )
    error_info: Optional[Dict[str, str]] = Field(
        default=None, description="报错信息, key为时间戳, value为错误描述"
    )
    log_content: Optional[str] = Field(
        default=None, description="日志内容, 仅在提取单条历史记录数据时返回"
    )
    status: Optional[str] = Field(default=None, description="单条记录状态")
    message: Optional[str] = Field(default=None, description="单条记录消息")
    type_key: Optional[str] = Field(default=None, description="脚本类型键")
    username: Optional[str] = Field(default=None, description="用户名")


class HistorySearchIn(BaseModel):
    mode: Literal["DAILY", "WEEKLY", "MONTHLY"] = Field(..., description="合并模式")
    start_date: str = Field(..., description="开始日期, 格式YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期, 格式YYYY-MM-DD")


class HistorySearchOut(OutBase):
    data: Dict[str, Dict[str, HistoryData]] = Field(
        default_factory=dict,
        description="历史记录索引, 格式为 { '日期': { '用户名': HistoryData } }",
    )


class HistoryDataGetIn(BaseModel):
    jsonPath: str = Field(..., description="需要提取数据的历史记录JSON文件")


class HistoryDataGetOut(OutBase):
    data: HistoryData = Field(default_factory=HistoryData, description="历史记录数据")


@router.post(
    "/search",
    tags=["Get"],
    summary="搜索历史记录总览信息",
    response_model=HistorySearchOut,
    status_code=200,
)
async def search_history(history: HistorySearchIn) -> HistorySearchOut:
    try:
        raw = history_store.search(
            start_date=history.start_date,
            end_date=history.end_date,
            mode=history.mode,
        )
        data = {
            date_key: {
                username: HistoryData.model_validate(info)
                for username, info in users.items()
            }
            for date_key, users in raw.items()
        }
    except Exception as e:
        return HistorySearchOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data={},
        )
    return HistorySearchOut(data=data)


@router.post(
    "/data",
    tags=["Get"],
    summary="从指定文件内获取历史记录数据",
    response_model=HistoryDataGetOut,
    status_code=200,
)
async def get_history_data(history: HistoryDataGetIn = Body(...)) -> HistoryDataGetOut:
    try:
        detail = history_store.get_detail(history.jsonPath)
        data = HistoryData.model_validate(detail)
    except Exception as e:
        return HistoryDataGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=HistoryData(),
        )
    return HistoryDataGetOut(data=data)
