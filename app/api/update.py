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


import asyncio
from contextlib import suppress
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends

from app.core import Config
from app.services import Updater
from app.contracts.common_contract import OutBase
from app.contracts.update_contract import UpdateCheckIn, UpdateCheckOut


router = APIRouter(prefix="/api/update", tags=["软件更新"])


QueryUpdateCheckIn = Annotated[UpdateCheckIn, Depends()]


def _track_temp_task(task: asyncio.Task[Any]) -> None:
    """统一跟踪临时后台任务，避免重复的列表维护代码。"""

    Config.temp_task.append(task)

    def _cleanup(done_task: asyncio.Task[Any]) -> None:
        with suppress(ValueError):
            Config.temp_task.remove(done_task)

    task.add_done_callback(_cleanup)


async def _build_update_check_out(version: UpdateCheckIn) -> UpdateCheckOut:
    if_need, latest_version, update_info = await Updater.check_update(
        current_version=version.current_version, if_force=version.if_force
    )
    return UpdateCheckOut(
        if_need_update=if_need, latest_version=latest_version, update_info=update_info
    )


@router.post(
    "/check",
    tags=["Get"],
    summary="检查更新",
    response_model=UpdateCheckOut,
)
async def check_update(version: UpdateCheckIn = Body(...)) -> UpdateCheckOut:
    return await _build_update_check_out(version)


@router.get(
    "/check",
    tags=["Get"],
    summary="按 REST 风格检查更新",
    response_model=UpdateCheckOut,
)
async def check_update_rest(version: QueryUpdateCheckIn) -> UpdateCheckOut:
    return await _build_update_check_out(version)


@router.post(
    "/download",
    tags=["Action"],
    summary="下载更新",
    response_model=OutBase,
)
async def download_update() -> OutBase:
    task = asyncio.create_task(Updater.download_update())
    _track_temp_task(task)
    return OutBase()


@router.post(
    "/install",
    tags=["Action"],
    summary="安装更新",
    response_model=OutBase,
)
async def install_update() -> OutBase:
    task = asyncio.create_task(Updater.install_update())
    _track_temp_task(task)
    return OutBase()
