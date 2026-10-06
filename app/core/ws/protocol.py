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
各 ``WS*Data`` 为出站 data 段的载荷契约，由业务模块构造后交给 Publisher。
"""

from typing import Dict, List, Literal, Mapping, Optional

from pydantic import BaseModel, Field, JsonValue, ValidationError, field_validator

from app.models.task import TaskMode
from app.utils.logger import get_logger

logger = get_logger("WS协议")


# ==================== 固定路由 ID ====================

ID_MAIN = "Main"
ID_TASK_MANAGER = "TaskManager"
ID_UPDATE = "Update"
ID_PLUGIN_SYSTEM = "PluginSystem"
ID_PLUGIN_MARKET = "PluginMarket"
ID_I18N = "I18n"
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

# 国际化资源变更（id=I18n）
I18N_UPDATED = "i18n.updated"

# 通用错误提示（id=EmulatorManager / ArknightsPCToolkit）
EMULATOR_NOTICE = "emulator.notice"
TOOLKIT_NOTICE = "toolkit.notice"


# ==================== 消息信封 ====================


class WSEnvelope(BaseModel):
    """主 WebSocket 统一消息信封, 前后端均按 id + type 路由"""

    id: str = Field(
        ...,
        description="路由ID, 标识任务、请求或业务会话, 如 Main、TaskManager、任务UUID",
    )
    type: str = Field(
        ...,
        description="消息类别, 点分小写命名, 如 task.info.updated、backend.shutdown.ready",
    )
    data: Dict[str, JsonValue] = Field(
        default_factory=dict, description="消息数据, 关键消息使用对应的 WS*Data 模型构造"
    )

    @field_validator("id", "type")
    @classmethod
    def validate_route_field(cls, value: str) -> str:
        """路由字段必须为非空字符串，并统一去除首尾空白。"""

        normalized = value.strip()
        if not normalized:
            raise ValueError("WebSocket 路由 id/type 不能为空")
        return normalized


# ==================== 任务消息载荷 ====================


class WSTaskNoticeData(BaseModel):
    """任务提示消息数据 (type=task.notice)"""

    level: Literal["info", "warning", "error"] = Field(..., description="提示级别")
    message: str = Field(..., description="提示内容")


class WSTaskLogUpdatedData(BaseModel):
    """当前任务日志 (type=task.log.updated)。"""

    log: str = Field(default="", description="当前脚本日志")


class WSTaskCreatedData(BaseModel):
    """新任务创建通知 (id=TaskManager, type=task.created)。"""

    taskId: str = Field(..., description="任务 ID")
    mode: TaskMode = Field(..., description="任务模式")
    queueId: Optional[str] = Field(default=None, description="调度队列 ID")
    scriptId: Optional[str] = Field(default=None, description="脚本 ID")
    userId: Optional[str] = Field(default=None, description="用户 ID")


class WSTaskCompletedData(BaseModel):
    """任务完成消息 (type=task.completed)。

    ``task`` 为 ``TaskItem`` 的 API dump（与 ``/api/dispatch/get``、
    ``task.info.updated`` 同一载荷）。
    """

    result: str = Field(default="", description="结果摘要")
    outcome: Literal["success", "error", "cancelled"] = Field(
        default="success", description="终态"
    )
    error: Optional[str] = Field(default=None, description="错误说明")
    task: Dict[str, JsonValue] = Field(
        default_factory=dict, description="TaskItem API 载荷"
    )


# ==================== 弹窗消息载荷 ====================


class WSDialogRequestData(BaseModel):
    """应用内弹窗请求数据 (id=Main, type=dialog.request)"""

    requestId: str = Field(..., description="弹窗请求ID, 响应使用相同ID关联")
    taskId: Optional[str] = Field(default=None, description="关联的任务ID")
    title: str = Field(..., description="弹窗标题")
    message: str = Field(..., description="弹窗正文")
    options: List[str] = Field(
        default_factory=lambda: ["是", "否"], description="选项文案"
    )


class WSDialogResponseData(BaseModel):
    """应用内弹窗响应数据 (id=Main, type=dialog.response)"""

    requestId: str = Field(..., description="对应的弹窗请求ID")
    choice: bool = Field(..., description="用户是否选择第一个选项")


# ==================== 电源与更新消息载荷 ====================


class PowerCountdownSnapshot(BaseModel):
    """当前电源倒计时 HTTP 初始快照。"""

    active: bool = Field(default=False, description="是否正在倒计时")
    operation: Optional[str] = Field(default=None, description="待执行电源操作")
    remaining: int = Field(default=0, ge=0, description="剩余秒数")


class UpdateDownloadSnapshot(BaseModel):
    """更新下载 HTTP 初始快照。"""

    status: Literal[
        "idle",
        "downloading",
        "switchingSource",
        "completed",
        "failed",
        "cancelled",
    ] = Field(default="idle")
    version: Optional[str] = Field(default=None, description="当前下载版本")
    source: Optional[str] = Field(default=None, description="当前下载源")
    downloaded_size: int = Field(default=0, ge=0)
    file_size: int = Field(default=0, ge=0)
    speed: float = Field(default=0, ge=0)
    file: Optional[str] = Field(default=None, description="完成后的更新包路径")
    message: Optional[str] = Field(default=None, description="失败或状态说明")


class WSPowerCountdownData(BaseModel):
    """电源倒计时更新数据 (id=Main, type=power.countdown.updated)"""

    operation: str = Field(..., description="将执行的电源操作")
    remaining: int = Field(..., description="剩余秒数")


class WSUpdateProgressData(BaseModel):
    """更新下载进度数据 (id=Update, type=update.progress)"""

    downloaded_size: int = Field(..., description="已下载字节数")
    file_size: int = Field(..., description="文件总字节数")
    speed: float = Field(..., description="下载速度 (B/s)")
    source: str = Field(..., description="下载源")


class WSUpdateCompletedData(BaseModel):
    """更新下载完成数据 (id=Update, type=update.completed)。"""

    file: str = Field(..., description="已下载更新包路径")


class WSUpdateFailedData(BaseModel):
    """更新下载失败数据 (id=Update, type=update.failed)。"""

    message: str = Field(..., description="失败原因")


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
