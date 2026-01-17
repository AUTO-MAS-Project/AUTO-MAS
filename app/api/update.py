#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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


import asyncio
from fastapi import APIRouter, Body

from app.core import Config
from app.services import Updater
from app.models.schema import *

router = APIRouter(prefix="/api/update", tags=["软件更新"])


@router.post(
    "/check",
    tags=["Get"],
    summary="检查更新",
    response_model=UpdateCheckOut,
    status_code=200,
)
async def check_update(version: UpdateCheckIn = Body(...)) -> UpdateCheckOut:

    try:
        if_need, latest_version, update_info = await Updater.check_update(
            current_version=version.current_version, if_force=version.if_force
        )
    except Exception as e:
        return UpdateCheckOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            if_need_update=False,
            latest_version="",
            update_info={},
        )
    return UpdateCheckOut(
        if_need_update=if_need, latest_version=latest_version, update_info=update_info
    )


@router.post(
    "/download",
    tags=["Action"],
    summary="下载更新",
    response_model=OutBase,
    status_code=200,
)
async def download_update() -> OutBase:

    try:
        task = asyncio.create_task(Updater.download_update())
        Config.temp_task.append(task)
        task.add_done_callback(lambda t: Config.temp_task.remove(t))
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/install",
    tags=["Action"],
    summary="安装更新",
    response_model=OutBase,
    status_code=200,
)
async def install_update() -> OutBase:

    try:
        task = asyncio.create_task(Updater.install_update())
        Config.temp_task.append(task)
        task.add_done_callback(lambda t: Config.temp_task.remove(t))
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
