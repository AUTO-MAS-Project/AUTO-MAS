"""Windows 进程平台层在受 AUTO-MAS-Runtime Job Object 监督下的脱离行为。

后端被监督器的 ``KILL_ON_JOB_CLOSE`` Job 管着时，子进程默认必须留在 Job
里（MAA.exe、脚本进程、agent、taskkill/schtasks 等），后端被硬杀或宿主崩溃
时才能被一并回收；只有游戏/模拟器这类不该随后端退出的进程（Runtime 契约
C8）才由调用点显式传 ``breakaway=True``，叠加 ``CREATE_BREAKAWAY_FROM_JOB``。
父进程若恰好处在一个不允许 breakaway 的 Job 里，带这个标志的
``CreateProcess`` 会以 ``ERROR_ACCESS_DENIED``（WinError 5）失败，
``ProcessManager.open_process`` 与 ``ProcessRunner.run_process`` 都必须在这种
情况下去掉该标志重试一次。

本文件只覆盖 Windows 上的行为，非 Windows 平台整体跳过：
``subprocess.CREATE_BREAKAWAY_FROM_JOB``/``WindowsProcessPlatform`` 都只在
Windows 上存在，模块顶层不引用它们，全部延迟到测试函数体内导入，避免非
Windows 平台连收集（collect）这个文件都失败。
"""

import asyncio
import os
import subprocess

import pytest


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Job Object 脱离仅 Windows 概念")


class _FakeProcess:
    """够 ProcessRunner.run_process 走完 communicate/returncode 的最小桩。"""

    returncode = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", b""

    async def wait(self) -> int:
        return self.returncode


def _access_denied() -> PermissionError:
    """模拟父进程所在 Job 不允许 breakaway 时 CreateProcess 的失败。"""

    err = PermissionError("[WinError 5] 拒绝访问。")
    err.winerror = 5
    return err


def _install_fake_spawn(
    monkeypatch: pytest.MonkeyPatch, *, deny_first: bool = False
) -> list[dict]:
    calls: list[dict] = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append(kwargs)
        if deny_first and len(calls) == 1:
            raise _access_denied()
        return _FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    return calls


def test_windows_creation_flags_split_base_and_breakaway() -> None:
    from app.utils.platform.windows.process import WindowsProcessPlatform

    breakaway = subprocess.CREATE_BREAKAWAY_FROM_JOB

    # 基础标志不带脱离位——默认子进程留在监督器的 Job 里。
    assert not (WindowsProcessPlatform.creation_flags & breakaway)
    assert WindowsProcessPlatform.breakaway_flags == breakaway
    # 自更新安装程序要活过后端退出，detached_flags 固定带脱离位。
    # DETACHED_PROCESS 本身不会让子进程脱离 Job，必须叠加
    # CREATE_BREAKAWAY_FROM_JOB 才行——两者都要在，防止以后有人以为
    # DETACHED_PROCESS 已经处理了这件事而把 breakaway 位删掉。
    assert WindowsProcessPlatform.detached_flags & breakaway
    assert WindowsProcessPlatform.detached_flags & subprocess.DETACHED_PROCESS


# ---------------------------------------------------------------- open_process


