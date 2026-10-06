"""MAA 脚本配置。"""

from __future__ import annotations

from typing import Annotated, Literal

from annotated_types import Ge, Le
from pydantic import Field

from auto_mas_core import (
    ConfigCollection,
    ConfigGroup,
    FolderPath,
    ScriptEntry,
    collection,
    select,
)

from .choices import _TRANSITION
from .user import MaaUser

class MaaScript(ScriptEntry):
    """MAA 脚本配置。"""

    class Info(ScriptEntry.Info):
        name: str = Field(default="新 MAA 脚本", description="脚本名称")
        path: FolderPath = Field(default=None, description="MAA 安装目录")

    class Run(ConfigGroup):
        hard_time_limit: Annotated[int, Ge(1), Le(9999)] = Field(
            default=120, description="单账号运行总时限（分钟）"
        )
        task_transition_method: Annotated[Literal[*_TRANSITION], select()] = Field(
            default="ExitEmulator", description="任务切换方式"
        )
        proxy_times_limit: Annotated[int, Ge(0), Le(9999)] = Field(
            default=0, description="代理次数限制"
        )
        run_times_limit: Annotated[int, Ge(1), Le(9999)] = Field(
            default=3, description="运行次数限制"
        )
        annihilation_time_limit: Annotated[int, Ge(1), Le(9999)] = Field(
            default=40, description="剿灭时间限制（分钟）"
        )
        routine_time_limit: Annotated[int, Ge(1), Le(9999)] = Field(
            default=10, description="日常时间限制（分钟）"
        )
        if_check_game_update: bool = Field(
            default=False, description="是否在启动 MAA 前检查游戏更新"
        )
        if_auto_install_game_apk: bool = Field(
            default=False, description="是否允许自动下载并安装游戏安装包（仅官服）"
        )
        game_update_time_limit: Annotated[int, Ge(1), Le(9999)] = Field(
            default=60, description="游戏更新时间限制（分钟）"
        )

    info: Info = Field(default_factory=Info, description="脚本信息")
    run: Run = Field(default_factory=Run, description="运行")
    users: ConfigCollection[MaaUser] = collection(MaaUser)

