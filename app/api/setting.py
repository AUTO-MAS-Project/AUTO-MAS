#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from fastapi import APIRouter, Body

from core import Config
from models.schema import *

router = APIRouter(prefix="/api/setting", tags=["全局设置"])


@router.post("/get", summary="查询配置", response_model=SettingGetOut, status_code=200)
async def get_scripts() -> SettingGetOut:
    """查询配置"""

    try:
        data = await Config.get_setting()
    except Exception as e:
        return SettingGetOut(code=500, status="error", message=str(e), data={})
    return SettingGetOut(data=data)


@router.post("/update", summary="更新配置", response_model=BaseOut, status_code=200)
async def update_script(script: SettingUpdateIn = Body(...)) -> BaseOut:
    """更新配置"""

    try:
        await Config.update_setting(script.data)
    except Exception as e:
        return BaseOut(code=500, status="error", message=str(e))
    return BaseOut()
