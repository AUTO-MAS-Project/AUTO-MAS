"""applaunch 的 adb 执行器与启动等待: 失败时必须留下能查的线索。"""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace

from app.utils.common.emulator2 import applaunch
from app.utils.common.emulator2.applaunch import (
    build_adb_runner,
    describe_adb_failure,
    ensure_app_running,
    is_stale_connection,
)

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


def test_stale_connection_is_recognised():
    """连接失效的几种写法都要认出来, 正常输出一个都不能误判。"""
    assert is_stale_connection("error: device offline")
    assert is_stale_connection("adb.exe: device '127.0.0.1:16384' not found")
    assert is_stale_connection(
        "cannot connect to 127.0.0.1:16384: 由于目标计算机积极拒绝"
    )
    assert not is_stale_connection("1")
    assert not is_stale_connection("")
    assert not is_stale_connection("package:/system/priv-app/Settings/Settings.apk")


def test_describe_adb_failure_only_speaks_for_stale_connections():
    """只有连接失效才给「换端口」的提示: adb 路径失效之类喂这句会把人带偏。"""
    hint = describe_adb_failure("error: device offline")
    assert "端口" in hint
    assert describe_adb_failure("") == ""
    assert describe_adb_failure(BROKEN_ADB_OUTPUT) == ""


def test_runner_reconnects_and_retries_when_connection_is_stale(monkeypatch):
    """命令报 offline 时要 disconnect+connect 重建一次再重试, 而不是把失败丢给上层。

    两台 MuMu 共用 5037 时 server 里会留着指向旧实例的连接, 此时 connect 直接回
    成功、每条命令却都报 offline——只靠每秒轮询永远等不到开机完成。
    """
    monkeypatch.setattr(applaunch, "_RECONNECT_COOLDOWN", 0.0)
    calls: list[tuple[str, ...]] = []
    shell_outputs = iter(["error: device offline", "1"])

    async def fake_run_process(program, *args, timeout=None, if_merge_std=False):
        calls.append((str(program), *args))
        if "shell" in args:
            return SimpleNamespace(returncode=0, stdout=next(shell_outputs))
        return SimpleNamespace(returncode=0, stdout="connected")

    monkeypatch.setattr(applaunch.ProcessRunner, "run_process", fake_run_process)
    runner = build_adb_runner(Path("adb.exe"), "127.0.0.1:16384")

    code, output = asyncio.run(runner("shell", "getprop", "sys.boot_completed"))

    assert (code, output) == (0, "1")
    # 首次连接一次 + 发现失效后重连一次
    assert [c[1] for c in calls].count("disconnect") == 2
    assert [c[1] for c in calls].count("connect") == 2


def test_boot_timeout_detail_carries_port_hint():
    """连不上时 detail 要带上「端口被占」的提示, 弹窗里才说得清下一步做什么。"""

    async def stale_runner(*args: str, timeout: float | None = None):
        return 1, "error: device offline"

    result = asyncio.run(
        ensure_app_running(
            stale_runner, "com.example.game", boot_timeout=0, launch_timeout=0
        )
    )

    assert not result.ok
    assert result.reason == "boot-timeout"
    assert "device offline" in result.detail
    assert "端口" in result.detail


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
