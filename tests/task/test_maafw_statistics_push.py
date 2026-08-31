"""MaaFW 用户级「统计信息」推送。

``MaaFWUserConfig`` 一直有完整的 Notify 组（Enabled / IfSendStatistic /
IfSendMail / ToAddress / IfServerChan / ServerChanKey），编辑页也能配，但在此
之前没有任何代码往它发——脚本级「代理结果」是 MaaFW 唯一会发出去的报告，与
M9A 等专项脚本不齐。

两层都要守：

- ``report._push_statistics`` 的渠道分发；
- ``final_task`` 真的会调它。**挂接点才是上次出事的地方**：``5f8d90db`` 把推送
  接在第一层 ``manager.py`` 里，``#481`` 删掉那个文件时一并带走，而
  ``test_maafw_run_report`` 只测 ``push_notification`` 函数本身、测不到调用点，
  于是一路全绿地漏着，直到 ``#417`` 统一迁移才把脚本级补回来。
"""

import asyncio
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app.core  # noqa: F401
import app.core.notify as core_notify
import app.task.MaaFW.tools.embedded.runner_task as runner_task
from app.task.MaaFW.tools.notify import report


class _FakeTemplate:
    def render(self, message):
        return "html:" + str(message.get("user_info", ""))


class _FakeTemplateEnv:
    def __init__(self):
        self.requested = []

    def get_template(self, name):
        self.requested.append(name)
        return _FakeTemplate()


class _FakeConfig:
    def __init__(self, settings=None, webhooks=None):
        self.settings = settings or {}
        self.notify_env = _FakeTemplateEnv()
        self.Notify_CustomWebhooks = webhooks or {}

    def get(self, group, name):
        return self.settings.get((group, name), False)


class _FakeUserConfig:
    """用户配置的最小实现：get(group, key) + Notify_CustomWebhooks。"""

    def __init__(self, settings):
        self.settings = settings
        self.Notify_CustomWebhooks = {}
        self.sets = []

    def get(self, group, name):
        return self.settings.get((group, name), False)

    async def set(self, group, name, value):
        self.sets.append((group, name, value))
        self.settings[(group, name)] = value


class _FakeNotify:
    def __init__(self):
        self.mail_calls = []
        self.serverchan_calls = []
        self.webhook_calls = []
        self.koishi_calls = []

    async def send_mail(self, mode, title, content, to_address):
        self.mail_calls.append((mode, title, content, to_address))

    async def ServerChanPush(self, title, content, send_key):
        self.serverchan_calls.append((title, content, send_key))

    async def WebhookPush(self, title, content, webhook):
        self.webhook_calls.append((title, content, webhook))

    async def send_koishi(self, content):
        self.koishi_calls.append(content)


def _statistics():
    return {
        "user_info": "用户A",
        "start_time": "2026-08-31 10:00:00",
        "end_time": "2026-08-31 10:30:00",
        "user_result": "代理任务全部完成",
    }


class StatisticsDispatchTest(unittest.TestCase):
    """渠道分发：全局与用户两路各自受自己的开关控制。"""

    def _push(self, config, notify, user_config=None):
        with ExitStack() as stack:
            stack.enter_context(patch.object(report, "Config", config))
            stack.enter_context(patch.object(core_notify, "Config", config))
            stack.enter_context(patch.object(core_notify, "Notify", notify))
            asyncio.run(
                report.push_notification(
                    "统计信息", "标题", _statistics(), user_config=user_config
                )
            )

    def test_both_switches_off_sends_nothing(self) -> None:
        notify = _FakeNotify()
        self._push(_FakeConfig(), notify)
        self.assertEqual(notify.mail_calls, [])
        self.assertEqual(notify.serverchan_calls, [])

    def test_global_statistic_switch_fans_out(self) -> None:
        notify = _FakeNotify()
        config = _FakeConfig(
            {
                ("Notify", "IfSendStatistic"): True,
                ("Notify", "IfServerChan"): True,
                ("Notify", "ServerChanKey"): "global-key",
            }
        )
        self._push(config, notify)
        self.assertEqual(len(notify.serverchan_calls), 1)
        self.assertEqual(notify.serverchan_calls[0][2], "global-key")

    def test_user_channels_receive_their_own_copy(self) -> None:
        """用户自己配的邮箱要收到——这正是此前完全没接的那一路。"""

        notify = _FakeNotify()
        user_config = _FakeUserConfig(
            {
                ("Notify", "Enabled"): True,
                ("Notify", "IfSendStatistic"): True,
                ("Notify", "IfSendMail"): True,
                ("Notify", "ToAddress"): "user@example.com",
            }
        )
        self._push(_FakeConfig(), notify, user_config=user_config)
        self.assertEqual(len(notify.mail_calls), 1)
        self.assertEqual(notify.mail_calls[0][3], "user@example.com")

    def test_user_switch_off_sends_nothing_to_the_user(self) -> None:
        notify = _FakeNotify()
        user_config = _FakeUserConfig(
            {
                ("Notify", "Enabled"): False,
                ("Notify", "IfSendStatistic"): True,
                ("Notify", "IfSendMail"): True,
                ("Notify", "ToAddress"): "user@example.com",
            }
        )
        self._push(_FakeConfig(), notify, user_config=user_config)
        self.assertEqual(notify.mail_calls, [])

    def test_statistics_ignore_the_result_time_gate(self) -> None:
        """SendTaskResultTime 管的是「代理结果」，不该拦住统计信息。"""

        notify = _FakeNotify()
        config = _FakeConfig(
            {
                ("Notify", "SendTaskResultTime"): "仅失败时",
                ("Notify", "IfSendStatistic"): True,
                ("Notify", "IfServerChan"): True,
                ("Notify", "ServerChanKey"): "k",
            }
        )
        self._push(config, notify)
        self.assertEqual(len(notify.serverchan_calls), 1)

    def test_engine_agnostic_template(self) -> None:
        """MaaFW 是通用外部运行，用 general_statistics 而不是某个专项模板。"""

        config = _FakeConfig({("Notify", "IfSendStatistic"): True})
        self._push(config, _FakeNotify())
        self.assertEqual(config.notify_env.requested, ["general_statistics.html"])


