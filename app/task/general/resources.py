#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

from app.config import ConfigEntry
from app.models.config import GeneralConfig
from app.models.task import ScriptTaskResources


def declare_task_resources(script: ConfigEntry) -> ScriptTaskResources:
    """声明运行期实际占用的目录与模拟器绑定。"""
    if not isinstance(script, GeneralConfig):
        raise TypeError("脚本配置类型错误")
    if not script.Game.Enabled or script.Game.Type != "Emulator":
        return ScriptTaskResources()
    return ScriptTaskResources(
        emulator=(script.Game.EmulatorId, script.Game.EmulatorIndex)
    )
