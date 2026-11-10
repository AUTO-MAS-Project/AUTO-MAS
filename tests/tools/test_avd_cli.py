"""modavd CLI 的 JSON、选路、状态与时限契约测试。"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

import pytest
from loguru import logger as loguru_logger

from app.core.emulator_manager.operations import EmulatorOperations
from app.models.emulator import DeviceStatus, EmulatorRuntimePolicy
from app.utils.common.emulator2 import detect
from app.utils.common.emulator2.avd import cli as cli_module
from app.utils.common.emulator2.avd import host as host_module
from app.utils.common.emulator2.avd import manager as manager_module
from app.utils.common.emulator2.avd import service as service_module
from app.utils.common.emulator2.avd import updater as updater_module
from app.utils.common.emulator2.avd.cli import (
    CREATE_PROCESS_MARGIN_SECONDS,
    CREATE_TIMEOUT_SECONDS,
    CLIError,
    ModAvdCli,
    ModAvdUnavailable,
    ProcessOutput,
    _run_process,
    resolve_cli,
)
from app.utils.common.emulator2.avd.manager import _AvdCore
from app.utils.common.process.scope import TaskProcessScope, current_process_scope


@pytest.mark.asyncio
async def test_create_retries_without_timeout_for_v01_usage_error(
    tmp_path: Path,
) -> None:
    calls: list[tuple[list[str], float]] = []
    outputs = [
        ProcessOutput(0, '{"ok":true,"data":{"instances":[]}}', ""),
        ProcessOutput(
            2,
            '{"ok":false,"error":{"code":"usage","message":"命令 create 没有选项 --timeout"}}',
            "",
        ),
        ProcessOutput(0, '{"ok":true,"data":{"index":7}}', ""),
    ]

    async def runner(
        args: Sequence[str], timeout: float, timeout_handler: object, breakaway: bool
    ) -> ProcessOutput:
        calls.append((list(args), timeout))
        return outputs.pop(0)

    cli = ModAvdCli(tmp_path, exe=sys.executable, runner=runner)
    assert await cli.create(index=7) == {"index": 7}
    # 先 list 记下新建前就在的实例，超时收尾时不会把它们当成这次建的
    assert calls[0][0][4:] == ["list"]
    assert "--timeout" in calls[1][0]
    assert "--timeout" not in calls[2][0]
    assert (
        calls[1][1]
        == calls[2][1]
        == CREATE_TIMEOUT_SECONDS + CREATE_PROCESS_MARGIN_SECONDS
    )


@pytest.mark.asyncio
async def test_real_fake_modavd_program_keeps_json_and_stderr_separate(
    tmp_path: Path,
) -> None:
    script = tmp_path / "fake_modavd.py"
    script.write_text(
        "import json, sys\n"
        "print('fake log', file=sys.stderr)\n"
        "print(json.dumps({'ok': True, 'data': {'instances': []}}, ensure_ascii=False))\n",
        encoding="utf-8",
    )
    exe = Path(sys.executable)

    async def runner(
        args: Sequence[str],
        timeout: float,
        timeout_handler: object,
        breakaway: bool,
    ) -> ProcessOutput:
        del timeout, timeout_handler, breakaway
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script),
            *list(args)[1:],
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return ProcessOutput(
            process.returncode or 0,
            stdout.decode("utf-8"),
            stderr.decode("utf-8"),
        )

    result = await ModAvdCli(tmp_path, exe=exe, runner=runner).list()

    assert result == {"instances": []}


@pytest.mark.asyncio
async def test_run_process_uses_separate_streams_and_devnull_stdin(
    tmp_path: Path,
) -> None:
    script = tmp_path / "fake.py"
    script.write_text(
        "import sys\n"
        "data = sys.stdin.buffer.read()\n"
        "print('out:' + str(len(data)))\n"
        "print('err', file=sys.stderr)\n",
        encoding="utf-8",
    )
    output = await _run_process([sys.executable, str(script)], timeout=5)
    assert output.returncode == 0
    assert output.stdout.strip() == "out:0"
    assert output.stderr.strip() == "err"


@pytest.mark.asyncio
async def test_run_process_timeout_calls_cleanup_before_kill(tmp_path: Path) -> None:
    script = tmp_path / "sleep.py"
    script.write_text("import time; time.sleep(60)\n", encoding="utf-8")
    alive_at_cleanup: list[bool] = []

    async def cleanup(process: asyncio.subprocess.Process) -> None:
        alive_at_cleanup.append(process.returncode is None)

    with pytest.raises(CLIError) as exc_info:
        await _run_process(
            [sys.executable, str(script)], timeout=0.05, timeout_handler=cleanup
        )
    # 收尾时 CLI 进程还活着：先收尾、后结束进程
    assert alive_at_cleanup == [True]
    assert exc_info.value.code == "timeout"


@pytest.mark.asyncio
async def test_resolve_cli_caches_version_and_rejects_bad_protocol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = tmp_path / "tools" / "modavd.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(Path(sys.executable).read_bytes())
    calls = 0

    async def version(self: ModAvdCli) -> dict:
        nonlocal calls
        calls += 1
        return {"version": "0.36.0", "protocol": 1}

    monkeypatch.setattr(ModAvdCli, "version", version)
    assert await resolve_cli(tmp_path) is not None
    assert await resolve_cli(tmp_path) is not None
    assert calls == 1

    bad_root = tmp_path / "bad"
    bad_exe = bad_root / "tools" / "modavd.exe"
    bad_exe.parent.mkdir(parents=True)
    bad_exe.write_bytes(Path(sys.executable).read_bytes())

    async def bad_version(self: ModAvdCli) -> dict:
        return {"version": "0.36.0", "protocol": 999}

    monkeypatch.setattr(ModAvdCli, "version", bad_version)
    with pytest.raises(ModAvdUnavailable, match="协议 999"):
        await resolve_cli(bad_root)


@pytest.mark.asyncio
async def test_resolve_cli_does_not_cache_transient_version_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = tmp_path / "tools" / "modavd.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(Path(sys.executable).read_bytes())
    calls = 0

    async def version(self: ModAvdCli) -> dict:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise CLIError("timeout", "暂时超时")
        return {"version": "0.2.0", "protocol": 1}

    monkeypatch.setattr(ModAvdCli, "version", version)
    with pytest.raises(ModAvdUnavailable):
        await resolve_cli(tmp_path)
    assert await resolve_cli(tmp_path) is not None
    assert calls == 2


class _FakeManagerCli:
    def __init__(self) -> None:
        self.list_calls = 0
        self.create_call = None
        self.create_error: CLIError | None = None
        self.status_after_create: str | None = None

    async def list(self) -> dict:
        self.list_calls += 1
        return {
            "instances": [
                {
                    "index": 2,
                    "title": "测试实例",
                    "status": "starting",
                    "busy": "starting",
                    "pid": 1234,
                    "started_at": "2026-10-30T10:00:00+01:00",
                    "adb_address": "127.0.0.1:20021",
                }
            ]
        }

    async def info(self, index: str) -> dict:
        return {
            "index": int(index),
            "title": "测试实例",
            "status": "offline",
            "config": {
                "memory_mb": 4096,
                "cpu": 4,
                "fps": 60,
                "width": 1280,
                "height": 720,
                "dpi": 240,
            },
        }

    async def set(self, index: str, **kwargs: object) -> dict:
        self.set_call = (index, kwargs)
        return {
            "applied": {
                "memory_mb": kwargs.get("memory"),
                "cpu": kwargs.get("cpu"),
                "fps": kwargs.get("fps"),
            }
        }

    async def check(self, *, memory: int | str | None = None) -> dict:
        del memory
        return {"items": []}

    async def create(self, **kwargs: object) -> dict:
        self.create_call = kwargs
        if self.create_error is not None:
            raise self.create_error
        return {"index": kwargs.get("index")}

    async def status(self, index: str) -> dict:
        if self.status_after_create is None:
            raise CLIError("not_found", f"实例 {index} 不存在")
        return {"index": int(index), "status": self.status_after_create}


@pytest.mark.asyncio
async def test_manager_create_timeout_preserves_cli_error_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager_exe = tmp_path / "sdk" / "emulator" / "emulator.exe"
    cli = _FakeManagerCli()
    cli.create_error = CLIError("timeout", "超时", "查看日志")
    cli.status_after_create = "create_failed"
    manager = _AvdCore(manager_exe, 60, False, cli=cli)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="删掉它再新建") as exc_info:
        await manager.create_instance("x", native_index=7)
    assert isinstance(exc_info.value.__cause__, CLIError)
    assert exc_info.value.__cause__.code == "timeout"


# ---- 真的假 modavd 程序 -----------------------------------------------------------

#: 按 ``--json`` 约定输出的假 modavd：经 ``sys.executable`` 当子进程起，调用记进状态目录的
#: 独立的 ``call-*.json``；``plan.json`` 按命令（或 ``命令:第一个参数``，如 ``update:install``）给出数据、
#: 错误、原样输出、退出码，``stderr`` 是先打到 stderr 的几行，``sleep`` 先干等这么多秒，
#: ``hold`` 让进程活着直到收到 ``stop``，``bridge_seconds`` 先起一个命令行带 ``modavd-bridge.ps1`` 的
#: 子进程（装桥）。
_FAKE_MODAVD = r"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
state = Path(os.environ["FAKE_MODAVD_STATE"])
args = sys.argv[1:]
root = args[args.index("--root") + 1] if "--root" in args else ""
command = args[args.index("--json") + 1]
rest = args[args.index("--json") + 2 :]
# Windows 上并发追加同一文件可能覆盖其他进程的记录；各自完整写入后再发布。
call_id = uuid4().hex
pending = state / ("call-" + call_id + ".tmp")
pending.write_text(
    json.dumps({"at": time.time(), "root": root, "command": command, "args": rest}),
    encoding="utf-8",
)
pending.replace(state / ("call-" + call_id + ".json"))
plan_file = state / "plan.json"
plan = json.loads(plan_file.read_text(encoding="utf-8")) if plan_file.exists() else {}
spec = plan.get(command + ":" + rest[0], plan.get(command, {})) if rest else plan.get(command, {})
print("fake modavd log line", file=sys.stderr)
for line in spec.get("stderr", []):
    print(line, file=sys.stderr, flush=True)
if command == "stop":
    (state / "stopped").write_text("1", encoding="utf-8")
if spec.get("bridge_seconds"):
    subprocess.run(
        [sys.executable, "-c", "import sys, time; time.sleep(float(sys.argv[1]))",
         str(spec["bridge_seconds"]), "modavd-bridge.ps1"]
    )
    (state / "bridge-done").write_text(str(time.time()), encoding="utf-8")
if spec.get("sleep"):
    time.sleep(float(spec["sleep"]))
if spec.get("hold"):
    deadline = time.time() + spec["hold"]
    while time.time() < deadline and not (state / "stopped").exists():
        time.sleep(0.05)
    (state / (command + "-exited")).write_text(str(time.time()), encoding="utf-8")
if "raw" in spec:
    sys.stdout.write(spec["raw"])
    sys.exit(spec.get("exit", 0))
if "error" in spec:
    print(json.dumps({"ok": False, "error": spec["error"]}, ensure_ascii=False))
    sys.exit(spec.get("exit", 2))
print(json.dumps({"ok": True, "data": spec.get("data", {})}, ensure_ascii=False))
sys.exit(spec.get("exit", 0))
"""


