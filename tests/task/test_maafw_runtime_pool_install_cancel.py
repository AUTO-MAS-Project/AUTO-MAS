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


# ---------------------------------------------------------------------------
# 镜像源轮换路径：受监督时装依赖走的是 _run_with_source_rotation，
# 它必须和 _run 一样吃到取消令牌，并且取消不能被当成「换下一个源」。
# ---------------------------------------------------------------------------

_ROTATION_SOURCES = ("https://mirror-a.invalid", "https://mirror-b.invalid", "https://mirror-c.invalid")


def test_source_rotation_terminates_subprocess_within_two_seconds_after_cancel(
    tmp_path: Path,
) -> None:
    cancel_event = threading.Event()
    attempted: list[str | None] = []

    def build_command(source: str | None) -> list[str]:
        attempted.append(source)
        return _SLEEP_COMMAND

    _set_after(cancel_event, 0.3)
    started = time.monotonic()
    with install_cancel_scope(cancel_event):
        with pytest.raises(MaaFWRuntimeInstallCancelled):
            installer._run_with_source_rotation(
                build_command,
                _ROTATION_SOURCES,
                cwd=tmp_path,
                build_env=lambda _source: None,
                timeout=30,
                failure_label="测试安装",
            )
    elapsed = time.monotonic() - started

    # 子进程要睡 30 秒；三个候选源若被逐个试过会更久。0.3 秒后置位 + 至多 2 秒收尸。
    assert elapsed < 0.3 + installer.INSTALL_CANCEL_TERMINATE_TIMEOUT_SECONDS + 0.5
    assert attempted == [_ROTATION_SOURCES[0]], "取消后不得再尝试后续镜像源"


def test_source_rotation_does_not_treat_cancel_as_source_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls: list[list[str]] = []

    def cancelled_run(command, **kwargs):  # noqa: ANN001 - 打桩
        calls.append(list(command))
        raise MaaFWRuntimeInstallCancelled("stub cancelled")

    monkeypatch.setattr(installer, "_run_subprocess", cancelled_run)
    with caplog.at_level("WARNING", logger=installer.logger.name):
        with pytest.raises(MaaFWRuntimeInstallCancelled, match="stub cancelled"):
            installer._run_with_source_rotation(
                lambda source: ["uv", "pip", "install", "--index-url", str(source)],
                _ROTATION_SOURCES,
                cwd=tmp_path,
                build_env=lambda _source: {},
                timeout=30,
                failure_label="测试安装",
            )

    assert len(calls) == 1, "取消必须原样穿透，不能换源重试"
    assert calls[0][-1] == _ROTATION_SOURCES[0]
    assert not any("换下一个源重试" in record.getMessage() for record in caplog.records)


def test_source_rotation_refuses_to_start_when_already_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cancel_event = threading.Event()
    cancel_event.set()
    started: list[list[str]] = []

    def fake_start(command, **kwargs):  # noqa: ANN001 - 只记录调用
        started.append(list(command))
        raise AssertionError("已取消时不应再启动子进程")

    monkeypatch.setattr(installer.subprocess, "Popen", fake_start)
    monkeypatch.setattr(installer.subprocess, "run", fake_start)
    with install_cancel_scope(cancel_event):
        with pytest.raises(MaaFWRuntimeInstallCancelled):
            installer._run_with_source_rotation(
                lambda _source: _SLEEP_COMMAND,
                _ROTATION_SOURCES,
                cwd=tmp_path,
                build_env=lambda _source: None,
                timeout=30,
                failure_label="测试安装",
            )
    assert started == []


def test_uv_requirements_install_with_index_rotation_propagates_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """真实调用方 ``_install_requirements_with_uv`` 在多镜像源下也只试一次。"""

    monkeypatch.delenv("UV_INDEX_URL", raising=False)
    monkeypatch.delenv("UV_DEFAULT_INDEX", raising=False)
    monkeypatch.delenv(installer.AUTO_MAS_UV_INDEX_URL_ENV, raising=False)
    monkeypatch.setenv(
        installer.AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV, ";".join(_ROTATION_SOURCES)
    )
    cancel_event = threading.Event()
    attempted: list[list[str]] = []

    def cancelled_run(command, **kwargs):  # noqa: ANN001 - 打桩
        attempted.append(list(command))
        installer.raise_if_install_cancelled()
        raise AssertionError("令牌已置位时打桩不应走到这里")

    monkeypatch.setattr(installer, "_run_subprocess", cancelled_run)
    cancel_event.set()
    with install_cancel_scope(cancel_event):
        with pytest.raises(MaaFWRuntimeInstallCancelled):
            installer._install_requirements_with_uv(
                "uv.exe",
                tmp_path / "envs" / "shared" / "Scripts" / "python.exe",
                ["maafw==1.0"],
                cache_dir=tmp_path / "cache",
                link_mode="hardlink",
                cwd=tmp_path,
            )

    assert len(attempted) == 1
    assert attempted[0][attempted[0].index("--index-url") + 1] == _ROTATION_SOURCES[0]