class StatisticsWiringTest(unittest.TestCase):
    """挂接点：final_task 必须真的把统计发出去。"""

    def _task(self, *, run_complete: bool):
        task = object.__new__(runner_task.MaaFWPluginAutoProxyTask)
        task.check_result = "Pass"
        task.run_complete = run_complete
        task.task_info = SimpleNamespace(task_id="task-id")
        task.cur_user_item = SimpleNamespace(name="用户A", status="运行")
        task.cur_user_log = SimpleNamespace(status="MaaFW 任务运行超时")
        task.cur_user_config = _FakeUserConfig(
            {("Data", "ProxyTimes"): 3, ("Info", "RemainedDay"): -1}
        )
        task.cur_user_log_started_at = None
        task.saved_paths = [Path("history/a.json")]

        async def noop():
            return None

        task._shutdown_runner = noop
        task._close_emulator = noop
        task._close_game = noop
        task._release_project_path = noop
        task._send_success_notify = noop

        async def save_logs():
            return task.saved_paths

        task._save_user_logs = save_logs
        return task

    def _run_final_task(self, task):
        pushed = []

        async def fake_push(**kwargs):
            pushed.append(kwargs)

        async def fake_merge(paths):
            return {"index": {}}

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(runner_task, "push_notification", fake_push)
            )
            stack.enter_context(
                patch.object(runner_task.Config, "merge_statistic_info", fake_merge)
            )
            asyncio.run(task.final_task())
        return pushed

    def test_final_task_pushes_the_logs_it_just_saved(self) -> None:
        task = self._task(run_complete=True)
        captured = []

        async def capture(paths):
            captured.append(paths)

        task._push_user_statistics = capture
        asyncio.run(task.final_task())
        self.assertEqual(captured, [task.saved_paths], "统计文件路径要来自本轮日志")

    def test_push_carries_mode_user_config_and_result(self) -> None:
        task = self._task(run_complete=False)
        pushed = self._run_final_task(task)

        self.assertEqual(len(pushed), 1)
        call = pushed[0]
        self.assertEqual(call["mode"], "统计信息")
        self.assertIs(call["user_config"], task.cur_user_config)
        self.assertEqual(call["message"]["user_info"], "用户A")
        self.assertEqual(call["message"]["user_result"], "MaaFW 任务运行超时")
        self.assertIn("X", call["title"])

    def test_successful_run_reports_completion(self) -> None:
        task = self._task(run_complete=True)
        pushed = self._run_final_task(task)

        self.assertEqual(pushed[0]["message"]["user_result"], "代理任务全部完成")

    def test_push_failure_does_not_break_the_run(self) -> None:
        """推送炸了不能连累收尾——用户状态照常落定。"""

        task = self._task(run_complete=True)

        async def boom(*args, **kwargs):
            raise RuntimeError("smtp down")

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(runner_task.Config, "merge_statistic_info", boom)
            )
            stack.enter_context(patch.object(runner_task.Publisher, "send", boom))
            asyncio.run(task.final_task())
        self.assertEqual(task.cur_user_item.status, "完成")


if __name__ == "__main__":
    unittest.main()