class _FakeModavd:
    """把根目录的 ``tools\\modavd.exe`` 换成上面的假程序；走真正的 ``_run_process``。"""

    def __init__(self, base: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.state = base / "fake-state"
        self.state.mkdir()
        self.script = base / "fake_modavd.py"
        self.script.write_text(_FAKE_MODAVD, encoding="utf-8")
        self.launched: list[tuple[float, list[str]]] = []
        monkeypatch.setenv("FAKE_MODAVD_STATE", str(self.state))
        real_run_process = cli_module._run_process

        async def run(
            args: Sequence[str], *rest: object, **options: object
        ) -> ProcessOutput:
            # 只换掉要起的程序，其余参数照调用方原样交给真的 _run_process：调用约定对不上时
            # 和真实运行一样报错（11-02 实测前，位置参数传给只收关键字的参数，单测没看出来）
            self.launched.append((time.monotonic(), list(args)[1:]))
            return await real_run_process(
                [sys.executable, "-I", str(self.script), *list(args)[1:]],
                *rest,  # type: ignore[arg-type]
                **options,  # type: ignore[arg-type]
            )

        # ModAvdCli 默认 runner 在构造时取模块里的 _run_process，换掉它就覆盖所有调用点
        monkeypatch.setattr(cli_module, "_run_process", run)

    def plan(self, **commands: dict) -> None:
        (self.state / "plan.json").write_text(
            json.dumps(commands, ensure_ascii=False), encoding="utf-8"
        )

    def calls(self) -> list[dict]:
        records = [
            json.loads(log.read_text(encoding="utf-8"))
            for log in self.state.glob("call-*.json")
        ]
        return sorted(records, key=lambda record: record["at"])

    def commands(self) -> list[str]:
        return [item["command"] for item in self.calls()]


def _root_with_exe(base: Path, name: str = "root") -> Path:
    root = base / name
    exe = root / "tools" / "modavd.exe"
    exe.parent.mkdir(parents=True)
    # 只为让 executable_available 成立；runner 已换成假程序，这个文件不会被执行
    exe.write_bytes(Path(sys.executable).read_bytes())
    return root


def _policy() -> EmulatorRuntimePolicy:
    return EmulatorRuntimePolicy(
        silence_enabled=lambda: True,
        block_ads_enabled=lambda: False,
        resource_path=Path("."),
    )


@pytest.fixture(autouse=True)
def fast_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """收尾轮询、开机错开都调短，别让单测等秒级以上。"""
    monkeypatch.setattr(cli_module, "_CANCEL_POLL_SECONDS", 0.1)
    monkeypatch.setattr(cli_module, "START_STAGGER_SECONDS", 0.0)
    monkeypatch.setattr(cli_module, "_next_start_at", 0.0)


@pytest.mark.asyncio
async def test_start_timeout_waits_for_bridge_round_then_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    # 0.36.0 装桥时 status 报 online、busy 为空：只能看 start 子进程里有没有装桥脚本
    fake.plan(
        start={"bridge_seconds": 1.0, "hold": 20},
        status={"data": {"index": 7, "status": "online", "busy": "", "running": True}},
    )
    monkeypatch.setattr(cli_module, "start_process_timeout", lambda max_wait: 0.3)

    with pytest.raises(CLIError) as exc_info:
        await ModAvdCli(tmp_path).start(7, timeout=60)

    assert exc_info.value.code == "timeout"
    first_stop = next(item for item in fake.calls() if item["command"] == "stop")
    bridge_done = float((fake.state / "bridge-done").read_text(encoding="utf-8"))
    assert first_stop["at"] >= bridge_done
    assert first_stop["args"] == ["7"]
    # start 进程是收到 stop 后自己退出的，没有被结束
    assert (fake.state / "start-exited").exists()


@pytest.mark.asyncio
async def test_start_that_outlives_status_flips_is_not_cut_short(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    fake.plan(
        start={"hold": 1.0, "data": {"instance": {"index": 7, "status": "online"}}},
        status={"data": {"index": 7, "status": "offline", "busy": ""}},
    )
    result = await ModAvdCli(tmp_path).start(7, timeout=60)
    assert result == {"instance": {"index": 7, "status": "online"}}
    assert fake.commands() == ["start"]


@pytest.mark.asyncio
async def test_start_error_only_stops_when_start_may_have_left_it_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    cli = ModAvdCli(tmp_path)
    fake.plan(start={"error": {"code": "busy", "message": "另一个 modavd 正在开机"}})
    with pytest.raises(CLIError):
        await cli.start(7, timeout=60)
    assert fake.commands() == ["start"]

    fake.plan(
        start={"error": {"code": "timeout", "message": "开机超时"}},
        status={"data": {"index": 7, "status": "online", "running": True}},
    )
    with pytest.raises(CLIError):
        await cli.start(7, timeout=60)
    assert fake.commands()[1:] == ["start", "status", "stop"]


@pytest.mark.asyncio
async def test_task_stop_cancels_start_gracefully_and_force_close_spares_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # modavd start 起的模拟器会跟着 start 留在它所在的进程组里：手动停止任务的强制清理不能结束它，
    # 取消开机只能走 start 自己的收尾（请求 stop，等 start 自己退出）
    fake = _FakeModavd(tmp_path, monkeypatch)
    fake.plan(
        start={"hold": 20},
        status={"data": {"index": 7, "status": "online", "busy": "", "running": True}},
    )
    scope = TaskProcessScope()
    token = current_process_scope.set(scope)
    try:
        starting = asyncio.create_task(ModAvdCli(tmp_path).start(7, timeout=60))
    finally:
        current_process_scope.reset(token)
    try:
        await _until(lambda: "start" in fake.commands())
        starting.cancel()
        # 停止任务时取消和强制清理之间只隔约 10 秒，开机收尾常常还没完
        await scope.force_close()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(starting), 10)
        # 取消抛回来之前，start 已经收到 stop 自己退出，而不是被强制清理结束
        assert (fake.state / "start-exited").exists()
        assert "stop" in fake.commands()
    finally:
        if not scope.closed:
            await scope.force_close()


@pytest.mark.asyncio
async def test_starts_of_all_roots_take_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    fake.plan(start={"data": {}}, create={"data": {"index": 8}})
    monkeypatch.setattr(cli_module, "START_STAGGER_SECONDS", 0.6)
    monkeypatch.setattr(cli_module, "_next_start_at", 0.0)

    await asyncio.gather(
        ModAvdCli(tmp_path / "a").start(7, timeout=60),
        ModAvdCli(tmp_path / "b").create(index=8),
    )

    # create 先 list 一次记下原有实例，那次不开机、不算
    times = sorted(
        at for at, args in fake.launched if args[args.index("--json") + 1] != "list"
    )
    assert len(times) == 2
    assert times[1] - times[0] >= 0.5
    assert {item["root"] for item in fake.calls()} == {
        str(tmp_path / "a"),
        str(tmp_path / "b"),
    }


@pytest.mark.asyncio
async def test_power_close_uses_stop_all_and_reports_partial_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    root = _root_with_exe(tmp_path)
    fake.plan(
        version={"data": {"version": "0.1.0", "protocol": 1}},
        stop={
            "data": {
                "results": [{"index": 7}],
                "failed": [
                    {"index": 8, "error": {"code": "timeout", "message": "没关掉"}}
                ],
            },
            "exit": 6,
        },
    )
    monkeypatch.setattr(service_module, "managed_roots", lambda configs: [root])

    result = await service_module.close_running_instances([], timeout=10)

    # stop --all 回 ok 但有实例没关掉：这个根目录不能报成已关完
    assert result == {str(root): "failed"}
    stop_calls = [item for item in fake.calls() if item["command"] == "stop"]
    assert [item["args"] for item in stop_calls] == [["--all"]]


@pytest.mark.asyncio
async def test_power_close_probe_shares_the_deadline_and_does_not_hold_up_other_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    stuck = _root_with_exe(tmp_path, "stuck")
    healthy = _root_with_exe(tmp_path, "healthy")
    # 健康的根目录已经检测过（结果在缓存里）；卡住的那个还没缓存，它的 version 半分钟不回
    fake.plan(version={"data": {"version": "0.2.0", "protocol": 1}})
    assert await resolve_cli(healthy) is not None
    fake.plan(
        version={"sleep": 30},
        stop={"data": {"results": [{"index": 7}], "failed": []}},
    )
    monkeypatch.setattr(
        service_module, "managed_roots", lambda configs: [stuck, healthy]
    )

    started = time.monotonic()
    result = await service_module.close_running_instances([], timeout=3)
    elapsed = time.monotonic() - started

    # 探测也算在关机的总时限里：健康的照常关，卡住的到时限放弃，整体不多等
    assert result == {str(stuck): "timeout", str(healthy): "closed"}
    assert elapsed < 6
    stop_calls = [item for item in fake.calls() if item["command"] == "stop"]
    assert [item["root"] for item in stop_calls] == [str(healthy)]
    await asyncio.sleep(0.5)  # 让被取消的探测把它的子进程收掉


@pytest.mark.asyncio
async def test_broken_modavd_is_reported_and_never_falls_back_to_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    root = _root_with_exe(tmp_path)
    fake.plan(version={"raw": "", "exit": 1})
    manager_exe = root / "sdk" / "emulator" / "emulator.exe"

    with pytest.raises(ModAvdUnavailable, match="modavd 不可用"):
        await manager_module.build_manager(
            str(manager_exe), 60, runtime_policy=_policy()
        )
    with pytest.raises(ModAvdUnavailable, match="modavd 不可用"):
        await service_module.status(str(root))

    # 关机前 modavd 坏了：不另想办法关，这个根目录如实记失败
    monkeypatch.setattr(service_module, "managed_roots", lambda configs: [root])
    assert await service_module.close_running_instances([], timeout=10) == {
        str(root): "failed"
    }
    assert set(fake.commands()) == {"version"}


@pytest.mark.asyncio
async def test_root_without_modavd_cli_is_not_a_usable_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    root = tmp_path / "root"
    emulator = root / "sdk" / "emulator" / "emulator.exe"
    root.mkdir()

    with pytest.raises(RuntimeError, match="找不到 ModAVD 命令行"):
        await manager_module.build_manager(str(emulator), 60, runtime_policy=_policy())
    with pytest.raises(RuntimeError, match="找不到 ModAVD 命令行"):
        await service_module.status(str(root))
    monkeypatch.setattr(service_module, "managed_roots", lambda configs: [root])
    assert await service_module.close_running_instances([], timeout=10) == {
        str(root): "failed"
    }
    assert fake.launched == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("protocol", "usable"), [(1, True), (2, True), (3, False)])
