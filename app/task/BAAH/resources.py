#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

from app.config import ConfigEntry
from app.models.config import BAAHConfig
from app.models.task import ScriptTaskResources


def declare_task_resources(script: ConfigEntry) -> ScriptTaskResources:
    """声明运行期实际占用的目录与模拟器绑定。"""
    if not isinstance(script, BAAHConfig):
        raise TypeError("脚本配置类型错误")
    return ScriptTaskResources(emulator=(script.Emulator.Id, script.Emulator.Index))
