#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025 AUTO-MAS Team

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


from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Body

from app.core import Config
from app.models.schema import *

router = APIRouter(prefix="/api/history", tags=["历史记录"])


@router.post(
    "/search",
    summary="搜索历史记录总览信息",
    response_model=HistorySearchOut,
    status_code=200,
)
async def search_history(history: HistorySearchIn) -> HistorySearchOut:

    try:
        data = await Config.search_history(
            history.mode,
            datetime.strptime(history.start_date, "%Y-%m-%d").date(),
            datetime.strptime(history.end_date, "%Y-%m-%d").date(),
        )
        for date, users in data.items():
            for user, records in users.items():
                record = await Config.merge_statistic_info(records)
                record["index"] = [HistoryIndexItem(**_) for _ in record["index"]]
                record = HistoryData(**record)
                data[date][user] = record
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
    summary="从指定文件内获取历史记录数据",
    response_model=HistoryDataGetOut,
    status_code=200,
)
async def get_history_data(history: HistoryDataGetIn = Body(...)) -> HistoryDataGetOut:

    try:
        path = Path(history.jsonPath)
        data = await Config.merge_statistic_info([path])
        data.pop("index", None)
        data["log_content"] = path.with_suffix(".log").read_text(encoding="utf-8")
        data = HistoryData(**data)
    except Exception as e:
        return HistoryDataGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=HistoryData(**{}),
        )
    return HistoryDataGetOut(data=data)