async def test_protocols_1_and_2_use_the_cli_and_others_are_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, protocol: int, usable: bool
) -> None:
    # 2 是 ModAVDManager 0.3.0 去掉 restart 时升的；MAS 重启是先 stop 再 start，两个都能用
    fake = _FakeModavd(tmp_path, monkeypatch)
    root = _root_with_exe(tmp_path)
    fake.plan(version={"data": {"version": "x", "protocol": protocol}})
    manager_exe = str(root / "sdk" / "emulator" / "emulator.exe")

    if usable:
        manager = await manager_module.build_manager(
            manager_exe, 60, runtime_policy=_policy()
        )
        assert manager._cli is not None
    else:
        # 认不出的协议照决定 1 报「modavd 不可用」，不退回 Python 实现
        with pytest.raises(
            ModAvdUnavailable, match="协议 3（比 MAS 认识的 1 / 2 更新）"
        ):
            await manager_module.build_manager(
                manager_exe, 60, runtime_policy=_policy()
            )
    assert fake.commands() == ["version"]


@pytest.mark.asyncio
async def test_own_install_refuses_changes_and_queries_never_start_modavd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    root = _root_with_exe(tmp_path)
    fake.plan(version={"data": {"version": "0.7.0", "protocol": 2}})
    manager = await manager_module.build_manager(
        str(root / "sdk" / "emulator" / "emulator.exe"), 60, runtime_policy=_policy()
    )
    # MAS 自己起的 modavd update install 在跑：换上前那次 list 记着一台实例
    key = updater_module.root_key(root)
    monkeypatch.setattr(updater_module, "_installing", {key})
    monkeypatch.setattr(
        updater_module, "_instance_snapshots", {key: [{"index": 7, "title": "七"}]}
    )
    before = len(fake.calls())

    with pytest.raises(RuntimeError, match="正在更新"):
        await manager.open("7")
    with pytest.raises(RuntimeError, match="正在更新"):
        await manager.restart("7")
    with pytest.raises(RuntimeError, match="正在更新"):
        await manager.create_instance("x", native_index=7)
    with pytest.raises(RuntimeError, match="正在更新"):
        await manager.delete_instance("7")
    with pytest.raises(RuntimeError, match="正在更新"):
        await manager.write_instance_settings("7", {"memoryMb": 4096})
    # 只读查询不起 modavd：实例都算没在运行，列表用换上前那次 list
    assert await manager.getStatus("7") == DeviceStatus.OFFLINE
    info = await manager.getInfo(None)
    assert {k: (v.title, v.status) for k, v in info.items()} == {
        "7": ("七", DeviceStatus.OFFLINE)
    }
    assert await manager.list_devices() == {"7": "七"}
    assert await manager.close("7") == DeviceStatus.OFFLINE
    assert (await service_module.status(str(root)))["prechecks"] == []
    # 关机前收尾：实例本来就都关了，跳过这个根目录
    monkeypatch.setattr(service_module, "managed_roots", lambda configs: [root])
    assert await service_module.close_running_instances([], timeout=10) == {
        str(root): "closed"
    }
    assert len(fake.calls()) == before


