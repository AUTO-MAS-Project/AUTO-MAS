#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import cast

from app.config import ConfigEntry
from app.models.config import BAAHConfig
from app.models.script_contracts import ScriptEmulatorBinding
from app.models.task import ScriptTaskResources

EMULATOR_BINDING = ScriptEmulatorBinding(
    group="Emulator", id_field="Id", index_field="Index"
)


def declare_task_resources(script: ConfigEntry) -> ScriptTaskResources:
    """声明运行期实际占用的目录与模拟器绑定。"""
    script = cast(BAAHConfig, script)
    return ScriptTaskResources(emulator=EMULATOR_BINDING.read(script))
