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
"""脚本管理：MaaEnd 路由与端点专用模型。"""

from pathlib import Path
from typing import (
    List,
    Literal,
    Optional,
)

from fastapi import APIRouter, Body
from pydantic import (
    BaseModel,
    Field,
)

from app.core import Config
from app.models.schema import (
    ComboBoxItem,
    OutBase,
    ScriptDeleteIn,
)
from app.utils import get_logger


class MaaEndLogBundleIn(BaseModel):
    outputDirectory: Path | None = Field(
        default=None, description="手动保存目录；未提供时只查询现有归档"
    )


class MaaEndLogBundleOut(OutBase):
    directories: list[str] = Field(
        default_factory=list, description="各安装最新日志包所在目录"
    )
    needsDirectory: bool = Field(
        default=False, description="是否需要选择目录保存当前日志"
    )
    incompleteCount: int = Field(default=0, description="未能保存的文件数")


class MaaEndEssenceTargetGroup(BaseModel):
    value: str = Field(..., description="武器类型标识")
    label: str = Field(..., description="武器类型展示名")
    options: List[ComboBoxItem] = Field(..., description="该类型可选武器")


class MaaEndAutoCollectGroup(BaseModel):
    value: str = Field(..., description="上游路线选项名")
    label: str = Field(..., description="采集分类展示名")
    region: str = Field(..., description="上游地区开关名，旧版为空")
    regionLabel: str = Field(..., description="地区展示名")
    configKey: Literal["AutoCollectRoutes", "AutoCollectCommonRoutes"] = Field(
        ..., description="用户路线配置字段"
    )
    options: List[ComboBoxItem] = Field(..., description="该分类的动态路线")
    defaultCases: list[str] = Field(..., description="上游默认路线")


class MaaEndLauncherPathOut(OutBase):
    """MaaEnd 启动器路径识别结果（供前端自动识别与落盘）"""

    launcher_path: str = Field(
        ..., description="由游戏客户端路径识别到的启动器 Launcher.exe 完整路径"
    )


class MaaEndInventoryOptions(BaseModel):
    description: str = Field(..., description="上游库存目标填写说明")
    inputs: list[ComboBoxItem] = Field(..., description="上游库存目标输入字段")
    claimModes: list[ComboBoxItem] = Field(..., description="上游库存任务领取方式")


class MaaEndOptionsOut(OutBase):
    inventory: MaaEndInventoryOptions | None = Field(
        default=None, description="上游库存目标选项，旧版不支持时为空"
    )
    launchGameControllers: list[str] = Field(
        default_factory=list, description="支持 MaaEnd 原生启动的控制器"
    )
    gameSettingControllers: list[str] = Field(
        default_factory=list, description="支持独立游戏显示设置的控制器"
    )
    projectName: str = Field(default="mxu", description="MaaEnd 资源声明的项目名称")
    projectVersion: str = Field(default="", description="MaaEnd 资源声明的项目版本")
    autoCollectGroups: List[MaaEndAutoCollectGroup] = Field(
        default_factory=list, description="MaaEnd 自动采集地区与分类"
    )
    originalResolution: Optional[str] = Field(
        default=None, description="从游戏 Unity 注册表读取的原始分辨率"
    )
    originalDisplayType: Optional[Literal["Window", "Fullscreen"]] = Field(
        default=None, description="从游戏注册表读取的原始显示模式"
    )
    controllers: List[ComboBoxItem] = Field(..., description="MaaEnd 控制器选项")
    controllerTypes: dict[str, str] = Field(..., description="控制器协议类型映射")
    essenceLocations: List[ComboBoxItem] = Field(
        ..., description="MaaEnd 基质刷取地点选项"
    )
    essenceMenus: List[ComboBoxItem] = Field(..., description="MaaEnd 基质刷取模式选项")
    essenceTargetWeaponGroups: List[MaaEndEssenceTargetGroup] = Field(
        ..., description="MaaEnd 基质目标武器分组"
    )


