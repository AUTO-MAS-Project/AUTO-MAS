#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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


from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, ValidationInfo

from app.config import (
    ConfigGroup,
    legacy,
)
from app.config.types import (
    SYSTEM_BLOCKED_DIRS,
    JsonDictString,
    JsonListString,
    normalize_path_input,
    path_policy,
)
from app.utils import EMULATOR_PATH_BOOK

from .base import DomainEntry


def normalize_emulator_manager(value: object, info: ValidationInfo) -> object:
    """复用模拟器管理器定位入口，将目录或快捷方式归一为主程序路径。"""
    value = normalize_path_input(value)
    if value is None:
        return None
    kind = info.data.get("Type", "general")
    if kind not in EMULATOR_PATH_BOOK:
        return value
    from app.utils import emulator as _utils_emulator

    return _utils_emulator.tools.find_emulator_manager_path(str(value), kind)


EmulatorManagerPath = Annotated[
    Path | None,
    path_policy(kind="file", must_exist=True, blocked_dirs=SYSTEM_BLOCKED_DIRS),
    BeforeValidator(normalize_emulator_manager),
]


class EmulatorConfig(DomainEntry):
    "模拟器配置"

    class InfoFields(ConfigGroup):
        Type: Annotated[
            Literal["general", "mumu", "ldplayer", "emulator2"],
            legacy(group="Data", name="Type"),
        ] = Field(default_factory=lambda: "general", description="模拟器类型")

        Baselines: JsonDictString = Field(
            default_factory=lambda: "{}",
            description="守卫的基准: {设备号: {字段: 值}}, 只记用户显式设过的字段",
        )

        BossKey: Annotated[JsonListString, legacy(group="Data", name="BossKey")] = (
            Field(default_factory=lambda: "[ ]", description="老板键快捷键配置")
        )

        ConfigGuard: bool = Field(
            default_factory=lambda: False,
            description="Emulator 2.0 的稳定模式：开着就把会干扰截图识别的模拟器功能压住, 启动实例前顺带确保一次, 这样新建的实例也会跟着进入安全状态。 关掉只是不再确保, **不会把那些项改回去**——不知道用户原本想要什么值。 Emulator 2.0 的配置守卫：以 MAS 存的这份设置为准, 启动前与关闭后各核验一次, 对不上就写回去。与旧雷电那套「开机拍快照关机还原」不是一回事, 见 utils/emulator2/guard.py",
        )

        ForceKillBeforeLaunch: bool = Field(
            default_factory=lambda: False,
            description="启动 MuMu 实例前先关闭已在运行的实例并强力清理残留进程 用于已有非管理员实例导致新实例无法以管理员身份启动的场景; 会关掉全部实例, 多开慎用",
        )

        ForceKillOnClose: bool = Field(
            default_factory=lambda: False, description="关闭 MuMu 时强力清理残留进程"
        )

        MaxWaitTime: Annotated[
            int,
            Field(ge=1, le=9999),
            legacy(group="Data", name="MaxWaitTime"),
        ] = Field(default_factory=lambda: 300, description="最大等待时间（秒）")

        Name: str = Field(default_factory=lambda: "新模拟器", description="模拟器名称")

        Path: EmulatorManagerPath = Field(default=None, description="模拟器路径")

        Paths: JsonListString = Field(
            default_factory=lambda: "[]",
            description='Emulator 2.0 纳管的模拟器路径列表 [{"pathId", "installPath", "alias", "type", "version"}]',
        )

        Slots: JsonListString = Field(
            default_factory=lambda: "[]",
            description='Emulator 2.0 的设备号槽位表 [{"slot", "pathId", "nativeIndex", "state": "active"|"tombstone"}] 槽位号在本配置内单调递增分配, 移除路径写墓碑, 号码永不复用',
        )

        StableMode: bool = Field(
            description="Emulator 2.0: 稳定模式是否开启", default_factory=lambda: False
        )

    Info: InfoFields = Field(default_factory=InfoFields)


__all__ = ["EmulatorConfig"]
