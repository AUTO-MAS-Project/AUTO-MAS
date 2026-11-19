"""applaunch 的 adb 执行器与启动等待: 失败时必须留下能查的线索。"""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace

from mumu_adapter import applaunch
from mumu_adapter.applaunch import build_adb_runner, ensure_app_running

#: 与真实 adb 等价的最小替身: 按 AdbRunner 契约永不抛异常, 只返回非 0 返回码。
BROKEN_ADB_OUTPUT = "[WinError 2] 系统找不到指定的文件。"


def _broken_runner() -> Callable[..., Awaitable[tuple[int, str]]]:
    async def run(*args: str, timeout: float | None = None) -> tuple[int, str]:
        return -1, BROKEN_ADB_OUTPUT

    return run


def _fake_offline_device(monkeypatch, adb_address: str) -> list[tuple[str, ...]]:
    """装一个假 adb: 连接是僵尸的, 只有「先失败过一次再断开重建」才能救回来。

    僵尸连接下预先 ``connect`` 会假成功、设备照样 offline——这就是两台 MuMu 互相顶掉
    5037 server 之后的真实现场。所以这里要求 ``disconnect`` 之前命令真的失败过一次,
    才能区分「命令失败后重连」和「命令还没发就先把连接拆了」。
    """
    calls: list[tuple[str, ...]] = []
    state = {"failed": False, "healthy": False}

    async def fake_run_process(program, *args, timeout=None, if_merge_std=False):
        calls.append(tuple(str(arg) for arg in args))
        if args[0] == "disconnect":
            state["healthy"] = state["failed"]
            return SimpleNamespace(returncode=0, stdout=f"disconnected {adb_address}")
        if args[0] == "connect":
            return SimpleNamespace(returncode=0, stdout="connected")
        if not state["healthy"]:
            state["failed"] = True
            # 与真实 adb 一致: offline 不带地址, not found 才带
            return SimpleNamespace(returncode=1, stdout="error: device offline")
        return SimpleNamespace(returncode=0, stdout="1")

    monkeypatch.setattr(applaunch.ProcessRunner, "run_process", fake_run_process)
    return calls


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
    assert applaunch.is_stale_connection("error: device offline")
    assert applaunch.is_stale_connection("adb.exe: device '127.0.0.1:16384' not found")
    assert applaunch.is_stale_connection(
        "cannot connect to 127.0.0.1:16384: 由于目标计算机积极拒绝"
    )
    assert not applaunch.is_stale_connection("1")
    assert not applaunch.is_stale_connection("")
    assert not applaunch.is_stale_connection(
        "package:/system/priv-app/Settings/Settings.apk"
    )


def test_shell_command_missing_is_not_a_stale_connection():
    """设备连得好好的、只是设备里没有某条命令时, 不能当成连接失效。

    雷电 14 的镜像里没有 ``monkey``, 正常连着的设备执行它只会打出
    ``/system/bin/sh: monkey: not found``; 按裸 ``not found`` 判就会把一条好连接
    断开重连, 还把命令重复执行一次。
    """
    assert not applaunch.is_stale_connection("/system/bin/sh: monkey: not found")
    assert not applaunch.is_stale_connection("/system/bin/sh: am: not found")
    assert not applaunch.is_stale_connection("sh: pm: not found")
    # 真掉线还是照样要认出来
    assert applaunch.is_stale_connection("error: device '127.0.0.1:16384' not found")
    assert applaunch.is_stale_connection("adb.exe: device 'emulator-5554' not found")
    assert applaunch.is_stale_connection("error: device not found")


def test_describe_adb_failure_only_speaks_for_stale_connections():
    """只有连接失效才给「换端口」的提示: adb 路径失效之类喂这句会把人带偏。"""
    hint = applaunch.describe_adb_failure("error: device offline")
    assert "端口" in hint
    assert applaunch.describe_adb_failure("") == ""
    assert applaunch.describe_adb_failure(BROKEN_ADB_OUTPUT) == ""


