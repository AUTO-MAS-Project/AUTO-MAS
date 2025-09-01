#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox

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


import os
from pathlib import Path
import shutil
from fastapi import APIRouter, Body

from app.core import Config
from app.services import System
from app.models.schema import *

router = APIRouter(prefix="/api/setting", tags=["全局设置"])


@router.post("/get", summary="查询配置", response_model=SettingGetOut, status_code=200)
async def get_scripts() -> SettingGetOut:
    """查询配置"""

    try:
        data = await Config.get_setting()
    except Exception as e:
        return SettingGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=GlobalConfig(**{}),
        )
    return SettingGetOut(data=GlobalConfig(**data))


@router.post("/update", summary="更新配置", response_model=OutBase, status_code=200)
async def update_script(script: SettingUpdateIn = Body(...)) -> OutBase:
    """更新配置"""

    try:
        data = script.data.model_dump(exclude_unset=True)
        await Config.update_setting(data)

        if data.get("Start", {}).get("IfSelfStart", None) is not None:
            await System.set_SelfStart()
        if data.get("Function", None) is not None:
            function = data["Function"]
            if function.get("IfAllowSleep", None) is not None:
                await System.set_Sleep()
            if function.get("IfSkipMumuSplashAds", None) is not None:
                MuMu_splash_ads_path = (
                    Path(os.getenv("APPDATA") or "")
                    / "Netease/MuMuPlayer-12.0/data/startupImage"
                )
                if Config.get("Function", "IfSkipMumuSplashAds"):
                    if MuMu_splash_ads_path.exists() and MuMu_splash_ads_path.is_dir():
                        shutil.rmtree(MuMu_splash_ads_path)
                    MuMu_splash_ads_path.touch()
                else:
                    if MuMu_splash_ads_path.exists() and MuMu_splash_ads_path.is_file():
                        MuMu_splash_ads_path.unlink()

    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
