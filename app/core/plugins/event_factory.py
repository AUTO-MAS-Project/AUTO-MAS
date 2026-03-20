#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.utils import get_logger
from app.utils.constants import UTC8

from .event_contract import EVENT_CONTRACT_VERSION, is_script_event, is_valid_source


logger = get_logger("插件事件工厂")


class PluginEventFactory:
    """统一构建并发送插件事件。"""

    @staticmethod
    def _emit_payload(*, event: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """发送已构建好的事件载荷。

        该方法统一处理事件发送异常，避免业务链路被插件系统影响。
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
        """构建通用事件包。

        通用事件仅包含基础字段（event/source/timestamp）和可选 data，
        适用于 backend.start 这类非脚本领域事件。
        """
        payload: Dict[str, Any] = {
            "event": event,
            "event_version": EVENT_CONTRACT_VERSION,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if isinstance(data, dict) and data:
            payload["data"] = data

        return payload

    @staticmethod
    def emit_event(
        *,
        event: str,
        source: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """发送通用事件。

        业务模块可通过该方法直接发送非脚本领域事件，避免携带无关字段。
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
        """构建脚本领域事件载荷。

        该方法在通用事件包基础上，补充 task/script 相关字段。
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
        """发送脚本领域事件。

        适用于 task_manager 等脚本生命周期场景。
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
