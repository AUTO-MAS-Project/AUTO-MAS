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

"""脚本管理路由与端点专用模型。"""

import uuid
from typing import (
    Dict,
    List,
    Literal,
    Optional,
    Union,
)

from fastapi import APIRouter, Body
from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

import app.models.config as _config_models
from app.config.wire import ConfigInput, ConfigPayload, config_contract
from app.core import Config
from app.core.game_calendar import SCRIPT_CALENDAR_GAMES
from app.models.schema import (
    OutBase,
    ScriptDeleteIn,
    UserInBase,
)
from app.utils import get_logger

BAAHConfig = ConfigPayload[_config_models.BAAHConfig]


BAAHConfigInput = ConfigInput[_config_models.BAAHConfig]


BetterGIConfig = ConfigPayload[_config_models.BetterGIConfig]


BetterGIConfigInput = ConfigInput[_config_models.BetterGIConfig]


GeneralConfig = ConfigPayload[_config_models.GeneralConfig]


GeneralConfigInput = ConfigInput[_config_models.GeneralConfig]


HSRConfig = ConfigPayload[_config_models.HSRConfig]


HSRConfigInput = ConfigInput[_config_models.HSRConfig]


M9AConfig = ConfigPayload[_config_models.M9AConfig]


M9AConfigInput = ConfigInput[_config_models.M9AConfig]


MSSConfig = ConfigPayload[_config_models.MSSConfig]


MSSConfigInput = ConfigInput[_config_models.MSSConfig]


MaaConfig = ConfigPayload[_config_models.MaaConfig]


MaaConfigInput = ConfigInput[_config_models.MaaConfig]


MaaEndConfig = ConfigPayload[_config_models.MaaEndConfig]


MaaEndConfigInput = ConfigInput[_config_models.MaaEndConfig]


MaaFWConfig = ConfigPayload[_config_models.MaaFWConfig]


MaaFWConfigInput = ConfigInput[_config_models.MaaFWConfig]


OkNteConfig = ConfigPayload[_config_models.OkNteConfig]


OkNteConfigInput = ConfigInput[_config_models.OkNteConfig]


OkwwConfig = ConfigPayload[_config_models.OkwwConfig]


OkwwConfigInput = ConfigInput[_config_models.OkwwConfig]


SrcConfig = ConfigPayload[_config_models.SrcConfig]


SrcConfigInput = ConfigInput[_config_models.SrcConfig]


WhimboxConfig = ConfigPayload[_config_models.WhimboxConfig]


WhimboxConfigInput = ConfigInput[_config_models.WhimboxConfig]


ZzzOdConfig = ConfigPayload[_config_models.ZzzOdConfig]


ZzzOdConfigInput = ConfigInput[_config_models.ZzzOdConfig]


class ScriptIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal[
        "MaaConfig",
        "GeneralConfig",
        "OkwwConfig",
        "OkNteConfig",
        "SrcConfig",
        "MaaEndConfig",
        "M9AConfig",
        "MaaFWConfig",
        "HSRConfig",
        "BetterGIConfig",
        "ZzzOdConfig",
        "BAAHConfig",
        "WhimboxConfig",
        "MSSConfig",
    ] = Field(..., description="配置类型")

    activityGame: str | None = Field(
        default=None, description="对应的游戏活动标识，无游戏归属时为空"
    )


class ScriptCreateIn(BaseModel):
    type: Literal[
        "MAA",
        "SRC",
        "General",
        "Okww",
        "OkNte",
        "MaaEnd",
        "M9A",
        "MaaFW",
        "HSR",
        "BetterGI",
        "ZzzOd",
        "BAAH",
        "Whimbox",
        "MSS",
    ] = Field(
        ...,
        description="脚本类型: MAA脚本, 通用脚本, OK-WW脚本, OK-NTE脚本, SRC脚本, MaaEnd脚本, M9A脚本, MaaFW脚本, HSR脚本, BetterGI脚本, ZZZ-OD脚本, BAAH脚本, 奇想盒脚本, MSS脚本",
    )
    scriptId: str | None = Field(
        default=None, description="直接从该脚本ID复制创建, 仅在复制创建时使用"
    )


class ScriptCreateOut(OutBase):
    scriptId: str = Field(..., description="新创建的脚本ID")
    data: Union[
        MaaConfig,
        SrcConfig,
        GeneralConfig,
        OkwwConfig,
        OkNteConfig,
        MaaEndConfig,
        M9AConfig,
        MaaFWConfig,
        HSRConfig,
        BetterGIConfig,
        ZzzOdConfig,
        BAAHConfig,
        WhimboxConfig,
        MSSConfig,
    ] = Field(..., description="脚本配置数据")


class ScriptGetIn(BaseModel):
    scriptId: Optional[str] = Field(
        default=None, description="脚本ID, 未携带时表示获取所有脚本数据"
    )


