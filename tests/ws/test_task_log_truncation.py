"""task.log.updated 日志截断与 publisher 超限丢弃告警测试。

覆盖三类行为:
1. build_task_log_push_payload 的尾部截断、截断标记与边界条件；
2. TaskInfo.on_change 推送超长日志时实际发出截断后的 payload；
3. WSPublisher.send 超过应用层消息上限时发出含 id/type/size 的
   warning 告警（而非静默丢弃），且不污染可合并缓存。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core import task_manager as task_manager_module
from app.core.task_manager import (
    TASK_LOG_PUSH_TAIL_CHARS,
    TaskInfo,
    build_task_log_push_payload,
)
from app.core.ws import protocol
from app.core.ws import publisher as publisher_module
from app.core.ws.publisher import WSPublisher
from app.models.task import ScriptItem


class TestBuildTaskLogPushPayload:
    def test_short_log_payload_unchanged(self) -> None:
        payload = build_task_log_push_payload("line-1")
        assert payload == {"log": "line-1"}
        assert "truncated" not in payload
        assert "log_total_length" not in payload

    def test_none_log_becomes_empty_string(self) -> None:
        assert build_task_log_push_payload(None) == {"log": ""}

    def test_exact_limit_boundary_not_truncated(self) -> None:
        text = "a" * TASK_LOG_PUSH_TAIL_CHARS
        payload = build_task_log_push_payload(text)
        assert payload == {"log": text}

    def test_one_over_limit_truncated_with_markers(self) -> None:
        text = "head" + "a" * TASK_LOG_PUSH_TAIL_CHARS
        payload = build_task_log_push_payload(text)
        # 保留的是尾部窗口，日志最新内容在尾部。
        assert payload["log"] == text[-TASK_LOG_PUSH_TAIL_CHARS:]
        assert len(payload["log"]) == TASK_LOG_PUSH_TAIL_CHARS
        assert payload["truncated"] is True
        assert payload["log_total_length"] == len(text)

    def test_tail_keeps_latest_content(self) -> None:
        text = "old-" * ((TASK_LOG_PUSH_TAIL_CHARS // 4) + 8) + "LATEST-LINE"
        payload = build_task_log_push_payload(text)
        assert payload["log"].endswith("LATEST-LINE")

    def test_tail_window_constant_is_sane(self) -> None:
        # 窗口应远大于插件事件的 2000 字符 tail，给日志页合理回看空间。
        assert TASK_LOG_PUSH_TAIL_CHARS >= 100 * 1024
        # 最坏情况（全部 4 字节 UTF-8 字符）序列化后仍须低于应用层上限，
        # 否则截断后的消息仍会被 publisher 整条拒发。
        assert TASK_LOG_PUSH_TAIL_CHARS * 4 < protocol.DEFAULT_MAX_MESSAGE_BYTES


@pytest.mark.asyncio
async def test_on_change_pushes_truncated_log_payload() -> None:
    oversized_log = "x" * (TASK_LOG_PUSH_TAIL_CHARS + 100)
    task_info = TaskInfo(
        mode="AutoProxy",
        task_id="task-1",
        queue_id=None,
        script_id=None,
        user_id=None,
        script_list=[
            ScriptItem(
                script_id="script-1",
                name="示例脚本",
                status="运行",
                log=oversized_log,
            )
        ],
        current_index=0,
    )

    with patch(
        "app.core.task_manager.Publisher.send", new_callable=AsyncMock
    ) as send, patch.object(
        task_info, "_emit_task_progress", new_callable=AsyncMock
    ), patch.object(task_info, "_emit_task_log", new_callable=AsyncMock):
        await task_info.on_change()

    log_calls = [
        call
        for call in send.await_args_list
        if call.kwargs["type"] == protocol.TASK_LOG_UPDATED
    ]
    assert len(log_calls) == 1
    data = log_calls[0].kwargs["data"]
    assert data["log"] == oversized_log[-TASK_LOG_PUSH_TAIL_CHARS:]
    assert data["truncated"] is True
    assert data["log_total_length"] == len(oversized_log)


@pytest.mark.asyncio
async def test_on_change_short_log_payload_has_no_extra_fields() -> None:
    task_info = TaskInfo(
        mode="AutoProxy",
        task_id="task-1",
        queue_id=None,
        script_id=None,
        user_id=None,
        script_list=[
            ScriptItem(
                script_id="script-1",
                name="示例脚本",
                status="运行",
                log="line-1",
            )
        ],
        current_index=0,
    )

    with patch(
        "app.core.task_manager.Publisher.send", new_callable=AsyncMock
    ) as send, patch.object(
        task_info, "_emit_task_progress", new_callable=AsyncMock
    ), patch.object(task_info, "_emit_task_log", new_callable=AsyncMock):
        await task_info.on_change()

    log_calls = [
        call
        for call in send.await_args_list
        if call.kwargs["type"] == protocol.TASK_LOG_UPDATED
    ]
    assert len(log_calls) == 1
    assert log_calls[0].kwargs["data"] == {"log": "line-1"}


@pytest.mark.asyncio
async def test_publisher_oversize_drop_logs_warning_with_id_type_size() -> None:
    publisher = WSPublisher()
    oversized_payload = {"log": "x" * (protocol.DEFAULT_MAX_MESSAGE_BYTES + 1)}

    with patch.object(publisher_module, "logger") as mock_logger:
        sent = await publisher.send(
            "task-oversize",
            protocol.TASK_INFO_UPDATED,
            oversized_payload,
        )

    assert sent is False
    assert mock_logger.warning.call_count == 1
    message = mock_logger.warning.call_args.args[0]
    assert "id=task-oversize" in message
    assert f"type={protocol.TASK_INFO_UPDATED}" in message
    assert "size=" in message
    assert f"limit={protocol.DEFAULT_MAX_MESSAGE_BYTES}" in message
    # 超限消息不得进入可合并缓存，否则快照恢复同样会超限。
    assert publisher.cache.get("task-oversize", protocol.TASK_INFO_UPDATED) is None


@pytest.mark.asyncio
async def test_publisher_normal_size_send_no_oversize_warning() -> None:
    publisher = WSPublisher()

    with patch.object(publisher_module, "logger") as mock_logger:
        await publisher.send(
            "task-normal",
            protocol.TASK_INFO_UPDATED,
            {"log": "short"},
        )

    assert mock_logger.warning.call_count == 0
    assert publisher.cache.get("task-normal", protocol.TASK_INFO_UPDATED) == {
        "log": "short"
    }


def test_helper_exported_from_task_manager_module() -> None:
    # 常量与 helper 属于日志推送路径的公开约定，防止被误删。
    assert task_manager_module.TASK_LOG_PUSH_TAIL_CHARS == 512 * 1024
    assert callable(task_manager_module.build_task_log_push_payload)
