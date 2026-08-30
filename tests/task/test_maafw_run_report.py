import asyncio
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import app.core  # noqa: F401

from app.task.MaaFW.tools.notify import report


class _FakeTemplate:
    def render(self, message):
        return f"html:{message['title']}"


class _FakeTemplateEnv:
    def get_template(self, name):
        assert name == "general_result.html"
        return _FakeTemplate()


class _FakeConfig:
    def __init__(self, settings=None, webhooks=None):
        self.settings = settings or {}
        self.notify_env = _FakeTemplateEnv()
        self.Notify_CustomWebhooks = webhooks or {}

    def get(self, group, name):
        return self.settings.get((group, name), False)


class _FakeNotify:
    def __init__(self):
        self.mail_calls = []
        self.serverchan_calls = []
        self.webhook_calls = []
        self.koishi_calls = []

    async def send_mail(self, kind, title, content, to_address):
        self.mail_calls.append((kind, title, content, to_address))

    async def ServerChanPush(self, title, content, send_key):
        self.serverchan_calls.append((title, content, send_key))

    async def WebhookPush(self, title, content, webhook):
        self.webhook_calls.append((title, content, webhook))

    async def send_koishi(self, content):
        self.koishi_calls.append(content)


def _message(*, uncompleted=0):
    return {
        "title": "08-28 | 测试 MaaFW的自动代理任务报告",
        "script_name": "测试 MaaFW",
        "start_time": "2026-08-28 18:00:00",
        "end_time": "2026-08-28 18:30:00",
        "completed_count": 1,
        "uncompleted_count": uncompleted,
        "result": "用户A: 18:00 - Success!",
    }


class MaafwRunReportGateTest(unittest.TestCase):
    """SendTaskResultTime 门控与渠道分发的纯逻辑回归。"""

    def _push(self, config, notify, mode="代理结果", message=None):
        with ExitStack() as stack:
            stack.enter_context(patch.object(report, "Config", config))
            stack.enter_context(patch.object(report, "Notify", notify))
            asyncio.run(
                report.push_notification(
                    mode, "标题", message if message is not None else _message()
                )
            )

    def test_default_setting_sends_nothing(self) -> None:
        notify = _FakeNotify()
        self._push(_FakeConfig(), notify)
        self.assertEqual(notify.mail_calls, [])
        self.assertEqual(notify.serverchan_calls, [])
        self.assertEqual(notify.webhook_calls, [])
        self.assertEqual(notify.koishi_calls, [])

    def test_failure_only_setting_skips_full_success(self) -> None:
        notify = _FakeNotify()
        config = _FakeConfig(
            {
                ("Notify", "SendTaskResultTime"): "仅失败时",
                ("Notify", "IfSendMail"): True,
                ("Notify", "ToAddress"): "a@b.c",
            }
        )
        self._push(config, notify, message=_message(uncompleted=0))
        self.assertEqual(notify.mail_calls, [])

    def test_failure_only_setting_sends_on_failure(self) -> None:
        notify = _FakeNotify()
        config = _FakeConfig(
            {
                ("Notify", "SendTaskResultTime"): "仅失败时",
                ("Notify", "IfSendMail"): True,
                ("Notify", "ToAddress"): "a@b.c",
            }
        )
        self._push(config, notify, message=_message(uncompleted=1))
        self.assertEqual(len(notify.mail_calls), 1)
        kind, title, content, to_address = notify.mail_calls[0]
        self.assertEqual(kind, "网页")
        self.assertEqual(title, "标题")
        self.assertTrue(content.startswith("html:"))
        self.assertEqual(to_address, "a@b.c")

    def test_always_setting_fans_out_enabled_channels(self) -> None:
        notify = _FakeNotify()
        config = _FakeConfig(
            {
                ("Notify", "SendTaskResultTime"): "任何时刻",
                ("Notify", "IfServerChan"): True,
                ("Notify", "ServerChanKey"): "key",
                ("Notify", "IfKoishiSupport"): True,
            },
            webhooks={"w1": object()},
        )
        self._push(config, notify, message=_message(uncompleted=0))
        self.assertEqual(notify.mail_calls, [])
        self.assertEqual(len(notify.serverchan_calls), 1)
        self.assertIn("AUTO-MAS 敬上", notify.serverchan_calls[0][1])
        self.assertEqual(notify.serverchan_calls[0][2], "key")
        self.assertEqual(len(notify.webhook_calls), 1)
        self.assertEqual(len(notify.koishi_calls), 1)

    def test_other_modes_send_nothing(self) -> None:
        notify = _FakeNotify()
        config = _FakeConfig({("Notify", "SendTaskResultTime"): "任何时刻"})
        self._push(config, notify, mode="统计信息")
        self.assertEqual(notify.serverchan_calls, [])
        self.assertEqual(notify.webhook_calls, [])


if __name__ == "__main__":
    unittest.main()
