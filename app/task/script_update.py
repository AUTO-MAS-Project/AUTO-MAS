"""L2 的脚本安装恢复汇总，兼容旧 manager 产生的恢复事件。

TODO(脚本更新迁移)：检查、安装和恢复的统一编排后续全部迁入 L2；
当前只迁入任务作用域和结果汇总，尚未将旧 manager 的安装业务上移。
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

from app.core import Publisher
from app.core.ws import protocol
from app.models.schema import WSTaskNoticeData
from app.models.task import TaskItem
from app.utils import get_logger

if TYPE_CHECKING:
    from app.core.script_update_recovery import RecoveryIncident

logger = get_logger("脚本更新")


_current_recovery_session: ContextVar["ScriptRecoverySession | None"] = ContextVar(
    "current_script_update_recovery_session", default=None
)


def record_recovery_event(event: RecoveryIncident) -> None:
    """将安装恢复事件加入当前任务的恢复会话，未绑定会话时记录警告以保留诊断线索。"""
    session = _current_recovery_session.get()
    if session is not None:
        session.record_recovery(event)
    else:
        logger.warning(
            f"脚本恢复报告未附着运行队列：{event.script_type} {event.outcome}"
        )


class ScriptRecoverySession:
    """L2 持有的一轮安装恢复结果，在任务收尾统一发布。"""

    def __init__(self, task_info: TaskItem) -> None:
        """绑定本次任务并建立恢复事件列表和汇总发送标记。"""
        self._task = task_info
        self._recovery_events: list[RecoveryIncident] = []
        self._recovery_reported = False

    @contextmanager
    def bind(self):
        """在上下文内将当前任务设为安装恢复事件接收方，退出时恢复外层会话。"""
        token = _current_recovery_session.set(self)
        try:
            yield
        finally:
            _current_recovery_session.reset(token)

    def record_recovery(self, event: RecoveryIncident) -> None:
        """只记录当前任务的恢复结果，去重重复确认与后续账号复检。"""
        if event not in self._recovery_events:
            self._recovery_events.append(event)

    async def publish_recovery_summary(self) -> None:
        """在整轮任务完成时集中发一份报告，非脚本级即时弹窗。"""
        if self._recovery_reported:
            return
        self._recovery_reported = True
        if not self._recovery_events:
            return
        outcomes = {
            "verified": "已校验安装并自动清理残留记录",
            "reinstalled": "自动重装修复完成",
            "old_version": "重新下载失败，已验证旧版并继续运行",
            "blocked": "恢复失败，已保护安装现场并阻止启动",
        }
        lines = ["[脚本安装恢复汇总]"]
        for event in self._recovery_events:
            detail = f"；原因：{event.reason}" if event.reason else ""
            source = f"；来源：{event.source}" if event.source else ""
            version = (
                f"；当前版本：{event.installed_version}"
                if event.installed_version
                else ""
            )
            lines.append(
                f"- {event.script_type} ({event.script_id})："
                f"{outcomes[event.outcome]}{version}{source}{detail}"
                f"；目录：{event.install_root}"
            )
        message = "\n".join(lines)
        if any(
            event.outcome in ("old_version", "blocked")
            for event in self._recovery_events
        ):
            logger.warning(message)
        else:
            logger.info(message)
        # TaskItem.current.log 是虚拟投影（不可写）；汇总保存在任务树自身
        # 的 recovery_summary 字段，再通过任务完成包和任务通知同时传递。
        self._task.current.recovery_summary = message
        await self._task.commit()
        try:
            await Publisher.send(
                id=self._task.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="warning"
                    if any(
                        e.outcome in ("old_version", "blocked")
                        for e in self._recovery_events
                    )
                    else "info",
                    message=message,
                ),
            )
        except Exception:
            logger.warning("脚本恢复汇总已写入日志，但发送任务通知失败")