_UPDATE_HELP = {
    "data": {
        "commands": [
            {
                "options": [
                    {"flag": "--source github|mirrorchyan"},
                    {"flag": "--cdk-dpapi B64"},
                ]
            }
        ]
    }
}


@pytest.mark.asyncio
async def test_update_passes_source_and_cdk_cipher_as_is_and_never_logs_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    cli = ModAvdCli(_root_with_exe(tmp_path))
    monkeypatch.setattr(cli_module, "CALLER_UPDATE_OPTIONS_PLATFORM", True)
    secret = "AQAAANCMnd8BFdERjHoAwE/Cl+s="
    fake.plan(
        help=_UPDATE_HELP,
        update={"error": {"code": "invalid_argument", "message": "解不开"}, "exit": 2},
    )
    lines: list[str] = []
    sink = loguru_logger.add(lambda message: lines.append(str(message)), level="DEBUG")
    try:
        with pytest.raises(CLIError) as error:
            await cli.update(
                "check",
                automas_version="v5.8.0",
                source="mirrorchyan",
                cdk_dpapi=secret,
            )
        fake.plan(help=_UPDATE_HELP, update={"data": {}})
        await cli.update("prepare", source="github", cdk_dpapi="")
    finally:
        loguru_logger.remove(sink)

    assert [c["args"] for c in fake.calls() if c["command"] == "update"] == [
        ["check", "--automas-version", "v5.8.0", "--source", "mirrorchyan"]
        + ["--cdk-dpapi", secret],
        # 没有 CDK 也显式传空串，免得 modavd 用图形管理器里存的那份
        ["prepare", "--source", "github", "--cdk-dpapi", ""],
    ]
    assert fake.commands().count("help") == 1  # 选项探测按 exe 缓存
    assert secret not in "".join(lines) + str(error.value)


