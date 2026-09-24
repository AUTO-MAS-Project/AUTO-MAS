"""任务日志增量推送协议: seq 单调递增、追加只发差量、日志变短整体替换、快照与推送衔接。"""

import unittest
from unittest.mock import AsyncMock, patch

from app.core.task_manager import TaskInfo, _TaskManager
from app.core.ws import protocol
from app.models.task import ScriptItem


def _make_task_info() -> TaskInfo:
    task_info = TaskInfo(
        mode="AutoProxy",
        task_id="task-id",
        queue_id=None,
        script_id=None,
        user_id=None,
    )
    task_info.script_list = [ScriptItem(script_id="s1", name="脚本", status="运行")]
    task_info.current_index = 0
    return task_info


def _log_payloads(send: AsyncMock) -> list:
    return [
        call.kwargs["data"]
        for call in send.await_args_list
        if call.kwargs["type"] == protocol.TASK_LOG_UPDATED
    ]


class TaskLogIncrementalTest(unittest.IsolatedAsyncioTestCase):
    async def test_first_push_replaces_and_appends_send_only_delta(self) -> None:
        task_info = _make_task_info()
        with patch(
            "app.core.task_manager.Publisher.send", new_callable=AsyncMock
        ) as send:
            task_info.script_list[0].log = "line1\n"
            await task_info.on_change()
            task_info.script_list[0].log = "line1\nline2\n"
            await task_info.on_change()

        first, second = _log_payloads(send)
        self.assertEqual((first.log, first.append, first.seq), ("line1\n", False, 1))
        self.assertEqual((second.log, second.append, second.seq), ("line2\n", True, 2))
        self.assertEqual(task_info._last_pushed_log, "line1\nline2\n")

    async def test_unchanged_log_does_not_push_but_info_still_does(self) -> None:
        task_info = _make_task_info()
        with patch(
            "app.core.task_manager.Publisher.send", new_callable=AsyncMock
        ) as send:
            task_info.script_list[0].log = "same"
            await task_info.on_change()
            await task_info.on_change()

        self.assertEqual(len(_log_payloads(send)), 1)
        info_pushes = [
            call
            for call in send.await_args_list
            if call.kwargs["type"] == protocol.TASK_INFO_UPDATED
        ]
        self.assertEqual(len(info_pushes), 2)
        self.assertEqual(task_info._log_seq, 1)

    async def test_shrunk_log_falls_back_to_full_replace(self) -> None:
        task_info = _make_task_info()
        with patch(
            "app.core.task_manager.Publisher.send", new_callable=AsyncMock
        ) as send:
            task_info.script_list[0].log = "abc"
            await task_info.on_change()
            task_info.script_list[0].log = "xyz"
            await task_info.on_change()
            task_info.script_list[0].log = ""
            await task_info.on_change()

        payloads = _log_payloads(send)
        self.assertEqual([p.append for p in payloads], [False, False, False])
        self.assertEqual([p.seq for p in payloads], [1, 2, 3])
        self.assertEqual([p.log for p in payloads], ["abc", "xyz", ""])

    async def test_full_replace_is_truncated_but_state_keeps_full_log(self) -> None:
        task_info = _make_task_info()
        long_log = "x" * 200_005
        with patch(
            "app.core.task_manager.Publisher.send", new_callable=AsyncMock
        ) as send:
            task_info.script_list[0].log = long_log
            await task_info.on_change()
            task_info.script_list[0].log = long_log + "tail"
            await task_info.on_change()

        first, second = _log_payloads(send)
        self.assertEqual(len(first.log), 200_000)
        self.assertEqual((second.log, second.append), ("tail", True))

    async def test_snapshot_returns_last_pushed_log_not_current(self) -> None:
        task_info = _make_task_info()
        manager = _TaskManager()
        manager.task_info[__import__("uuid").uuid4()] = task_info
        with (
            patch("app.core.task_manager.Publisher.send", new_callable=AsyncMock),
            patch.object(_TaskManager, "_scheduled_script_identities", return_value=[]),
        ):
            task_info.script_list[0].log = "pushed"
            await task_info.on_change()
            # 变化尚未推送: 快照必须回上次推送的内容, 才能与下一条增量衔接
            task_info.script_list[0].log = "pushed+pending"
            snapshot = manager.get_runtime_snapshot()

        item = snapshot.tasks[0]
        self.assertEqual((item.log, item.logSeq), ("pushed", 1))
