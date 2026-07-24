"""主 WebSocket 的稳定消息协议。

所有消息始终使用 ``{id, type, data}``。新的 typed event 仅使用 dotted
``type``，不会引入第二套顶层信封。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.models.schema import WSEnvelope
from app.utils import get_logger
from app.utils.ws_limits import DEFAULT_WS_MAX_MESSAGE_BYTES

logger = get_logger("WS协议")


# 固定路由 ID
ID_CLIENT = "Client"
ID_MAIN = "Main"
ID_TASK_MANAGER = "TaskManager"
ID_UPDATE = "Update"
ID_PLUGIN_SYSTEM = "PluginSystem"
ID_PLUGIN_MARKET = "PluginMarket"
ID_EMULATOR_MANAGER = "EmulatorManager"
ID_ARKNIGHTS_PC_TOOLKIT = "ArknightsPCToolkit"

# 主连接替换协议；前端代理依此区分正常重连与后端故障。
CONNECTION_REPLACED_CLOSE_CODE = 4001
CONNECTION_REPLACED_CLOSE_REASON = "connection replaced"
MESSAGE_TOO_BIG_CLOSE_CODE = 1009
MESSAGE_TOO_BIG_CLOSE_REASON = "message too large"

# 应用层在进入 Pydantic/业务分发前后的统一上限。传输层仍保留 uvicorn /
# websockets 自己的帧上限，两层共同避免单条消息占用无界内存。
DEFAULT_MAX_MESSAGE_BYTES = DEFAULT_WS_MAX_MESSAGE_BYTES


# 任务消息（任务 UUID 作为 id）
TASK_INFO_UPDATED = "task.info.updated"
TASK_LOG_UPDATED = "task.log.updated"
TASK_NOTICE = "task.notice"
TASK_COMPLETED = "task.completed"
TASK_CREATED = "task.created"

# 生命周期与电源（id=Main）
BACKEND_SHUTDOWN_READY = "backend.shutdown.ready"
FRONTEND_CLOSE_REQUESTED = "frontend.close.requested"
POWER_COUNTDOWN_UPDATED = "power.countdown.updated"
POWER_COUNTDOWN_CANCELLED = "power.countdown.cancelled"
POWER_SIGN_UPDATED = "power.sign.updated"

# 弹窗（id=Main）
DIALOG_REQUEST = "dialog.request"
DIALOG_RESPONSE = "dialog.response"

# 更新（id=Update）
UPDATE_PROGRESS = "update.progress"
UPDATE_COMPLETED = "update.completed"
UPDATE_FAILED = "update.failed"
UPDATE_CANCELLED = "update.cancelled"

# 插件系统（id=PluginSystem）
PLUGIN_RUNTIME_UPDATED = "plugin.runtime.updated"
PLUGIN_SNAPSHOT_UPDATED = "plugin.snapshot.updated"
PLUGIN_HMR = "plugin.hmr"

# 插件市场（id=PluginMarket）
MARKET_SNAPSHOT_REQUEST = "market.snapshot.request"
MARKET_SNAPSHOT_RESPONSE = "market.snapshot.response"
MARKET_ERROR = "market.error"
PLUGIN_INSTALL_REQUEST = "plugin.install.request"
PLUGIN_INSTALL_PROGRESS = "plugin.install.progress"
PLUGIN_INSTALL_RESULT = "plugin.install.result"
PLUGIN_UNINSTALL_REQUEST = "plugin.uninstall.request"
PLUGIN_UNINSTALL_RESULT = "plugin.uninstall.result"
PLUGIN_INSTALLED_REQUEST = "plugin.installed.request"
PLUGIN_INSTALLED_SYNC = "plugin.installed.sync"

# 通用协议
COMMAND = "command"
COMMAND_RESPONSE = "response"
SNAPSHOT_REQUEST = "snapshot.request"
SNAPSHOT_RESPONSE = "snapshot.response"
EMULATOR_NOTICE = "emulator.notice"
TOOLKIT_NOTICE = "toolkit.notice"


class EventName:
    """兼容早期 Experimental Alpha 对常量容器的引用。"""

    TASK_INFO_UPDATED = TASK_INFO_UPDATED
    PLUGIN_SNAPSHOT_UPDATED = PLUGIN_SNAPSHOT_UPDATED
    PLUGIN_RUNTIME_UPDATED = PLUGIN_RUNTIME_UPDATED
    POWER_SIGN_UPDATED = POWER_SIGN_UPDATED
    DIALOG_REQUEST = DIALOG_REQUEST
    DIALOG_RESPONSE = DIALOG_RESPONSE
    DOWNLOAD_PROGRESS = UPDATE_PROGRESS
    LOG_ENTRY = TASK_LOG_UPDATED
    COMMAND_RESULT = COMMAND_RESPONSE
    PLUGIN_REALTIME = PLUGIN_RUNTIME_UPDATED
    UPDATE_PROGRESS = UPDATE_PROGRESS
    SYSTEM_NOTIFY = TASK_NOTICE
    EMULATOR_STATUS = EMULATOR_NOTICE
    MAAFW_TOOL = TOOLKIT_NOTICE


# 只有可由快照恢复的状态才进入 publisher cache。
MERGEABLE_TYPES: frozenset[str] = frozenset(
    {
        TASK_INFO_UPDATED,
        PLUGIN_SNAPSHOT_UPDATED,
        PLUGIN_RUNTIME_UPDATED,
        POWER_SIGN_UPDATED,
    }
)
MERGEABLE_EVENTS = MERGEABLE_TYPES


def message_size_bytes(raw: Any) -> int:
    """返回消息在线路上的近似 UTF-8 JSON 字节数。"""

    if isinstance(raw, bytes):
        return len(raw)
    if isinstance(raw, str):
        return len(raw.encode("utf-8"))
    serialized = json.dumps(
        raw,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return len(serialized.encode("utf-8"))


def parse_envelope(raw: Any) -> WSEnvelope | None:
    """解析入站对象；非法消息记录后丢弃。"""

    if not isinstance(raw, dict):
        logger.warning(f"入站消息不是对象，已丢弃: {type(raw).__name__}")
        return None
    try:
        return WSEnvelope.model_validate(raw)
    except ValidationError as exc:
        logger.warning(f"入站消息不符合 WS 信封格式，已丢弃: {exc.error_count()} 个字段错误")
        return None


def build_message(
    id: str,
    type: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造可直接发送的稳定信封。"""

    return WSEnvelope(id=str(id or ""), type=type, data=dict(data or {})).model_dump()


# 兼容旧模块的类型名；内容仍是稳定信封，不再支持 event/payload。
LegacyMessage = WSEnvelope
OutboundMessage = WSEnvelope