@pytest.mark.asyncio
async def test_old_update_cli_gets_neither_source_nor_cdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    cli = ModAvdCli(_root_with_exe(tmp_path))
    monkeypatch.setattr(cli_module, "CALLER_UPDATE_OPTIONS_PLATFORM", True)
    fake.plan(
        help={"data": {"commands": [{"options": [{"flag": "--automas-version V"}]}]}},
        update={"data": {}},
    )

    await cli.update(
        "install", automas_version="v5.8.0", source="github", cdk_dpapi="x"
    )
    await cli.update("recover", source="github", cdk_dpapi="x")

    assert [c["args"] for c in fake.calls() if c["command"] == "update"] == [
        ["install", "--automas-version", "v5.8.0"],
        ["recover"],
    ]


@pytest.mark.asyncio
async def test_update_streams_progress_and_shows_busy_from_modavd_as_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    root = _root_with_exe(tmp_path)
    monkeypatch.setattr(cli_module, "CALLER_UPDATE_OPTIONS_PLATFORM", False)
    monkeypatch.setattr(updater_module, "_PUBLISH_INTERVAL_SECONDS", 0)
    progress = {"stage": "downloading", "percent": 50.0, "done_bytes": 5}
    line = {"msg": "下载", "progress": {**progress, "total_bytes": 10, "new": 1}}
    fake.plan(
        version={"data": {"version": "0.7.0", "protocol": 2}},
        list={"data": {"instances": [{"index": 7, "status": "offline"}]}},
        **{
            "update:status": {"data": {"updatable": True, "phase": "idle"}},
            "update:prepare": {
                "stderr": ["不是 JSON 的行", json.dumps(line, ensure_ascii=False)],
                "data": {"updatable": True, "prepared_version": "v0.8.0"},
            },
            "update:install": {
                "error": {
                    "code": "busy",
                    "message": "0.8.0 已下载并核对好，但现在不能换上：ModAVD.exe 开着",
                    "advice": "关掉管理器",
                    "details": {"reason": "running"},
                },
                "exit": 5,
            },
        },
    )
    published: list[updater_module.UpdateProgress] = []

    async def publish(path: Path, item: updater_module.UpdateProgress) -> None:
        published.append(item)

    host = updater_module.UpdateHost(
        settings=lambda: updater_module.UpdateSettings("github", "v5.8.0", ""),
        environment=lambda: None,
        managed_roots=lambda: [root],
        opening_instances=lambda path: [],
        publish_progress=publish,
    )

    assert (await updater_module.update(str(root), host=host))["reason"] == "started"
    await updater_module._runtime(root).job  # type: ignore[misc]

    downloading = [p for p in published if p.stage == "downloading"]
    assert (downloading[-1].percent, downloading[-1].totalBytes) == (50.0, 10)
    final = published[-1]
    assert (final.stage, final.status) == ("staged", "failed")
    assert "ModAVD.exe 开着" in final.message and "关掉管理器" in final.message
    assert not updater_module.update_in_progress(root)


@pytest.mark.asyncio
async def test_update_cdk_is_used_once_retried_empty_when_unreadable_and_notices_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(updater_module, "_PUBLISH_INTERVAL_SECONDS", 0)
    fallback = "Mirror 酱出错，这次改从 GitHub 下载"

    class Cli:
        root = tmp_path

        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []
            self.error = "invalid_argument"

        async def update(self, action: str, *, cdk_dpapi=None, **_: object) -> dict:
            self.calls.append((action, cdk_dpapi))
            if cdk_dpapi == "bad":
                raise CLIError(self.error, "--cdk-dpapi 解不开")
            if action == "prepare":
                return {"prepared_version": "v0.39.0", "notices": [fallback]}
            return {"updated": action == "install", "notices": [fallback]}

        async def list(self) -> dict:
            return {"instances": []}

    published: list[updater_module.UpdateProgress] = []

    async def publish(path: Path, item: updater_module.UpdateProgress) -> None:
        published.append(item)

    def host(cdk: str) -> updater_module.UpdateHost:
        return updater_module.UpdateHost(
            settings=lambda: updater_module.UpdateSettings(
                "mirrorchyan", "v5.8.0", cdk
            ),
            environment=lambda: None,
            managed_roots=lambda: [tmp_path],
            opening_instances=lambda path: [],
            publish_progress=publish,
        )

    # 已经准备好一版：install 传空 CDK，Mirror 酱只计 prepare 那一次；两次的 notices 去重后进最终消息
    cli = Cli()
    runtime = updater_module._runtime(tmp_path)
    await updater_module._run_update(runtime, cli, host("good"))  # type: ignore[arg-type]
    assert cli.calls == [("prepare", "good"), ("install", "")]
    assert published[-1].message == f"已更新；{fallback}"

    # 解不开：同一步用空 CDK 重试一次，提示带上「CDK 读不出」；别的错误码不重试
    cli.calls.clear()
    settings = host("bad").settings()
    _, notices = await updater_module._caller_update(cli, "check", settings, env=None)  # type: ignore[arg-type]
    assert cli.calls == [("check", "bad"), ("check", "")]
    assert notices == [updater_module.CDK_UNREADABLE_NOTICE, fallback]
    cli.calls.clear()
    cli.error = "busy"
    with pytest.raises(CLIError):
        await updater_module._caller_update(cli, "check", settings, env=None)  # type: ignore[arg-type]
    assert cli.calls == [("check", "bad")]


@pytest.mark.asyncio
async def test_open_retries_start_when_guest_script_push_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class StartCli:
        def __init__(self) -> None:
            self.starts = 0

        async def info(self, index: str) -> dict:
            return {"index": int(index), "status": "offline"}

        async def start(self, index: str, **kwargs: object) -> dict:
            self.starts += 1
            warnings = ["写客体脚本 mas-idlepoll.sh 失败: 文件被占用"]
            return {
                "warnings": warnings if self.starts == 1 else [],
                "instance": {"index": int(index), "status": "online"},
            }

    cli = StartCli()
    manager_exe = tmp_path / "sdk" / "emulator" / "emulator.exe"
    manager = _AvdCore(manager_exe, 60, False, cli=cli)  # type: ignore[arg-type]

    info = await manager.open("7")

    assert cli.starts == 2
    assert info.status == DeviceStatus.ONLINE


