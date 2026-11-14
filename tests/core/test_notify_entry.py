"""断连期间的系统通知在连接恢复后继续交付。"""

import os
import subprocess
import sys
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_global_system_notice_survives_disconnection_and_flushes(monkeypatch):
    from app.core import Config, Notify, Publisher

    monkeypatch.setattr(Config, "startup_notices", [])
    send = AsyncMock(return_value=False)
    monkeypatch.setattr(Publisher, "send", send)
    await Notify.push_system_notice(
        level="warning",
        title="初始化提示",
        lines=["待连接"],
        title_key="core.setting.func.scheduledWakeupFailure",
        line_keys=["core.setting.func.scheduledWakeupFailureTip"],
    )
    assert len(Config.startup_notices) == 1
    send.return_value = True
    await Notify.flush_startup_notices()
    assert Config.startup_notices == []
    data = send.await_args.kwargs["data"]
    assert data.titleKey == "core.setting.func.scheduledWakeupFailure"
    assert data.lineKeys == ["core.setting.func.scheduledWakeupFailureTip"]
    await Notify.flush_startup_notices()
    assert send.await_count == 2


def test_sdk_exports_host_notify_without_plugin_binding():
    """验证 SDK 直接导出宿主通知单例，插件无需额外绑定通知包装器。"""
    code = """
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd() / "plugins/auto_mas_core/src"))
from app.core import Notify, Plugin
from app.core.plugin import Plugin as direct_plugin
from app.core.plugin.manager import _PluginManager
from auto_mas_core.notify import Notify as sdk_notify
from auto_mas_core.services import Notify as service_notify
from auto_mas_core import Plugin as sdk_plugin
from app.plugin.base import BasePlugin
assert sdk_notify is service_notify is Notify
assert sdk_plugin is direct_plugin is Plugin
assert isinstance(Plugin, _PluginManager)
assert not hasattr(BasePlugin, "bind_notifications")
assert not hasattr(BasePlugin(), "notifications")
assert "_transport" not in Notify.__dict__
assert "app.core.plugin_manager" not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