def test_runner_does_not_touch_connection_before_a_command_fails(monkeypatch):
    """设备本来就连着时, 第一条命令之前不能动连接。

    界面上在已经开着的模拟器里点「打开游戏中心」也会新建一个执行器; 若它先断开再连,
    别的东西在同一个 5037 server 上给这台设备建的 ``adb forward`` 就被删了, 后面的
    ``connect`` 也不恢复。预先断连还会把唯一一次故障重连的机会提前用掉。
    """
    calls: list[tuple[str, ...]] = []

    async def fake_run_process(program, *args, timeout=None, if_merge_std=False):
        calls.append(tuple(str(arg) for arg in args))
        return SimpleNamespace(returncode=0, stdout="1")

    monkeypatch.setattr(applaunch.ProcessRunner, "run_process", fake_run_process)
    runner = build_adb_runner(Path("adb.exe"), "127.0.0.1:16384")

    assert asyncio.run(runner("shell", "getprop", "sys.boot_completed")) == (0, "1")
    assert not [c for c in calls if c[0] in ("disconnect", "connect")]


def test_runner_recovers_stale_connection_with_default_cooldown(monkeypatch):
    """命令报 offline 时断开重连一次再重试, 默认冷却下也要能恢复。

    冷却只该在「重连过之后」起作用。首次建连若就占掉它, 设备在启动命令期间掉线时
    monkey 与 am start 都会落在断线里, 只剩前台轮询一直等到 launch-timeout。
    """
    calls = _fake_offline_device(monkeypatch, "127.0.0.1:16384")
    runner = build_adb_runner(Path("adb.exe"), "127.0.0.1:16384")

    assert asyncio.run(runner("shell", "getprop", "sys.boot_completed")) == (0, "1")
    # 僵尸连接只有断开重建才救得回来, 这条命令确实走了恢复路径
    assert "disconnect" in [c[0] for c in calls]


def test_runner_reconnect_native_serial_skips_connect(monkeypatch):
    """``emulator-5554`` 这类原生序列号不能用 ``connect`` 恢复, 断开一次让 server 重新扫到。"""
    calls = _fake_offline_device(monkeypatch, "emulator-5554")
    runner = build_adb_runner(Path("adb.exe"), "emulator-5554")

    assert asyncio.run(runner("shell", "getprop", "sys.boot_completed")) == (0, "1")
    assert [c[0] for c in calls if c[0] in ("disconnect", "connect")] == ["disconnect"]


def test_runner_does_not_reconnect_for_missing_shell_command(monkeypatch):
    """设备里缺命令不是连接失效: 不能断开重连, 更不能把命令重复执行一次。"""
    calls: list[tuple[str, ...]] = []

    async def fake_run_process(program, *args, timeout=None, if_merge_std=False):
        calls.append(tuple(str(arg) for arg in args))
        return SimpleNamespace(returncode=127, stdout="sh: monkey: not found")

    monkeypatch.setattr(applaunch.ProcessRunner, "run_process", fake_run_process)
    runner = build_adb_runner(Path("adb.exe"), "127.0.0.1:16384")

    code, output = asyncio.run(runner("shell", "monkey", "-p", "com.example.game", "1"))

    assert code == 127
    assert "monkey: not found" in output
    assert len(calls) == 1


def test_boot_timeout_detail_keeps_raw_error_unless_caller_asks_for_hint():
    """公共启动流程只带原始 adb 报错; 「关掉别的模拟器、换端口」由调用方决定加不加。

    ModAVD 走 ``modavd adb`` 的私有 server, 关机或换端口处理不了它的连接, 喂这句提示
    只会把人带偏。
    """

    async def stale_runner(*args: str, timeout: float | None = None):
        return 1, "error: device offline"

    raw = asyncio.run(
        ensure_app_running(
            stale_runner, "com.example.game", boot_timeout=0, launch_timeout=0
        )
    )
    hinted = asyncio.run(
        ensure_app_running(
            stale_runner,
            "com.example.game",
            boot_timeout=0,
            launch_timeout=0,
            failure_hint=applaunch.describe_adb_failure,
        )
    )

    assert raw.reason == "boot-timeout"
    assert "device offline" in raw.detail
    assert "端口" not in raw.detail
    assert "端口" in hinted.detail


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