@pytest.mark.asyncio
async def test_creating_instance_shows_creating_and_is_never_stopped_or_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    root = _root_with_exe(tmp_path)
    version = {"data": {"version": "0.2.0", "protocol": 1}}
    creating = {
        "index": 7,
        "title": "新实例",
        "status": "creating",
        "busy": "creating",
        "running": True,
    }
    fake.plan(
        version=version,
        status={"data": creating},
        info={"data": creating},
        list={"data": {"instances": [creating]}},
    )
    manager = await manager_module.build_manager(
        str(root / "sdk" / "emulator" / "emulator.exe"), 60, runtime_policy=_policy()
    )

    assert (await manager.getInfo(None))["7"].status == DeviceStatus.CREATING
    # MAS 先问 modavd 的状态再拦：关机、重启会打断后台初始化，开机要等新建完成
    with pytest.raises(RuntimeError, match="正在新建"):
        await manager.close("7")
    with pytest.raises(RuntimeError, match="正在新建"):
        await manager.restart("7", manual=True)
    with pytest.raises(RuntimeError, match="正在新建"):
        await manager.open("7", manual=True)
    assert not {"stop", "start", "restart"} & set(fake.commands())

    # 新建程序中途被结束：modavd 按新建失败报；列表显示新建失败和原因，照常能关、能删
    failed = {
        **creating,
        "status": "create_failed",
        "busy": "",
        "creation_error": "新建它的程序中途退出了",
    }
    fake.plan(
        version=version,
        status={"data": failed},
        list={"data": {"instances": [failed]}},
        stop={"data": {}},
        delete={"data": {}},
    )
    info = (await manager.getInfo(None))["7"]
    assert (info.status, info.creation_error) == (
        DeviceStatus.CREATE_FAILED,
        "新建它的程序中途退出了",
    )
    path = SimpleNamespace(path_id="p", alias="AVD", type="avd")
    row = EmulatorOperations._device_row(None, path, "1", "7", info, "ok")  # type: ignore[arg-type]
    assert (row["status"], row["creationError"]) == (7, "新建它的程序中途退出了")
    assert await manager.close("7") == DeviceStatus.OFFLINE
    await manager.delete_instance("7")
    assert fake.commands()[-2:] == ["stop", "delete"]


class _Qemu:
    def __init__(self, name: str, *flags: str) -> None:
        self.pid = 4242
        self._name = name
        self._cmdline = [name, "-avd", "mas_7", "-ports", "20070,20071", *flags]

    def name(self) -> str:
        return self._name

    def cmdline(self) -> list[str]:
        return self._cmdline


@pytest.mark.asyncio
async def test_list_marks_headless_instances_so_show_and_hide_are_greyed_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    root = _root_with_exe(tmp_path)
    qemu_dir = root / "sdk" / "emulator" / "qemu" / "windows-x86_64"
    processes = {
        4242: _Qemu("qemu-system-x86_64-headless.exe", "-no-window"),
        4343: _Qemu("qemu-system-x86_64.exe"),
        4444: None,
    }

    class _Process:
        def __init__(self, pid: int) -> None:
            self._qemu = processes[pid]

        def exe(self) -> str:
            return str(qemu_dir / "qemu-system-x86_64.exe")

        def create_time(self) -> float:
            return 1.0

        def name(self) -> str:
            if self._qemu is None:
                raise manager_module.psutil.AccessDenied(4444)
            return self._qemu.name()

        def cmdline(self) -> list[str]:
            if self._qemu is None:
                raise manager_module.psutil.AccessDenied(4444)
            return self._qemu.cmdline()

    monkeypatch.setattr(manager_module.psutil, "Process", _Process)
    fake.plan(
        version={"data": {"version": "0.3.0", "protocol": 2}},
        list={
            "data": {
                "instances": [
                    # 0.3.0 带 window 字段：以它为准
                    {"index": 1, "status": "online", "running": True, "window": True},
                    {"index": 2, "status": "online", "running": True, "window": False},
                    {
                        "index": 3,
                        "status": "offline",
                        "running": False,
                        "window": False,
                    },
                    # 旧版没有 window：看 qemu 进程，认不出就按无头（宁可置灰）
                    {"index": 7, "status": "online", "pid": 4242},
                    {"index": 8, "status": "online", "pid": 4343},
                    {"index": 4, "status": "online", "pid": 4444},
                    {"index": 9, "status": "offline"},
                ]
            }
        },
    )
    manager = await manager_module.build_manager(
        str(root / "sdk" / "emulator" / "emulator.exe"), 60, runtime_policy=_policy()
    )

    info = await manager.getInfo(None)

    assert {key: item.headless for key, item in info.items()} == {
        "1": False,
        "2": True,
        "3": None,
        "7": True,
        "8": False,
        "4": True,
        "9": None,
    }
    path = SimpleNamespace(path_id="p", alias="AVD", type="avd")
    row = EmulatorOperations._device_row(None, path, "1", "7", info["7"], "ok")  # type: ignore[arg-type]
    assert row["headless"] is True


@pytest.mark.asyncio
async def test_restart_is_stop_then_start_and_running_mode_is_never_switched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    root = _root_with_exe(tmp_path)
    fake.plan(
        version={"data": {"version": "0.3.0", "protocol": 2}},
        stop={"data": {}},
        start={"data": {"instance": {"index": 7, "status": "online"}}},
        window={"data": {"index": 7, "windows": 0}},
        status={"data": {"index": 7, "status": "online"}},
    )
    # 静默模式开着：任务拉起无头，模拟器页手动启动带窗口
    manager = await manager_module.build_manager(
        str(root / "sdk" / "emulator" / "emulator.exe"), 60, runtime_policy=_policy()
    )

    # 0.3.0 没有 modavd restart：重启是先关机再开机，开机按这次的入口定有没有窗口
    await manager.restart("7")
    await manager.restart("7", manual=True)
    calls = [(item["command"], item["args"]) for item in fake.calls()]
    # 关机前问一次 status（新建中不关），开机前问一次 info（新建中不开、分辨率给 start 判断）
    assert [command for command, _ in calls] == [
        "version",
        "status",
        "stop",
        "info",
        "start",
        "status",
        "stop",
        "info",
        "start",
    ]
    starts = [args for command, args in calls if command == "start"]
    assert "--window" not in starts[0]
    assert "--window" in starts[1]

    # 实例正无头运行：旧版 modavd 再要窗口也只是接着用，不重启、不切换；脚本每轮调的显示照旧不抛
    before = len(fake.calls())
    assert (await manager.open("7", manual=True)).status == DeviceStatus.ONLINE
    await manager.setVisible("7", True)
    assert [item["command"] for item in fake.calls()[before:]] == [
        "info",
        "start",
        "window",
        "status",
    ]

    # 0.3.0 碰上这种情况报 busy（退出码 5）：提示原样给用户，也不去关那台正在跑的实例
    fake.plan(
        start={
            "error": {
                "code": "busy",
                "message": "ModAVD 实例 7 正在无头运行",
                "advice": "先关机再换成带窗口",
            },
            "exit": 5,
        },
    )
    before = len(fake.calls())
    with pytest.raises(RuntimeError, match="正在无头运行（建议：先关机再换成带窗口）"):
        await manager.open("7", manual=True)
    assert [item["command"] for item in fake.calls()[before:]] == ["info", "start"]


