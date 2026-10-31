#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import cast

from app.config import ConfigEntry
from app.models.config import MaaFWConfig
from app.models.script_contracts import ScriptEmulatorBinding
from app.models.task import ScriptTaskResources

EMULATOR_BINDING = ScriptEmulatorBinding(
    group="Emulator", id_field="Id", index_field="Index"
)
# 通用项目与全部 MaaFW 特调共用设备能力，不按控制器或特调缩小范围。
SUPPORTS_MOD_AVD = True


def declare_task_resources(script: ConfigEntry) -> ScriptTaskResources:
    """声明运行期实际占用的目录与模拟器绑定。"""
    script = cast(MaaFWConfig, script)
    # 运行期写入独立副本，来源目录相同不应阻止并发。
    return ScriptTaskResources(emulator=EMULATOR_BINDING.read(script))
