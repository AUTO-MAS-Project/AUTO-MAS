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


"""主 WebSocket 消息协议

统一信封为 WSEnvelope {id, type, data}，前后端均按 id + type 路由。
消息类别常量与 frontend/src/services/websocket/types.ts 保持一致。
"""

from typing import Dict, Mapping, Optional

from pydantic import JsonValue, ValidationError

from app.models.schema import WSEnvelope
from app.utils.logger import get_logger

logger = get_logger("WS协议")


# ==================== 固定路由 ID ====================

ID_MAIN = "Main"
ID_TASK_MANAGER = "TaskManager"
ID_UPDATE = "Update"
ID_PLUGIN_SYSTEM = "PluginSystem"
ID_PLUGIN_MARKET = "PluginMarket"
ID_EMULATOR_MANAGER = "EmulatorManager"
ID_ARKNIGHTS_PC_TOOLKIT = "ArknightsPCToolkit"


# ==================== 消息类别（后端 → 前端） ====================

# 任务消息（id 为任务 UUID）
TASK_INFO_UPDATED = "task.info.updated"
TASK_LOG_UPDATED = "task.log.updated"
TASK_NOTICE = "task.notice"
TASK_COMPLETED = "task.completed"

# 任务创建通知（id=TaskManager）
TASK_CREATED = "task.created"

# 应用生命周期与电源（id=Main）
BACKEND_SHUTDOWN_READY = "backend.shutdown.ready"
FRONTEND_CLOSE_REQUESTED = "frontend.close.requested"
POWER_COUNTDOWN_UPDATED = "power.countdown.updated"
POWER_COUNTDOWN_CANCELLED = "power.countdown.cancelled"
POWER_SIGN_UPDATED = "power.sign.updated"

# 应用内弹窗（id=Main）
DIALOG_REQUEST = "dialog.request"
DIALOG_RESPONSE = "dialog.response"  # 前端 → 后端

# 更新下载（id=Update）
UPDATE_PROGRESS = "update.progress"
UPDATE_COMPLETED = "update.completed"
UPDATE_FAILED = "update.failed"
UPDATE_CANCELLED = "update.cancelled"

# 插件系统实时消息（id=PluginSystem）
PLUGIN_RUNTIME_UPDATED = "plugin.runtime.updated"
PLUGIN_SNAPSHOT_UPDATED = "plugin.snapshot.updated"
PLUGIN_HMR = "plugin.hmr"

# 插件市场（id=PluginMarket，初始快照使用 HTTP）
MARKET_ERROR = "market.error"
PLUGIN_INSTALL_REQUEST = "plugin.install.request"
PLUGIN_INSTALL_PROGRESS = "plugin.install.progress"
PLUGIN_INSTALL_RESULT = "plugin.install.result"
PLUGIN_UNINSTALL_REQUEST = "plugin.uninstall.request"
PLUGIN_UNINSTALL_RESULT = "plugin.uninstall.result"
PLUGIN_INSTALLED_REQUEST = "plugin.installed.request"
PLUGIN_INSTALLED_SYNC = "plugin.installed.sync"

# 通用错误提示（id=EmulatorManager / ArknightsPCToolkit）
EMULATOR_NOTICE = "emulator.notice"
TOOLKIT_NOTICE = "toolkit.notice"


def parse_envelope(raw: object) -> Optional[WSEnvelope]:
    """解析入站消息为统一信封，非法消息记录后丢弃。

    Args:
        raw (object): 已反序列化的入站消息对象。

    Returns:
        Optional[WSEnvelope]: 合法时返回信封，否则返回 None。
    """
    if not isinstance(raw, dict):
        logger.warning(f"入站消息不是对象，已丢弃: {type(raw).__name__}")
        return None
    try:
        return WSEnvelope(**raw)
    except ValidationError as e:
        logger.warning(f"入站消息不符合信封格式，已丢弃: {e.error_count()} 个字段错误")
        return None


def build_message(
    id: str,
    type: str,
    data: Optional[Mapping[str, JsonValue]] = None,
) -> Dict[str, JsonValue]:
    """构造统一信封消息体。

    Args:
        id (str): 路由 ID。
        type (str): 消息类别。
        data (Optional[Mapping[str, JsonValue]]): JSON 消息数据。

    Returns:
        Dict[str, JsonValue]: 可直接序列化发送的消息体。
    """
    return WSEnvelope(id=id, type=type, data=dict(data or {})).model_dump(mode="json")
