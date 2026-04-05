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


from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Body
from pydantic import TypeAdapter

from app.core import Config
from app.api.common import RECOVERABLE_EXCEPTIONS, bind_api, error_out
from app.contracts.history_contract import (
    HistoryData,
    HistoryDataGetIn,
    HistoryDataGetOut,
    HistoryIndexItem,
    HistorySearchIn,
    HistorySearchOut,
)

router = APIRouter(prefix="/api/history", tags=["历史记录"])
api = bind_api(router)

HISTORY_INDEX_ADAPTER: TypeAdapter[list[HistoryIndexItem]] = TypeAdapter(
    list[HistoryIndexItem]
)


def _build_history_data(raw: dict[str, object]) -> HistoryData:
    data = dict(raw)
    index_data = data.get("index", [])
    data["index"] = []
    if isinstance(index_data, list):
        data["index"] = HISTORY_INDEX_ADAPTER.validate_python(index_data)
    return HistoryData.model_validate(data)


@api.post(
    "/search",
    tags=["Get"],
    summary="搜索历史记录总览信息",
    response_model=HistorySearchOut,
)
async def search_history(history: HistorySearchIn) -> HistorySearchOut:
    try:
        raw_data = await Config.search_history(
            history.mode,
            datetime.strptime(history.start_date, "%Y-%m-%d").date(),
            datetime.strptime(history.end_date, "%Y-%m-%d").date(),
        )
        data: dict[str, dict[str, HistoryData]] = {}
        for date, users in raw_data.items():
            current_users: dict[str, HistoryData] = {}
            for user, records in users.items():
                record = await Config.merge_statistic_info(records)
                current_users[user] = _build_history_data(record)
            data[date] = current_users
    except RECOVERABLE_EXCEPTIONS as e:
        return error_out(HistorySearchOut, e, data={})
    return HistorySearchOut(data=data)


@api.post(
    "/data",
    tags=["Get"],
    summary="从指定文件内获取历史记录数据",
    response_model=HistoryDataGetOut,
)
async def get_history_data(history: HistoryDataGetIn = Body(...)) -> HistoryDataGetOut:
    try:
        path = Path(history.jsonPath)
        raw_data = await Config.merge_statistic_info([path])
        raw_data.pop("index", None)
        raw_data["log_content"] = path.with_suffix(".log").read_text(encoding="utf-8")
        data = _build_history_data(raw_data)
    except RECOVERABLE_EXCEPTIONS as e:
        return error_out(HistoryDataGetOut, e, data=HistoryData())
    return HistoryDataGetOut(data=data)