async def _until(predicate, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "等太久"
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_cancelled_create_only_stops_the_instance_it_was_creating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_module, "_CREATE_CLEANUP_SECONDS", 1)
    cli = ModAvdCli(tmp_path)

    # 7 号原来就有实例：指定 7 号新建被取消时，收尾不能把那台关掉
    fake.plan(
        list={"data": {"instances": [{"index": 7, "status": "online"}]}},
        create={"hold": 20},
        stop={"data": {}},
    )
    task = asyncio.create_task(cli.create(index=7))
    await _until(lambda: "create" in fake.commands())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "stop" not in fake.commands()

    # 8 号是这次建出来的（新建中）：取消时要关掉它，别留一台没人管的无头模拟器
    for record in fake.state.glob("call-*.json"):
        record.unlink()
    fake.plan(list={"data": {"instances": []}}, create={"hold": 20}, stop={"data": {}})
    task = asyncio.create_task(cli.create(index=8))
    await _until(lambda: "create" in fake.commands())
    fake.plan(
        list={"data": {"instances": [{"index": 8, "status": "creating"}]}},
        stop={"data": {}},
    )
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    stops = [item["args"] for item in fake.calls() if item["command"] == "stop"]
    assert stops and all(args == ["8"] for args in stops)


@pytest.mark.parametrize("first_lookup", ["empty", "fails"])
@pytest.mark.asyncio
async def test_cancelled_create_keeps_looking_for_an_instance_that_shows_up_late(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, first_lookup: str
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_module, "_CREATE_CLEANUP_SECONDS", 5)
    cli = ModAvdCli(tmp_path)
    fake.plan(list={"data": {"instances": []}}, create={"hold": 20}, stop={"data": {}})
    task = asyncio.create_task(cli.create(index=8))
    await _until(lambda: "create" in fake.commands())

    # 取消时实例还列不出来（文件没建好），或这一次 list 失败
    if first_lookup == "fails":
        fake.plan(
            list={"error": {"code": "internal", "message": "读不出"}, "exit": 1},
            stop={"data": {}},
        )
    lists_before = fake.commands().count("list")
    task.cancel()
    await _until(lambda: fake.commands().count("list") > lists_before)
    assert "stop" not in fake.commands()

    # 之后 8 号以新建中出现：收尾要接着找到它并关掉
    fake.plan(
        list={"data": {"instances": [{"index": 8, "status": "creating"}]}},
        stop={"data": {}},
    )
    with pytest.raises(asyncio.CancelledError):
        await task
    stops = [item["args"] for item in fake.calls() if item["command"] == "stop"]
    assert stops and all(args == ["8"] for args in stops)


@pytest.mark.asyncio
async def test_concurrent_setting_writes_with_the_same_expected_value_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.utils.common.emulator2.settings import SettingsConflictError

    class SettingsCli(_FakeManagerCli):
        def __init__(self) -> None:
            super().__init__()
            self.memory = 4096

        async def info(self, index: str) -> dict:
            data = await super().info(index)
            data["config"]["memory_mb"] = self.memory
            return data

        async def set(self, index: str, **kwargs: object) -> dict:
            await asyncio.sleep(0.05)
            self.memory = int(kwargs["memory"])  # type: ignore[arg-type]
            return await super().set(index, **kwargs)

    cli = SettingsCli()
    manager_exe = tmp_path / "sdk" / "emulator" / "emulator.exe"
    manager = _AvdCore(manager_exe, 60, False, cli=cli)  # type: ignore[arg-type]

    results = await asyncio.gather(
        manager.write_instance_settings("7", {"memoryMb": 6144}, {"memoryMb": 4096}),
        manager.write_instance_settings("7", {"memoryMb": 3072}, {"memoryMb": 4096}),
        return_exceptions=True,
    )

    # 两个请求拿着同一份「打开表单时看到的值」：只能有一个写成，另一个报冲突，不能互相覆盖
    assert [isinstance(item, SettingsConflictError) for item in results] == [
        False,
        True,
    ]
    assert cli.memory == 6144


@pytest.mark.asyncio
async def test_concurrent_creates_keep_each_others_device_slots() -> None:
    from app.utils.common.emulator2.slots import PathRecord, SlotTable

    path = PathRecord("p", "D:/avd", "AVD", "avd", "37")
    saved = {"slots": SlotTable().to_json()}
    native = iter(["7", "8"])

    class Backend:
        async def create_instance(self, name: str | None, **options: object) -> str:
            index = next(native)
            await asyncio.sleep(0.05)  # 新建要在后台开一次机，两次新建叠在一起
            return index

    backend = Backend()

    class Facade:
        def __init__(self) -> None:
            self.paths = [path]
            self.slots = SlotTable.from_json(saved["slots"])

        def path_of(self, path_id: str) -> PathRecord | None:
            return path if path_id == path.path_id else None

        async def manager_for(self, record: PathRecord) -> Backend:
            return backend

    class Operations(EmulatorOperations):
        def __init__(self) -> None:
            pass

        async def build_manager(self, emulator_id: str):  # type: ignore[override]
            return Facade()

        async def _save(self, emulator_id, paths, slots) -> None:  # type: ignore[override]
            saved["slots"] = slots.to_json()

    operations = Operations()
    results = await asyncio.gather(
        operations.create_instance("e", "p"), operations.create_instance("e", "p")
    )

    assert all(item["ok"] for item in results)
    # 后存的那次不能拿新建前的旧槽位表把先存的设备号盖掉
    table = SlotTable.from_json(saved["slots"])
    assert sorted(record.native_index for record in table.records) == ["7", "8"]


