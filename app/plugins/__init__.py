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

"""
插件框架 — 按模块逐步合入自动对轨主线。

当前模块：EventBus（事件总线）
  合入 PR：feat/plugin-eventbus
  回召状态：pyproject.toml 中无对应声明（EventBus 为框架基础设施，不涉及子插件）

后续模块会逐步在此包下扩展。
"""

from .event_bus import EventBus, EventDispatchError
from .event_contract import (
    EVENT_CONTRACT_VERSION,
    PluginEventNames,
    SCRIPT_LIFECYCLE_EVENTS,
    is_script_event,
    is_valid_source,
)

__all__ = [
    "EventBus",
    "EventDispatchError",
    "EVENT_CONTRACT_VERSION",
    "PluginEventNames",
    "SCRIPT_LIFECYCLE_EVENTS",
    "is_script_event",
    "is_valid_source",
]
