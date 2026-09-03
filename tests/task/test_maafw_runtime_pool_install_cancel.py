"""MaaFW 运行池安装步骤对取消的响应。

后端关机时任务被取消，而环境准备可能正卡在 uv 装依赖：取消必须传进安装线程，
终止正在跑的子进程并在有限时间内返回；被打断的半成品 runtime 不能发布
（manifest 只在安装完整成功后写入，staging 目录被池删掉）。
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from app.task.MaaFW.tools.core.automas_maafw_runtime_pool import installer
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.installer import (
    MaaFWRuntimeInstallCancelled,
    install_cancel_scope,
)
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.pool import (
    RUNTIME_MANIFEST_NAME,
    MaaFWRuntimePool,
)

_SLEEP_COMMAND = [sys.executable, "-c", "import time; time.sleep(30)"]


def _set_after(event: threading.Event, delay: float) -> threading.Thread:
    thread = threading.Thread(target=lambda: (time.sleep(delay), event.set()))
    thread.daemon = True
    thread.start()
    return thread


def test_run_terminates_subprocess_within_two_seconds_after_cancel(
    tmp_path: Path,
) -> None:
    cancel_event = threading.Event()
    _set_after(cancel_event, 0.3)

    started = time.monotonic()
    with install_cancel_scope(cancel_event):
        with pytest.raises(MaaFWRuntimeInstallCancelled):
            installer._run(_SLEEP_COMMAND, cwd=tmp_path, timeout=30)
    elapsed = time.monotonic() - started

    # 0.3 秒后置位 + 至多 2 秒收尸；子进程本身要睡 30 秒，没被杀就不可能这么快。
    assert elapsed < 0.3 + installer.INSTALL_CANCEL_TERMINATE_TIMEOUT_SECONDS + 0.5


def test_run_refuses_to_start_when_already_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cancel_event = threading.Event()
    cancel_event.set()
    calls: list[list[str]] = []

    def fake_popen(command, **kwargs):  # noqa: ANN001 - 只记录调用
        calls.append(list(command))
        raise AssertionError("已取消时不应再启动子进程")

    monkeypatch.setattr(installer.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(installer.subprocess, "run", fake_popen)
    with install_cancel_scope(cancel_event):
        with pytest.raises(MaaFWRuntimeInstallCancelled):
            installer._run(_SLEEP_COMMAND, cwd=tmp_path, timeout=30)
    assert calls == []


def test_run_without_cancel_scope_keeps_plain_subprocess_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001 - 打桩
        seen["command"] = list(command)
        seen["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(command, 3, "", "boom")

    monkeypatch.setattr(installer.subprocess, "run", fake_run)
    assert installer.current_install_cancel_event() is None
    with pytest.raises(RuntimeError, match="exit=3"):
        installer._run(["uv", "pip", "install", "x"], cwd=tmp_path, timeout=7)
    assert seen == {"command": ["uv", "pip", "install", "x"], "timeout": 7}


def test_cancel_scope_is_restored_after_exit() -> None:
    event = threading.Event()
    assert installer.current_install_cancel_event() is None
    with install_cancel_scope(event):
        assert installer.current_install_cancel_event() is event
    assert installer.current_install_cancel_event() is None


def test_cancelled_install_leaves_no_runtime_and_no_staging(tmp_path: Path) -> None:
    pool = MaaFWRuntimePool(tmp_path / "pool")
    cancel_event = threading.Event()
    seen_paths: list[Path] = []

    def cancelled_installer(environment_path: Path, requirements, identity):  # noqa: ANN001
        # 模拟装到一半时取消：目录里已经有半成品，随后安装步骤看到令牌抛出。
        seen_paths.append(environment_path)
        environment_path.mkdir(parents=True)
        (environment_path / "half-installed.marker").write_text("x", encoding="utf-8")
        cancel_event.set()
        with install_cancel_scope(cancel_event):
            installer.raise_if_install_cancelled()
        raise AssertionError("置位后的令牌必须让安装步骤抛出")

    with pytest.raises(MaaFWRuntimeInstallCancelled):
        pool.ensure(["maafw==5.12.3"], installer=cancelled_installer)

    assert len(seen_paths) == 1
    stage_dir = seen_paths[0].parent
    assert not stage_dir.exists(), "半成品 staging 目录必须被删掉"
    assert pool.list() == []
    manifests = list((tmp_path / "pool").rglob(RUNTIME_MANIFEST_NAME))
    assert manifests == [], "被取消的安装不能留下 manifest"