class ScriptGetOut(OutBase):
    index: List[ScriptIndexItem] = Field(..., description="脚本索引列表")
    data: Dict[
        str,
        Union[
            MaaConfig,
            SrcConfig,
            GeneralConfig,
            OkwwConfig,
            OkNteConfig,
            MaaEndConfig,
            M9AConfig,
            MaaFWConfig,
            HSRConfig,
            BetterGIConfig,
            ZzzOdConfig,
            BAAHConfig,
            WhimboxConfig,
            MSSConfig,
        ],
    ] = Field(..., description="脚本数据字典, key来自于index列表的uid")


class ScriptUpdateIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    data: Union[
        MaaConfigInput,
        SrcConfigInput,
        GeneralConfigInput,
        OkwwConfigInput,
        OkNteConfigInput,
        MaaEndConfigInput,
        M9AConfigInput,
        MaaFWConfigInput,
        HSRConfigInput,
        BetterGIConfigInput,
        ZzzOdConfigInput,
        BAAHConfigInput,
        WhimboxConfigInput,
        MSSConfigInput,
    ] = Field(..., description="脚本更新数据")

    @model_validator(mode="before")
    @classmethod
    def select_config_contract(cls, value):
        """按目标配置选输入类型，避免联合类型丢弃其他专项的同组字段。"""
        if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
            return value
        try:
            target = Config.ScriptConfig[value["scriptId"]]
        except (KeyError, ValueError, TypeError, AttributeError):
            return value
        payload = config_contract(type(target), mode="input").model_validate(
            value["data"]
        )
        return {**value, "data": payload}


class ScriptReorderIn(BaseModel):
    indexList: List[str] = Field(..., description="脚本ID列表, 按新顺序排列")


class ScriptConfigImportIn(UserInBase):
    userId: Optional[str] = Field(
        default=None, description="用户ID, 未携带时导入到脚本级配置文件"
    )


router = APIRouter()
logger = get_logger("脚本管理 API")


@router.post(
    "/add",
    tags=["Add"],
    summary="添加脚本",
    response_model=ScriptCreateOut,
    status_code=200,
)
async def add_script(script: ScriptCreateIn = Body(...)) -> ScriptCreateOut:

    try:
        uid, config = await Config.add_script(script.type, script.scriptId)
        data = ConfigPayload[type(config)](
            **config.model_dump(context={"audience": "api"})
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"add_script失败: {type(e).__name__}: {e}")
        return ScriptCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            scriptId="",
            data=GeneralConfig(**{}),
        )
    return ScriptCreateOut(scriptId=str(uid), data=data)


@router.post(
    "/get",
    tags=["Get"],
    summary="查询脚本配置信息",
    response_model=ScriptGetOut,
    status_code=200,
)
async def get_script(script: ScriptGetIn = Body(...)) -> ScriptGetOut:

    try:
        index, data = await Config.get_script(script.scriptId)
        activity_games = {
            config.__name__: game for config, game in SCRIPT_CALENDAR_GAMES.items()
        }
        index = [
            ScriptIndexItem(**item, activityGame=activity_games.get(item["type"]))
            for item in index
        ]
        data = {
            uid: ConfigPayload[type(Config.ScriptConfig[uuid.UUID(uid)])](**cfg)
            for uid, cfg in data.items()
        }
    except Exception as e:
        logger.opt(exception=True).warning(f"get_script失败: {type(e).__name__}: {e}")
        return ScriptGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return ScriptGetOut(index=index, data=data)


@router.post(
    "/update",
    tags=["Update"],
    summary="更新脚本配置信息",
    response_model=OutBase,
    status_code=200,
)
async def update_script(
    script: ScriptUpdateIn = Body(...),
) -> OutBase:

    try:
        data = script.data.model_dump(exclude_unset=True)
        # 设备绑定不受支持时拦截保存，避免先提交配置。
        refusal = await Config.update_script_settings(script.scriptId, data)
        if refusal:
            return OutBase(code=500, status="error", message=refusal)

    except Exception as e:
        logger.opt(exception=True).warning(
            f"update_script失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/delete",
    tags=["Delete"],
    summary="删除脚本",
    response_model=OutBase,
    status_code=200,
)
async def delete_script(script: ScriptDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_script(script.scriptId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"delete_script失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/order",
    tags=["Update"],
    summary="重新排序脚本",
    response_model=OutBase,
    status_code=200,
)
async def reorder_script(script: ScriptReorderIn = Body(...)) -> OutBase:

    try:
        await Config.reorder_script(script.indexList)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"reorder_script失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/config/import",
    tags=["Action"],
    summary="从脚本目录导入配置文件",
    response_model=OutBase,
    status_code=200,
)
async def import_script_config_file(
    config: ScriptConfigImportIn = Body(...),
) -> OutBase:

    try:
        await Config.import_script_config_file(config.scriptId, config.userId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"import_script_config_file失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase(message="脚本配置文件已导入")