router = APIRouter()
logger = get_logger("脚本管理 API")


@router.get(
    "/maaend/launcher-path",
    tags=["Get"],
    summary="从终末地客户端路径识别官方启动器路径",
    response_model=MaaEndLauncherPathOut,
    status_code=200,
)
async def get_maaend_launcher_path_api(scriptId: str) -> MaaEndLauncherPathOut:
    """按脚本的终末地客户端路径识别启动器 Launcher.exe（前端「自动识别」用）。

    只回答「在哪」：不改配置；识别不到时返回 400 与说明，由前端提示手动选择。
    """

    try:
        from app.task.MaaEnd import api_service as domain_api

        launcher_path = domain_api.resolve_launcher_path(scriptId)
        return MaaEndLauncherPathOut(
            code=200,
            status="success",
            message="",
            launcher_path=launcher_path.as_posix(),
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_maaend_launcher_path_api失败: {type(e).__name__}: {e}"
        )
        return MaaEndLauncherPathOut(
            code=(
                400
                if isinstance(e, (ValueError, KeyError, TypeError, FileNotFoundError))
                else 500
            ),
            status="error",
            # message 直接展示给用户，不带异常类名前缀（类名只进上面的日志）
            message=str(e),
            launcher_path="",
        )


@router.post(
    "/maaend/log-bundle",
    tags=["Action"],
    summary="打开已有 MaaEnd 日志包或保存当前日志",
    response_model=MaaEndLogBundleOut,
)
async def resolve_maaend_log_bundle(options: MaaEndLogBundleIn) -> MaaEndLogBundleOut:
    from app.task.MaaEnd import api_service as domain_api

    scripts = Config.ScriptConfig.values()
    try:
        result = await domain_api.resolve_log_bundle(
            scripts, output_directory=options.outputDirectory
        )
        return MaaEndLogBundleOut(
            directories=result.directories,
            needsDirectory=result.needs_directory,
            incompleteCount=result.incomplete_count,
        )
    except (OSError, ValueError) as error:
        return MaaEndLogBundleOut(code=500, status="error", message=str(error))


@router.post(
    "/maaend/options",
    tags=["Get"],
    summary="获取 MaaEnd 动态选项",
    response_model=MaaEndOptionsOut,
    status_code=200,
)
async def get_maaend_options(options: ScriptDeleteIn = Body(...)) -> MaaEndOptionsOut:
    try:
        data = await Config.get_maaend_options(options.scriptId)
        return MaaEndOptionsOut(
            launchGameControllers=data["launchGameControllers"],
            gameSettingControllers=data["gameSettingControllers"],
            projectName=data["projectName"],
            projectVersion=data["projectVersion"],
            inventory=data.get("inventory"),
            autoCollectGroups=[
                MaaEndAutoCollectGroup(**item)
                for item in data.get("autoCollectGroups", [])
            ],
            originalResolution=data.get("originalResolution"),
            originalDisplayType=data.get("originalDisplayType"),
            controllers=[ComboBoxItem(**item) for item in data["controllers"]],
            controllerTypes=data["controllerTypes"],
            essenceLocations=[
                ComboBoxItem(**item) for item in data["essenceLocations"]
            ],
            essenceMenus=[
                ComboBoxItem(**item) for item in data.get("essenceMenus", [])
            ],
            essenceTargetWeaponGroups=[
                MaaEndEssenceTargetGroup(
                    value=item["value"],
                    label=item["label"],
                    options=[ComboBoxItem(**option) for option in item["options"]],
                )
                for item in data.get("essenceTargetWeaponGroups", [])
            ],
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_maaend_options失败: {type(e).__name__}: {e}"
        )
        return MaaEndOptionsOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            controllers=[],
            controllerTypes={},
            essenceLocations=[],
            essenceMenus=[],
            essenceTargetWeaponGroups=[],
        )
