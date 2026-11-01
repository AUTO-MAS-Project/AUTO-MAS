"""core.Notify 是进程共享的管理器，导入不装配渠道或连接。"""

import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest


def isolated(code: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, result.stderr


def test_core_notify_is_shared_instance_without_channel_initialization():
    isolated("""
import sys
from app.core import Notify
from app.core.notify import Notify as direct
from app.core.notify.manager import NotificationManager
assert isinstance(Notify, NotificationManager)
assert Notify is direct
assert "_transport" not in Notify.__dict__
assert "_renderer" not in Notify.__dict__
assert "windows_toasts" not in sys.modules
assert "plyer" not in sys.modules
""")


def test_notification_transport_can_initialize_without_api_routes():
    isolated("""
import importlib.abc
import sys
from types import SimpleNamespace
from unittest.mock import Mock

class RejectAPI(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "app.api" or fullname.startswith("app.api."):
            raise AssertionError(f"notification transport imported {fullname}")

sys.meta_path.insert(0, RejectAPI())
from app.core.notify import manager
registry = SimpleNamespace(by_id={}, bind=Mock(return_value=object()))
manager._get_registry = lambda: registry
notify = manager.NotificationManager()
assert notify._transport is notify._transport
registry.bind.assert_called_once()
""")


def test_api_consumers_share_singleton_and_manifests_keep_canonical_paths():
    isolated("""
from app.core import Notify
from app.api import setting, openclaw_qq
from app.api.community import accounts
assert setting.Notify is accounts.Notify is openclaw_qq.Notify is Notify
assert "_transport" not in Notify.__dict__
from app.core.notify.channels.discovery import discover_channels
manifests, errors = discover_channels()
assert manifests and not errors
assert all(m.entrypoint.startswith("app.core.notify.channels.") for m in manifests)
""")


@pytest.mark.asyncio
async def test_global_manager_prepares_channels_once_and_close_does_not_recreate(
    monkeypatch,
):
    from app.core import Notify
    from app.core.notify import manager

    channels = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    registry = SimpleNamespace(by_id={}, bind=Mock(return_value=channels))
    monkeypatch.setattr(manager, "_get_registry", lambda: registry)
    with patch.dict(Notify.__dict__, clear=True):
        await Notify.start()
        await Notify.start()
        registry.bind.assert_called_once()
        await Notify.close()
        await Notify.close()
        channels.stop.assert_awaited_once()
        registry.bind.assert_called_once()
        assert "_transport" not in Notify.__dict__
        assert "_renderer" not in Notify.__dict__


@pytest.mark.asyncio
async def test_global_system_notice_survives_disconnection_and_flushes(monkeypatch):
    from app.core import Config, Notify, Publisher

    monkeypatch.setattr(Config, "startup_notices", [])
    send = AsyncMock(return_value=False)
    monkeypatch.setattr(Publisher, "send", send)
    await Notify.push_system_notice(
        level="warning", title="初始化提示", lines=["待连接"]
    )
    assert len(Config.startup_notices) == 1
    send.return_value = True
    await Notify.flush_startup_notices()
    assert Config.startup_notices == []
    await Notify.flush_startup_notices()
    assert send.await_count == 2
