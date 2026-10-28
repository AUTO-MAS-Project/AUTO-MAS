#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

from app.config import ConfigEntry
from app.models.config import MaaConfig
from app.models.task import ScriptTaskResources


def declare_task_resources(script: ConfigEntry) -> ScriptTaskResources:
    """声明运行期实际占用的目录与模拟器绑定。"""
    if not isinstance(script, MaaConfig):
        raise TypeError("脚本配置类型错误")
    raw_path = str(script.Info.Path or "").strip()
    return ScriptTaskResources(
        root_paths=(Path(raw_path),) if raw_path else (),
        emulator=(script.Emulator.Id, script.Emulator.Index),
    )
