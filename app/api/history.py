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

from fastapi import APIRouter, Body

from app.core.history import history_store
from app.models.schema import (
    HistoryData,
    HistoryDataGetIn,
    HistoryDataGetOut,
    HistorySearchIn,
    HistorySearchOut,
)

router = APIRouter(prefix="/api/history", tags=["历史记录"])


def _history_data(raw: dict[str, object]) -> HistoryData:
    """Normalize persisted history while exposing known plugin statistics."""
    payload = dict(raw)
    statistics = payload.get("data")
    if isinstance(statistics, dict):
        for key in (
            "recruit_statistics",
            "drop_statistics",
            "matrix_statistics",
            "pull_count_statistics",
        ):
            if key in statistics:
                payload[key] = statistics[key]
    return HistoryData.model_validate(payload)


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
                username: _history_data(info)
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
        data = _history_data(detail)
    except Exception as e:
        return HistoryDataGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=HistoryData(),
        )
    return HistoryDataGetOut(data=data)
