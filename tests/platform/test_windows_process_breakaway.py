"""Windows 进程平台层在受 AUTO-MAS-Runtime Job Object 监督下的脱离行为。

后端启动模拟器/游戏等外部进程时，这些进程不应随后端一起被监督器的
``KILL_ON_JOB_CLOSE`` Job 回收——今天的用户可见行为是「关掉 AUTO-MAS 不关
游戏」，必须保持。做法是给 ``creationflags`` 叠加
``CREATE_BREAKAWAY_FROM_JOB``；但父进程若恰好处在一个不允许 breakaway 的
Job 里，带这个标志的 ``CreateProcess`` 会以 ``ERROR_ACCESS_DENIED``
（WinError 5）失败，因此 ``ProcessManager.open_process`` 必须在这种情况下
去掉该标志重试一次。

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


def test_windows_creation_flags_include_breakaway_from_job() -> None:
    from app.utils.platform.windows.process import WindowsProcessPlatform

    breakaway = subprocess.CREATE_BREAKAWAY_FROM_JOB

    assert WindowsProcessPlatform.creation_flags & breakaway
    assert WindowsProcessPlatform.detached_flags & breakaway
    # DETACHED_PROCESS 本身不会让子进程脱离 Job，必须叠加
    # CREATE_BREAKAWAY_FROM_JOB 才行——两者都要在，防止以后有人以为
    # DETACHED_PROCESS 已经处理了这件事而把 breakaway 位删掉。
    assert WindowsProcessPlatform.detached_flags & subprocess.DETACHED_PROCESS


def test_open_process_retries_without_breakaway_on_access_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.utils.platform.common.process import ProcessManager

    breakaway = subprocess.CREATE_BREAKAWAY_FROM_JOB
    calls: list[dict] = []
    sentinel_process = object()

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            # 模拟父进程所在 Job 不允许 breakaway 时 CreateProcess 的失败
            err = PermissionError("[WinError 5] 拒绝访问。")
            err.winerror = 5
            raise err
        return sentinel_process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    manager = ProcessManager()
    asyncio.run(manager.open_process("C:/fake/does-not-exist/game.exe"))

    assert len(calls) == 2
    first_flags = calls[0]["creationflags"]
    second_flags = calls[1]["creationflags"]
    assert first_flags & breakaway, "第一次必须带 breakaway 位"
    assert not (second_flags & breakaway), "重试必须去掉 breakaway 位"
    assert first_flags & ~breakaway == second_flags, "除 breakaway 位外其余标志不变"
    assert manager.process is sentinel_process, "重试成功后结果要正常传播"


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

    manager = ProcessManager()
    with pytest.raises(FileNotFoundError):
        asyncio.run(manager.open_process("C:/fake/does-not-exist/game.exe"))

    assert len(calls) == 1, "非 breakaway-拒绝的失败不应该重试"
