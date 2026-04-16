#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from datetime import datetime
from typing import Any, Dict, Optional

from app.utils import get_logger
from app.utils.constants import UTC8

from .event_contract import EVENT_CONTRACT_VERSION, is_script_event, is_valid_source


logger = get_logger("插件事件工厂")


class PluginEventFactory:
    """统一构建并发送插件事件。"""

    @staticmethod
    def build_task_progress_data(
        task_info: Any,
        *,
        queue_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        将任务对象转换为标准化的任务进度事件数据。

        Args:
            task_info (Any): 任务运行信息对象，需包含脚本列表与当前进度字段。

        Returns:
            Dict[str, Any]: 适用于 task.progress 事件的结构化载荷。
        """
        total_scripts = len(task_info.script_list)
        completed_scripts = sum(
            1 for item in task_info.script_list if item.status == "完成"
        )
        total_users = sum(len(item.user_list) for item in task_info.script_list)
        completed_users = sum(
            1
            for script_item in task_info.script_list
            for user_item in script_item.user_list
            if user_item.status == "完成"
        )

        current_script = None
        current_script_id = None
        current_script_name = None
        if 0 <= task_info.current_index < total_scripts:
            item = task_info.script_list[task_info.current_index]
            current_script = {
                "script_id": item.script_id,
                "script_name": item.name,
                "status": item.status,
                "current_user_index": item.current_index,
                "user_count": len(item.user_list),
            }
            current_script_id = item.script_id
            current_script_name = item.name

        return {
            "task_id": task_info.task_id,
            "mode": task_info.mode,
            "queue_id": task_info.queue_id,
            "queue_name": queue_name,
            "script_id": task_info.script_id,
            "user_id": task_info.user_id,
            "current_script_index": task_info.current_index,
            "current_script_id": current_script_id,
            "current_script_name": current_script_name,
            "script_total": total_scripts,
            "script_completed": completed_scripts,
            "user_total": total_users,
            "user_completed": completed_users,
            "task_info": task_info.asdict,
            "current_script": current_script,
        }

    @staticmethod
    async def _emit_payload_async(*, event: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """异步发送已构建好的事件载荷。

        该方法统一处理事件发送异常，避免业务链路被插件系统影响。
        """
        try:
            from app.core import PluginManager

            await PluginManager.emit_async(event, payload)
        except Exception as e:
            logger.warning(
                f"插件事件广播失败: event={event}, source={payload.get('source')}, error={e}"
            )

        return payload

    @staticmethod
    def _emit_payload(*, event: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        同步桥接发送已构建好的事件载荷。

        Args:
            event (str): 事件名。
            payload (Dict[str, Any]): 事件载荷。

        Returns:
            Dict[str, Any]: 原始事件载荷。
        """
        try:
            from app.core import PluginManager

            PluginManager.emit(event, payload)
        except Exception as e:
            logger.warning(
                f"插件事件广播失败: event={event}, source={payload.get('source')}, error={e}"
            )

        return payload

    @staticmethod
    def build_envelope(
        *,
        event: str,
        source: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        构建通用插件事件包。

        Args:
            event (str): 事件名。
            source (str): 事件来源标识。
            data (Optional[Dict[str, Any]]): 可选业务数据字典。

        Returns:
            Dict[str, Any]: 包含基础契约字段的事件载荷。
        """
        payload: Dict[str, Any] = {
            "event": event,
            "event_version": EVENT_CONTRACT_VERSION,
            "source": source,
            "timestamp": datetime.now(tz=UTC8).isoformat(),
        }

        if isinstance(data, dict) and data:
            payload["data"] = data

        return payload

    @staticmethod
    async def emit_event_async(
        *,
        event: str,
        source: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        构建并发送通用事件。

        Args:
            event (str): 事件名。
            source (str): 事件来源标识。
            data (Optional[Dict[str, Any]]): 可选业务数据字典。

        Returns:
            Dict[str, Any]: 已发送的事件载荷。
        """
        if not is_valid_source(source):
            logger.warning(f"事件来源格式不规范: source={source}, event={event}")

        payload = PluginEventFactory.build_envelope(event=event, source=source, data=data)
        return await PluginEventFactory._emit_payload_async(event=event, payload=payload)

    @staticmethod
    def emit_event(
        *,
        event: str,
        source: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        构建并发送通用事件（同步桥接）。

        Args:
            event (str): 事件名。
            source (str): 事件来源标识。
            data (Optional[Dict[str, Any]]): 可选业务数据字典。

        Returns:
            Dict[str, Any]: 已发送的事件载荷。
        """
        if not is_valid_source(source):
            logger.warning(f"事件来源格式不规范: source={source}, event={event}")

        payload = PluginEventFactory.build_envelope(event=event, source=source, data=data)
        return PluginEventFactory._emit_payload(event=event, payload=payload)

    @staticmethod
    def build_script_payload(
        *,
        event: str,
        source: str,
        task_id: Optional[str] = None,
        script_id: Optional[str] = None,
        script_name: Optional[str] = None,
        mode: Optional[str] = None,
        status: Optional[str] = None,
        error: Optional[str] = None,
        result: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        构建脚本领域事件载荷。

        Args:
            event (str): 事件名。
            source (str): 事件来源标识。
            task_id (Optional[str]): 任务 ID。
            script_id (Optional[str]): 脚本 ID。
            script_name (Optional[str]): 脚本名称。
            mode (Optional[str]): 运行模式。
            status (Optional[str]): 状态信息。
            error (Optional[str]): 错误信息。
            result (Optional[str]): 结果信息。
            data (Optional[Dict[str, Any]]): 可选业务数据字典。

        Returns:
            Dict[str, Any]: 合并脚本上下文字段后的事件载荷。
        """
        payload = PluginEventFactory.build_envelope(event=event, source=source, data=data)

        if task_id is not None:
            payload["task_id"] = str(task_id)
        if script_id is not None:
            payload["script_id"] = str(script_id)
        if script_name is not None:
            payload["script_name"] = script_name
        if mode is not None:
            payload["mode"] = mode
        if status is not None:
            payload["status"] = status
        if error is not None:
            payload["error"] = error
        if result is not None:
            payload["result"] = result

        return payload

    @staticmethod
    async def emit_script_event_async(
        *,
        event: str,
        source: str,
        task_id: Optional[str] = None,
        script_id: Optional[str] = None,
        script_name: Optional[str] = None,
        mode: Optional[str] = None,
        status: Optional[str] = None,
        error: Optional[str] = None,
        result: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        构建并发送脚本领域事件。

        Args:
            event (str): 事件名。
            source (str): 事件来源标识。
            task_id (Optional[str]): 任务 ID。
            script_id (Optional[str]): 脚本 ID。
            script_name (Optional[str]): 脚本名称。
            mode (Optional[str]): 运行模式。
            status (Optional[str]): 状态信息。
            error (Optional[str]): 错误信息。
            result (Optional[str]): 结果信息。
            data (Optional[Dict[str, Any]]): 可选业务数据字典。

        Returns:
            Dict[str, Any]: 已发送的脚本事件载荷。
        """
        if not is_valid_source(source):
            logger.warning(f"脚本事件来源格式不规范: source={source}, event={event}")

        if not is_script_event(event):
            logger.warning(f"非标准脚本事件名: event={event}")

        payload = PluginEventFactory.build_script_payload(
            event=event,
            source=source,
            task_id=task_id,
            script_id=script_id,
            script_name=script_name,
            mode=mode,
            status=status,
            error=error,
            result=result,
            data=data,
        )
        return await PluginEventFactory._emit_payload_async(event=event, payload=payload)

    @staticmethod
    def emit_script_event(
        *,
        event: str,
        source: str,
        task_id: Optional[str] = None,
        script_id: Optional[str] = None,
        script_name: Optional[str] = None,
        mode: Optional[str] = None,
        status: Optional[str] = None,
        error: Optional[str] = None,
        result: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        构建并发送脚本领域事件（同步桥接）。

        Args:
            event (str): 事件名。
            source (str): 事件来源标识。
            task_id (Optional[str]): 任务 ID。
            script_id (Optional[str]): 脚本 ID。
            script_name (Optional[str]): 脚本名称。
            mode (Optional[str]): 运行模式。
            status (Optional[str]): 状态信息。
            error (Optional[str]): 错误信息。
            result (Optional[str]): 结果信息。
            data (Optional[Dict[str, Any]]): 可选业务数据字典。

        Returns:
            Dict[str, Any]: 已发送的脚本事件载荷。
        """
        if not is_valid_source(source):
            logger.warning(f"脚本事件来源格式不规范: source={source}, event={event}")

        if not is_script_event(event):
            logger.warning(f"非标准脚本事件名: event={event}")

        payload = PluginEventFactory.build_script_payload(
            event=event,
            source=source,
            task_id=task_id,
            script_id=script_id,
            script_name=script_name,
            mode=mode,
            status=status,
            error=error,
            result=result,
            data=data,
        )
        return PluginEventFactory._emit_payload(event=event, payload=payload)