def test_open_process_default_stays_in_job(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.utils.platform.common.process import ProcessManager
    from app.utils.platform.windows.process import WindowsProcessPlatform

    calls = _install_fake_spawn(monkeypatch)

    asyncio.run(ProcessManager().open_process("C:/fake/does-not-exist/MAA.exe"))

    assert len(calls) == 1
    assert not (calls[0]["creationflags"] & subprocess.CREATE_BREAKAWAY_FROM_JOB)
    assert calls[0]["creationflags"] == WindowsProcessPlatform.creation_flags


def test_open_process_breakaway_adds_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.utils.platform.common.process import ProcessManager
    from app.utils.platform.windows.process import WindowsProcessPlatform

    calls = _install_fake_spawn(monkeypatch)

    asyncio.run(
        ProcessManager().open_process(
            "C:/fake/does-not-exist/game.exe", breakaway=True
        )
    )

    assert len(calls) == 1
    assert calls[0]["creationflags"] == (
        WindowsProcessPlatform.creation_flags | subprocess.CREATE_BREAKAWAY_FROM_JOB
    )


def test_open_process_retries_without_breakaway_on_access_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.utils.platform.common.process import ProcessManager

    breakaway = subprocess.CREATE_BREAKAWAY_FROM_JOB
    calls = _install_fake_spawn(monkeypatch, deny_first=True)

    manager = ProcessManager()
    asyncio.run(manager.open_process("C:/fake/does-not-exist/game.exe", breakaway=True))

    assert len(calls) == 2
    first_flags = calls[0]["creationflags"]
    second_flags = calls[1]["creationflags"]
    assert first_flags & breakaway, "第一次必须带 breakaway 位"
    assert not (second_flags & breakaway), "重试必须去掉 breakaway 位"
    assert first_flags & ~breakaway == second_flags, "除 breakaway 位外其余标志不变"
    assert isinstance(manager.process, _FakeProcess), "重试成功后结果要正常传播"


def test_open_process_default_does_not_retry_on_access_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没带 breakaway 位时的 WinError 5 不是「breakaway 被拒」，不能重试吞掉。"""

    from app.utils.platform.common.process import ProcessManager

    calls = _install_fake_spawn(monkeypatch, deny_first=True)

    with pytest.raises(PermissionError):
        asyncio.run(ProcessManager().open_process("C:/fake/does-not-exist/MAA.exe"))

    assert len(calls) == 1


def test_open_process_does_not_retry_on_unrelated_os_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不是「breakaway 被拒」的失败要照常往外抛，不能被这层兜底吞掉。"""

    from app.utils.platform.common.process import ProcessManager

    calls: list[dict] = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append(kwargs)
        raise FileNotFoundError(2, "系统找不到指定的文件。")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(FileNotFoundError):
        asyncio.run(
            ProcessManager().open_process(
                "C:/fake/does-not-exist/game.exe", breakaway=True
            )
        )

    assert len(calls) == 1, "非 breakaway-拒绝的失败不应该重试"


# ----------------------------------------------------------------- run_process


def test_run_process_default_stays_in_job(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.utils.platform.common.process_runner import ProcessRunner
    from app.utils.platform.windows.process import WindowsProcessPlatform

    calls = _install_fake_spawn(monkeypatch)

    result = asyncio.run(ProcessRunner.run_process("taskkill", "/F", "/PID", "1"))

    assert result.returncode == 0
    assert len(calls) == 1
    assert not (calls[0]["creationflags"] & subprocess.CREATE_BREAKAWAY_FROM_JOB)
    assert calls[0]["creationflags"] == WindowsProcessPlatform.creation_flags


def test_run_process_breakaway_adds_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.utils.platform.common.process_runner import ProcessRunner
    from app.utils.platform.windows.process import WindowsProcessPlatform

    calls = _install_fake_spawn(monkeypatch)

    asyncio.run(
        ProcessRunner.run_process(
            "C:/fake/does-not-exist/MuMuManager.exe", "control", breakaway=True
        )
    )

    assert len(calls) == 1
    assert calls[0]["creationflags"] == (
        WindowsProcessPlatform.creation_flags | subprocess.CREATE_BREAKAWAY_FROM_JOB
    )


def test_run_process_retries_without_breakaway_on_access_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.utils.platform.common.process_runner import ProcessRunner

    breakaway = subprocess.CREATE_BREAKAWAY_FROM_JOB
    calls = _install_fake_spawn(monkeypatch, deny_first=True)

    result = asyncio.run(
        ProcessRunner.run_process(
            "C:/fake/does-not-exist/MuMuManager.exe", "control", breakaway=True
        )
    )

    assert result.returncode == 0, "重试成功后结果要正常传播"
    assert len(calls) == 2
    first_flags = calls[0]["creationflags"]
    second_flags = calls[1]["creationflags"]
    assert first_flags & breakaway, "第一次必须带 breakaway 位"
    assert not (second_flags & breakaway), "重试必须去掉 breakaway 位"
    assert first_flags & ~breakaway == second_flags, "除 breakaway 位外其余标志不变"
