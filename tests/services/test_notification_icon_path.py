"""app/services/notification.py 系统通知图标路径的源码相对解析回归测试。

图标是随源码分发的内置资源（res/icons/），受监督布局下工作目录与源码目录
分离，路径必须仍按源码位置解析，不能被误解析到当前工作目录（该目录下不
存在该文件，plyer 会静默用不上图标）。
"""

import asyncio
from pathlib import Path

import pytest

from app.services import notification as notification_module


def test_push_plyer_icon_path_survives_cwd_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    class _FakeConfig:
        def get(self, *_args, **_kwargs) -> bool:
            return True

    captured: dict = {}

    def fake_notify(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(notification_module, "Config", _FakeConfig())
    monkeypatch.setattr(notification_module.notification, "notify", fake_notify)

    asyncio.run(notification_module.Notify.push_plyer("标题", "内容", "横幅", 5))

    assert Path(captured["app_icon"]).is_file()