@pytest.mark.asyncio
@pytest.mark.parametrize("supports_presets", [False, True])
async def test_resolution_flags_and_old_cli_compatibility(
    tmp_path: Path, supports_presets: bool
) -> None:
    writes: list[list[str]] = []

    async def runner(
        args: Sequence[str],
        timeout: float,
        timeout_handler: object = None,
        breakaway: bool = False,
    ) -> ProcessOutput:
        del timeout, timeout_handler, breakaway
        if "help" in args:
            options = [{"flag": "--resolution"}] if supports_presets else []
            data = {"commands": [{"name": "create", "options": options}]}
        elif "list" in args:
            data = {"instances": []}
        else:
            writes.append(list(args))
            data = {"index": 7, "applied": {}}
        return ProcessOutput(0, json.dumps({"ok": True, "data": data}), "")

    cli = ModAvdCli(tmp_path, exe=sys.executable, runner=runner)
    for resolution in (720, 1080):
        writes.clear()
        if not supports_presets and resolution == 1080:
            with pytest.raises(CLIError) as caught:
                await cli.create(index=7, resolution=resolution)
            assert caught.value.code == "unsupported"
            assert writes == []
            with pytest.raises(CLIError):
                await cli.set(7, resolution=resolution)
            assert writes == []
        else:
            await cli.create(index=7, resolution=resolution)
            await cli.set(7, resolution=resolution)
            assert len(writes) == 2
            for command in writes:
                assert ("--resolution" in command) == supports_presets
                if supports_presets:
                    assert command[command.index("--resolution") + 1] == str(resolution)
    # start 的分辨率由调用方从 info 拿来：1080p 的实例碰上没有 --resolution 的旧命令行先拒绝
    for resolution in (None, 720, 1080):
        writes.clear()
        if not supports_presets and resolution == 1080:
            with pytest.raises(CLIError) as caught:
                await cli.start(7, resolution=resolution)
            assert caught.value.code == "unsupported"
            assert writes == []
        else:
            await cli.start(7, resolution=resolution)
            assert len(writes) == 1
            assert "start" in writes[0]


# ---- MAS 自己不再碰 adb、进程和 ModAVD 的文件 ------------------------------------------------


@pytest.mark.asyncio
async def test_host_adb_goes_through_modavd_adb_and_keeps_png_bytes(
    tmp_path: Path,
) -> None:
    png = b"\x89PNG\r\n\x1a\n\x00\xff\r\n"
    calls: list[tuple[list[str], bool]] = []

    async def raw_runner(
        args: Sequence[str], timeout: float, merge_stderr: bool
    ) -> tuple[int, bytes, bytes]:
        calls.append((list(args), merge_stderr))
        if "screencap" in args:
            return 0, png, b""
        return 0, b"package:a\r\n", b""

    cli = ModAvdCli(tmp_path, exe="modavd.exe", raw_runner=raw_runner)
    adb = manager_module.AvdHostAdb(cli, "7")

    # 截图的字节原样交回（不解码、不换行转换），其余命令的输出合并 stderr 后解码
    assert await adb.screencap_png() == png
    assert await adb("shell", "pm", "path", "a", timeout=5) == (0, "package:a")
    head = ["modavd.exe", "--root", str(tmp_path), "--quiet", "adb", "7", "--"]
    assert calls == [
        (head + ["exec-out", "screencap", "-p"], False),
        (head + ["shell", "pm", "path", "a"], True),
    ]


@pytest.mark.asyncio
async def test_script_adb_server_comes_from_modavd_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    root = _root_with_exe(tmp_path)
    servers = {
        "adb_server_port": 21050,
        "adb_server_up": True,
        "script_adb_server_port": 21049,
        "script_adb_server_up": True,
    }
    fake.plan(version={"data": {"protocol": 2}}, servers={"data": servers})

    assert await host_module.ensure_script_adb_server(root) is True
    # 脚本的端口用 modavd 报的，不读 mas-avd.json、不按端口段算
    assert host_module.script_adb_env(root)["ANDROID_ADB_SERVER_PORT"] == "21049"

    fake.plan(
        servers={
            "error": {"code": "port_conflict", "message": "端口 21049 被 x.exe 占用"},
            "exit": 5,
        }
    )
    with pytest.raises(host_module.ScriptAdbPortConflict, match="21049"):
        await host_module.ensure_script_adb_server(root)
    assert fake.commands() == ["version", "servers", "servers"]


@pytest.mark.asyncio
async def test_frozen_instance_is_ended_with_modavd_stop_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Cli:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        async def shell(self, index: str, *command: str, timeout: float = 5) -> dict:
            self.calls.append(("shell", index, command))
            raise CLIError("timeout", "adb 不通")

        async def stop(self, index: str, *, force: bool = False) -> dict:
            self.calls.append(("stop", index, force))
            return {}

    class Qemu:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def is_running(self) -> bool:
            return True

        def status(self) -> str:
            return "running"

    class FastWatchdog(manager_module.FreezeWatchdog):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, interval=0.01, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(manager_module.psutil, "Process", Qemu)
    monkeypatch.setattr(manager_module.host, "process_cpu_seconds", lambda _: 1.0)
    monkeypatch.setattr(manager_module, "FreezeWatchdog", FastWatchdog)
    cli = Cli()
    key = manager_module._instance_key(tmp_path, "7")

    manager_module._start_watchdog(tmp_path, "7", 4242, cli=cli)  # type: ignore[arg-type]
    try:
        assert await asyncio.wait_for(manager_module._WATCHDOGS[key], 5) == "frozen"
    finally:
        reason = manager_module._FROZEN.pop(key, "")
    # adb 不通、CPU 时间不动：交给 modavd 强制关机，MAS 自己不结束进程
    assert [call for call in cli.calls if call[0] == "stop"] == [("stop", "7", True)]
    assert "已强制结束" in reason


@pytest.mark.asyncio
async def test_adding_a_root_only_needs_modavd_exe_and_a_usable_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    # 没有命令行的旧根目录（只有 sdk）：不认，也不起进程
    old = tmp_path / "old"
    (old / "sdk" / "emulator").mkdir(parents=True)
    (old / "sdk" / "emulator" / "emulator.exe").touch()
    assert not detect.is_avd_root(str(old))
    assert (await detect.probe_install_path(str(old), "avd")).reason == "not_found"
    assert fake.launched == []

    # 有 modavd.exe、协议认识：可添加，版本是 modavd list 报的包版本；组件齐不齐不在这里看
    root = _root_with_exe(tmp_path)
    fake.plan(
        version={"data": {"protocol": 2}},
        list={"data": {"version": "0.38.2", "instances": []}},
    )
    result = await detect.probe_install_path(str(root))
    assert (result.supported, result.reason, result.type, result.version) == (
        True,
        "ok",
        "avd",
        "0.38.2",
    )
    assert result.manager_exe.endswith("sdk/emulator/emulator.exe")
    assert fake.commands() == ["version", "list"]

    # 命令行用不了（协议不认识）：不能添加
    fake.plan(version={"data": {"protocol": 99}})
    result = await detect.probe_install_path(str(_root_with_exe(tmp_path, "new")))
    assert (result.supported, result.reason) == (False, "probe_failed")
