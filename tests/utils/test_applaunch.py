"""applaunch 的 adb 执行器与启动等待: 失败时必须留下能查的线索。"""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace

from app.utils.common.emulator2 import applaunch
from app.utils.common.emulator2.applaunch import build_adb_runner, ensure_app_running

#: 与真实 adb 等价的最小替身: 按 AdbRunner 契约永不抛异常, 只返回非 0 返回码。
BROKEN_ADB_OUTPUT = "[WinError 2] 系统找不到指定的文件。"


def _broken_runner() -> Callable[..., Awaitable[tuple[int, str]]]:
    async def run(*args: str, timeout: float | None = None) -> tuple[int, str]:
        return -1, BROKEN_ADB_OUTPUT

    return run


def test_boot_timeout_carries_last_adb_result():
    """等不到开机完成时要把最后一次 adb 返回带出去。

    没有这条时日志里只有一句「等待系统启动完成超时」: 系统真的没起完和 adb 命令压根
    执行不了(路径失效之类)是同一句话, 现场分不出是哪种。
    """
    result = asyncio.run(
        ensure_app_running(
            _broken_runner(), "com.example.game", boot_timeout=0, launch_timeout=0
        )
    )

    assert not result.ok
    assert result.reason == "boot-timeout"
    assert "-1" in result.detail
    assert BROKEN_ADB_OUTPUT in result.detail


def test_missing_adb_returns_error_code_and_logs_once(tmp_path: Path, monkeypatch):
    """adb 执行不了要返回错误码而不是抛异常, 且同一段轮询里只记一条 warning。"""
    recorded: list[str] = []
    monkeypatch.setattr(applaunch, "logger", SimpleNamespace(warning=recorded.append))
    runner = build_adb_runner(tmp_path / "adb.exe", "")

    code, output = asyncio.run(runner("shell", "getprop", "sys.boot_completed"))
    asyncio.run(runner("shell", "getprop", "sys.boot_completed"))

    assert code == -1
    assert output
    assert len(recorded) == 1
