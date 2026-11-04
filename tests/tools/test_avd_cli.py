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

from app.core.emulator_manager.operations import EmulatorOperations
from app.models.emulator import DeviceStatus, EmulatorRuntimePolicy
from app.utils.common.emulator2.avd import cli as cli_module
from app.utils.common.emulator2.avd import manager as manager_module
from app.utils.common.emulator2.avd import service as service_module
from app.utils.common.emulator2.avd import update_stage as stage_module
from app.utils.common.emulator2.avd import updater as updater_module
from app.utils.common.emulator2.avd.cli import (
    CREATE_PROCESS_MARGIN_SECONDS,
    CREATE_TIMEOUT_SECONDS,
    CLIError,
    ModAvdCli,
    ModAvdUnavailable,
    ProcessOutput,
    _run_process,
    map_cli_error,
    resolve_cli,
)
from app.utils.common.emulator2.avd.host import AdbPortConflict
from app.utils.common.emulator2.avd.manager import _AvdCore, map_status
from app.utils.common.emulator2.avd.precheck import PrecheckFailed


class _FakeRunner:
    def __init__(self, output: ProcessOutput | None = None) -> None:
        self.output = output
        self.calls: list[tuple[list[str], float, object, bool]] = []

    async def __call__(
        self,
        args: Sequence[str],
        timeout: float,
        timeout_handler: object = None,
        breakaway: bool = False,
    ) -> ProcessOutput:
        self.calls.append((list(args), timeout, timeout_handler, breakaway))
        if self.output is None:
            raise AssertionError("fake runner has no output")
        return self.output


def _cli(tmp_path: Path, runner: _FakeRunner) -> ModAvdCli:
    return ModAvdCli(tmp_path, exe=sys.executable, runner=runner)


@pytest.mark.asyncio
async def test_resolve_cli_requires_executable_and_protocol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert await resolve_cli(tmp_path) is None
    root = tmp_path / "known"
    exe = root / "tools" / "modavd.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(Path(sys.executable).read_bytes())

    # resolve_cli uses the production client; the executable is a valid interpreter image,
    # while the version probe is replaced with the contract-shaped fake result.
    async def version(self: ModAvdCli) -> dict:
        del self
        return {"protocol": 1}

    monkeypatch.setattr(ModAvdCli, "version", version)
    assert await resolve_cli(root) is not None


@pytest.mark.asyncio
async def test_stderr_is_not_mixed_into_json_and_arguments_are_mapped(
    tmp_path: Path,
) -> None:
    fake = _FakeRunner(
        ProcessOutput(
            0,
            '{"ok":true,"data":{"instances":[]}}',
            '{"step":"query","message":"日志不属于 stdout"}\n',
        )
    )
    cli = _cli(tmp_path, fake)
    assert await cli.list() == {"instances": []}
    args, timeout = fake.calls[-1][0], fake.calls[-1][1]
    assert args[1:5] == ["--root", str(tmp_path), "--json", "list"]
    assert timeout > 0

    fake.output = ProcessOutput(0, '{"ok":true,"data":{}}', "")
    await cli.create(index=2, title="测试", memory="3G", cpu=4, data_gb=64, fps=60)
    assert fake.calls[-1][0][4:] == [
        "create",
        "--index",
        "2",
        "--title",
        "测试",
        "--memory",
        "3G",
        "--cpu",
        "4",
        "--data-gb",
        "64",
        "--fps",
        "60",
        "--timeout",
        str(CREATE_TIMEOUT_SECONDS),
    ]
    assert fake.calls[-1][1] == CREATE_TIMEOUT_SECONDS + CREATE_PROCESS_MARGIN_SECONDS


@pytest.mark.asyncio
async def test_start_stop_window_install_flags_and_timeouts(tmp_path: Path) -> None:
    fake = _FakeRunner(ProcessOutput(0, '{"ok":true,"data":{}}', ""))
    cli = _cli(tmp_path, fake)

    await cli.start(3, window=True, timeout=10)
    args, process_timeout = fake.calls[-1][0], fake.calls[-1][1]
    assert args[4:] == ["start", "3", "--window", "--timeout", "10"]
    # 一次开机加三轮装桥：10 + 60 + 3 × (300 + 28 + 30 + 10 + 60)
    assert process_timeout == cli_module.start_process_timeout(10) == 1354

    await cli.stop(3)
    assert fake.calls[-1][0][4:] == ["stop", "3"]
    assert fake.calls[-1][1] == 90

    await cli.stop(3, force=True)
    assert fake.calls[-1][0][4:] == ["stop", "3", "--force"]

    await cli.window(3, visible=False)
    assert fake.calls[-1][0][4:] == ["window", "3", "hide"]

    await cli.install(3, tmp_path / "game.apk")
    assert fake.calls[-1][0][4:] == ["install", "3", str(tmp_path / "game.apk")]
    assert fake.calls[-1][1] >= 900


@pytest.mark.asyncio
async def test_set_delete_stop_all_and_shell_flags(tmp_path: Path) -> None:
    fake = _FakeRunner(ProcessOutput(0, '{"ok":true,"data":{}}', ""))
    cli = _cli(tmp_path, fake)
    await cli.set(7, title="七号", memory="4G", cpu=6, data_gb=48, fps=60)
    assert fake.calls[-1][0][4:] == [
        "set",
        "7",
        "--title",
        "七号",
        "--memory",
        "4G",
        "--cpu",
        "6",
        "--data-gb",
        "48",
        "--fps",
        "60",
    ]
    await cli.delete(7)
    assert fake.calls[-1][0][4:] == ["delete", "7", "--yes"]
    await cli.stop_all(force=True)
    assert fake.calls[-1][0][4:] == ["stop", "--all", "--force"]
    await cli.shell(7, "echo", "--value", "x")
    assert fake.calls[-1][0][4:] == [
        "shell",
        "7",
        "--timeout",
        "5",
        "--",
        "echo",
        "--value",
        "x",
    ]


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


def test_error_mapping() -> None:
    assert isinstance(map_cli_error(CLIError("invalid_argument", "bad")), ValueError)
    assert isinstance(map_cli_error(CLIError("port_conflict", "busy")), AdbPortConflict)
    assert isinstance(
        map_cli_error(CLIError("precheck_failed", "precheck")), PrecheckFailed
    )
    assert isinstance(map_cli_error(CLIError("internal", "boom")), RuntimeError)


@pytest.mark.parametrize(
    ("status", "busy", "expected"),
    [
        ("offline", "", DeviceStatus.OFFLINE),
        ("online", "", DeviceStatus.ONLINE),
        ("offline", "starting", DeviceStatus.STARTING),
        ("online", "stopping", DeviceStatus.CLOSEING),
        ("unknown", "", DeviceStatus.STARTING),
        ("creating", "creating", DeviceStatus.CREATING),
        ("creating", "stopping", DeviceStatus.CREATING),
        ("create_failed", "", DeviceStatus.CREATE_FAILED),
        ("offline", "mystery", DeviceStatus.STARTING),
    ],
)
def test_status_mapping(status: str, busy: str, expected: DeviceStatus) -> None:
    assert map_status(status, busy) == expected


def test_error_mapping_includes_advice() -> None:
    error = map_cli_error(CLIError("invalid_argument", "参数错", "换一个值"))
    assert isinstance(error, ValueError)
    assert "换一个值" in str(error)


@pytest.mark.asyncio
async def test_timeout_from_runner_is_a_cli_error(tmp_path: Path) -> None:
    async def timeout_runner(
        args: Sequence[str], timeout: float, timeout_handler: object, breakaway: bool
    ) -> ProcessOutput:
        del args, timeout, timeout_handler, breakaway
        raise asyncio.TimeoutError

    cli = ModAvdCli(tmp_path, exe=sys.executable, runner=timeout_runner)
    with pytest.raises(CLIError, match="未结束") as exc_info:
        await cli.info(1)
    assert exc_info.value.code == "timeout"


@pytest.mark.asyncio
async def test_error_envelope_preserves_code_message_and_advice(tmp_path: Path) -> None:
    fake = _FakeRunner(
        ProcessOutput(
            2,
            '{"ok":false,"error":{"code":"invalid_argument","message":"参数错","advice":"改正"}}',
            "log on stderr",
        )
    )
    with pytest.raises(CLIError) as exc_info:
        await _cli(tmp_path, fake).info(1)
    error = exc_info.value
    assert (error.code, error.message, error.advice, error.returncode) == (
        "invalid_argument",
        "参数错",
        "改正",
        2,
    )


def test_parse_envelope_accepts_utf8_bom() -> None:
    from app.utils.common.emulator2.avd.cli import _parse_envelope

    assert _parse_envelope(
        ProcessOutput(0, '\ufeff{"ok":true,"data":{"ready":true}}', "")
    ) == {"ready": True}


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
async def test_manager_cli_list_maps_busy_and_only_queries_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager_exe = tmp_path / "sdk" / "emulator" / "emulator.exe"
    cli = _FakeManagerCli()
    manager = _AvdCore(manager_exe, 60, False, cli=cli)  # type: ignore[arg-type]

    class _FakeProcess:
        def is_running(self) -> bool:
            return True

        def exe(self) -> str:
            return str(tmp_path / "sdk" / "emulator" / "qemu" / "qemu.exe")

        def create_time(self) -> float:
            return 1234.5

        def name(self) -> str:
            return "qemu.exe"

        def cmdline(self) -> list[str]:
            return ["qemu.exe"]

    monkeypatch.setattr(manager_module.psutil, "Process", lambda pid: _FakeProcess())

    info = await manager.getInfo(None)

    assert cli.list_calls == 1
    assert info["2"].status == DeviceStatus.STARTING
    assert info["2"].process_id == 1234
    assert info["2"].process_started_at == 1234.5
    assert info["2"].adb_address == "127.0.0.1:20021"


@pytest.mark.asyncio
async def test_manager_cli_settings_reads_snake_case_memory(tmp_path: Path) -> None:
    manager_exe = tmp_path / "sdk" / "emulator" / "emulator.exe"
    manager = _AvdCore(manager_exe, 60, False, cli=_FakeManagerCli())  # type: ignore[arg-type]

    settings = await manager.read_instance_settings("2")

    assert settings.values()["memoryMb"] == 4096


@pytest.mark.asyncio
async def test_manager_cli_settings_maps_memory_cpu_fps(tmp_path: Path) -> None:
    manager_exe = tmp_path / "sdk" / "emulator" / "emulator.exe"
    cli = _FakeManagerCli()
    manager = _AvdCore(manager_exe, 60, False, cli=cli)  # type: ignore[arg-type]
    result = await manager.write_instance_settings(
        "2", {"memoryMb": 5120, "cpu": 6, "fps": 60}
    )
    assert cli.set_call == ("2", {"memory": 5120, "cpu": 6, "fps": 60})
    assert result == {"memoryMb": 5120, "cpu": 6, "fps": 60}


@pytest.mark.asyncio
async def test_manager_set_visible_ignores_cli_error(tmp_path: Path) -> None:
    class WindowErrorCli:
        async def window(self, index: str, *, visible: bool) -> None:
            del index, visible
            raise CLIError("internal", "窗口暂不可用")

    manager_exe = tmp_path / "sdk" / "emulator" / "emulator.exe"
    manager = _AvdCore(  # type: ignore[arg-type]
        manager_exe, 60, False, cli=WindowErrorCli()
    )
    assert await manager.setVisible("2", True) == DeviceStatus.UNKNOWN


@pytest.mark.asyncio
async def test_manager_create_maps_all_options_and_fps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_AvdCore, "_check_components", lambda self: None)
    manager_exe = tmp_path / "sdk" / "emulator" / "emulator.exe"
    cli = _FakeManagerCli()
    manager = _AvdCore(manager_exe, 60, False, cli=cli)  # type: ignore[arg-type]
    assert (
        await manager.create_instance(
            "x", memory_mb=4096, cpu=4, fps=30, data_partition_gb=64, native_index=7
        )
        == "7"
    )
    assert cli.create_call == {
        "index": 7,
        "title": "x",
        "memory": 4096,
        "cpu": 4,
        "data_gb": 64,
        "fps": 30,
    }


@pytest.mark.asyncio
async def test_manager_create_timeout_preserves_cli_error_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_AvdCore, "_check_components", lambda self: None)
    manager_exe = tmp_path / "sdk" / "emulator" / "emulator.exe"
    cli = _FakeManagerCli()
    cli.create_error = CLIError("timeout", "超时", "查看日志")
    cli.status_after_create = "create_failed"
    manager = _AvdCore(manager_exe, 60, False, cli=cli)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="删掉它再新建") as exc_info:
        await manager.create_instance("x", native_index=7)
    assert isinstance(exc_info.value.__cause__, CLIError)
    assert exc_info.value.__cause__.code == "timeout"


@pytest.mark.asyncio
async def test_manager_create_error_without_leftover_instance_maps_normally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_AvdCore, "_check_components", lambda self: None)
    manager_exe = tmp_path / "sdk" / "emulator" / "emulator.exe"
    cli = _FakeManagerCli()
    cli.create_error = CLIError("invalid_argument", "内存不在范围内")
    manager = _AvdCore(manager_exe, 60, False, cli=cli)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="内存不在范围内"):
        await manager.create_instance("x", native_index=7)


@pytest.mark.asyncio
async def test_manager_cli_not_found_maps_to_not_found(tmp_path: Path) -> None:
    manager_exe = tmp_path / "sdk" / "emulator" / "emulator.exe"
    cli = _FakeManagerCli()
    manager = _AvdCore(manager_exe, 60, False, cli=cli)  # type: ignore[arg-type]
    assert await manager.getStatus("9") == DeviceStatus.NOT_FOUND


def test_service_cli_status_result_maps_components_and_prechecks(
    tmp_path: Path,
) -> None:
    result = service_module._cli_status_result(
        tmp_path,
        {
            "root": str(tmp_path),
            "components": [
                {
                    "id": "emulator",
                    "name": "模拟器",
                    "version": "0.2.0",
                    "build": "mas-36",
                    "installed": True,
                    "optional": False,
                    "local_sdk": True,
                }
            ],
            "items": [
                {
                    "id": "acceleration",
                    "ok": True,
                    "reason": "可用",
                    "advice": "",
                    "adb_address": "127.0.0.1:20087",
                }
            ],
        },
    )
    assert result["root"] == str(tmp_path)
    assert result["ready"] is True
    assert result["components"][0]["testPackage"] is True
    assert result["prechecks"][0]["adb_address"] == "127.0.0.1:20087"


# ---- 真的假 modavd 程序 -----------------------------------------------------------

#: 按 ``--json`` 约定输出的假 modavd：经 ``sys.executable`` 当子进程起，调用记进状态目录的
#: 独立的 ``call-*.json``；``plan.json`` 按命令给出数据、错误、原样输出、退出码，``sleep`` 先干等这么多秒，
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
spec = plan.get(command, {})
print("fake modavd log line", file=sys.stderr)
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

    async def python_close(root_path: Path, *, timeout: float) -> dict:
        raise AssertionError("modavd 可用时不该退回 Python 关机")

    monkeypatch.setattr(service_module, "_close_python_root", python_close)

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

    async def python_close(root_path: Path, *, timeout: float) -> dict:
        raise AssertionError("两个根目录都有可用的 modavd，不该退回 Python")

    monkeypatch.setattr(service_module, "_close_python_root", python_close)

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

    # 用户定的例外：关机前 modavd 坏了，退回 Python 的 sync + emu kill，不能不 sync 就被结束
    closed: list[Path] = []

    async def python_close(root_path: Path, *, timeout: float) -> dict:
        closed.append(root_path)
        return {}

    monkeypatch.setattr(service_module, "managed_roots", lambda configs: [root])
    monkeypatch.setattr(service_module, "_close_python_root", python_close)
    await service_module.close_running_instances([], timeout=10)
    assert closed == [root]

    # 更新器只按进程判断开着的实例，不起 modavd
    assert manager_module.running_instances(root) == []
    assert set(fake.commands()) == {"version"}


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
async def test_update_in_progress_refuses_and_never_starts_modavd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    root = _root_with_exe(tmp_path)
    monkeypatch.setattr(updater_module, "update_in_progress", lambda path: True)
    manager_exe = root / "sdk" / "emulator" / "emulator.exe"

    manager = await manager_module.build_manager(
        str(manager_exe), 60, runtime_policy=_policy()
    )
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
    # 面板轮询用到的查询改走文件和进程快照
    assert await manager.getStatus("7") == DeviceStatus.NOT_FOUND
    assert await manager.getInfo(None) == {}
    assert await manager.list_devices() == {}
    assert await manager.close("7") == DeviceStatus.OFFLINE
    snapshot = await service_module.status(str(root))
    assert snapshot["prechecks"] == []

    monkeypatch.setattr(service_module, "managed_roots", lambda configs: [root])
    await service_module.close_running_instances([], timeout=10)

    assert fake.calls() == []
    assert fake.launched == []


def _fake_processes(monkeypatch: pytest.MonkeyPatch, items: list[dict]) -> None:
    class _Process:
        def __init__(self, info: dict) -> None:
            self.info = info

    monkeypatch.setattr(
        stage_module.psutil,
        "process_iter",
        lambda attrs=None: [_Process(item) for item in items],
    )


def test_processes_using_counts_any_modavd_process_of_this_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    other = tmp_path / "other"
    _fake_processes(
        monkeypatch,
        [
            {
                "pid": 11,
                "name": "modavd.exe",
                "exe": str(root / "tools" / "modavd.exe"),
            },
            {"pid": 12, "name": "ModAVD.exe", "exe": str(root / "ModAVD.exe")},
            {
                "pid": 13,
                "name": "modavd.exe",
                "exe": str(other / "tools" / "modavd.exe"),
            },
            {"pid": 14, "name": "notepad.exe", "exe": str(tmp_path / "notepad.exe")},
        ],
    )
    assert [item["pid"] for item in stage_module.processes_using(root)] == [11, 12]


def test_swap_in_refuses_before_renaming_when_modavd_holds_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    (root / "sdk" / "emulator").mkdir(parents=True)
    _fake_processes(
        monkeypatch,
        [{"pid": 21, "name": "modavd.exe", "exe": str(root / "tools" / "modavd.exe")}],
    )
    monkeypatch.setattr(stage_module, "read_state", lambda path: {})
    monkeypatch.setattr(stage_module, "_check_staged", lambda path, state: None)
    monkeypatch.setattr(stage_module, "ensure_metadata_readable", lambda path: None)
    renamed: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        stage_module, "_rename", lambda src, dst: renamed.append((src, dst))
    )

    with pytest.raises(stage_module.SwapBlocked, match="modavd.exe"):
        stage_module.swap_in(root)
    assert renamed == []


def test_lingering_netsimd_asks_to_wait_instead_of_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    _fake_processes(
        monkeypatch,
        [
            {
                "pid": 31,
                "name": "netsimd.exe",
                "exe": str(root / "sdk" / "emulator" / "netsimd.exe"),
            }
        ],
    )
    with pytest.raises(stage_module.SwapBlocked, match="稍等再装"):
        stage_module.ensure_not_in_use(root, "装")


@pytest.mark.asyncio
async def test_open_retries_start_when_guest_script_push_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class StartCli:
        def __init__(self) -> None:
            self.starts = 0

        async def start(self, index: str, **kwargs: object) -> dict:
            self.starts += 1
            warnings = ["写客体脚本 mas-idlepoll.sh 失败: 文件被占用"]
            return {
                "warnings": warnings if self.starts == 1 else [],
                "instance": {"index": int(index), "status": "online"},
            }

    monkeypatch.setattr(_AvdCore, "_check_components", lambda self: None)
    monkeypatch.setattr(
        manager_module.host, "find_qemu_process", lambda avd, port: None
    )
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
    (root / "mas-avd.json").write_text(
        json.dumps({"instances": {"7": {"creationState": "creating"}}}),
        encoding="utf-8",
    )
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
        list={"data": {"instances": [creating]}},
    )
    monkeypatch.setattr(_AvdCore, "_check_components", lambda self: None)
    manager = await manager_module.build_manager(
        str(root / "sdk" / "emulator" / "emulator.exe"), 60, runtime_policy=_policy()
    )

    assert (await manager.getInfo(None))["7"].status == DeviceStatus.CREATING
    # modavd stop 不拦新建中的实例，MAS 自己拦：关机、重启会打断后台初始化
    with pytest.raises(RuntimeError, match="正在新建"):
        await manager.close("7")
    with pytest.raises(RuntimeError, match="正在新建"):
        await manager.restart("7", manual=True)
    with pytest.raises(RuntimeError, match="正在新建"):
        await manager.open("7", manual=True)
    assert not {"stop", "start", "restart"} & set(fake.commands())

    # 记着新建中、却问不到 modavd 的状态：不放行，免得正好打断新建
    fake.plan(
        version=version,
        status={"error": {"code": "internal", "message": "状态读不出"}, "exit": 1},
    )
    with pytest.raises(RuntimeError, match="查不到 modavd 的状态"):
        await manager.close("7")
    assert "stop" not in fake.commands()

    # 新建程序中途被结束：mas-avd.json 还记着 creating，modavd 按新建失败报；列表显示新建失败和原因，
    # 照常能关、能删
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
    monkeypatch.setattr(_AvdCore, "_check_components", lambda self: None)
    running: dict[str, object] = {"qemu": None}
    monkeypatch.setattr(
        manager_module.host, "find_qemu_process", lambda avd, port: running["qemu"]
    )
    # 静默模式开着：任务拉起无头，模拟器页手动启动带窗口
    manager = await manager_module.build_manager(
        str(root / "sdk" / "emulator" / "emulator.exe"), 60, runtime_policy=_policy()
    )

    # 0.3.0 没有 modavd restart：重启是先关机再开机，开机按这次的入口定有没有窗口
    await manager.restart("7")
    await manager.restart("7", manual=True)
    calls = [(item["command"], item["args"]) for item in fake.calls()]
    assert [command for command, _ in calls] == [
        "version",
        "stop",
        "start",
        "stop",
        "start",
    ]
    starts = [args for command, args in calls if command == "start"]
    assert "--window" not in starts[0]
    assert "--window" in starts[1]

    # 实例正无头运行：旧版 modavd 再要窗口也只是接着用，不重启、不切换；脚本每轮调的显示照旧不抛
    running["qemu"] = _Qemu("qemu-system-x86_64-headless.exe", "-no-window")
    before = len(fake.calls())
    assert (await manager.open("7", manual=True)).status == DeviceStatus.ONLINE
    await manager.setVisible("7", True)
    assert [item["command"] for item in fake.calls()[before:]] == [
        "start",
        "window",
        "status",
    ]

    # 0.3.0 碰上这种情况报 busy（退出码 5）：提示原样给用户，也不去关那台正在跑的实例
    fake.plan(
        start={
            "error": {
                "code": "busy",
                "message": "魔改 AVD 实例 7 正在无头运行",
                "advice": "先关机再换成带窗口",
            },
            "exit": 5,
        },
    )
    before = len(fake.calls())
    with pytest.raises(RuntimeError, match="正在无头运行（建议：先关机再换成带窗口）"):
        await manager.open("7", manual=True)
    assert [item["command"] for item in fake.calls()[before:]] == ["start"]


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
async def test_cancelled_create_looks_again_after_the_cli_is_ended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    # 收尾时限一到就结束 CLI：模拟器是脱离 CLI 起的，结束以后还要再找一次、把它关掉
    monkeypatch.setattr(cli_module, "_CREATE_CLEANUP_SECONDS", 0)
    cli = ModAvdCli(tmp_path)
    fake.plan(list={"data": {"instances": []}}, create={"hold": 20}, stop={"data": {}})
    task = asyncio.create_task(cli.create(index=8))
    await _until(lambda: "create" in fake.commands())
    fake.plan(
        list={"data": {"instances": [{"index": 8, "status": "create_failed"}]}},
        stop={"data": {}},
    )
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    stops = [item["args"] for item in fake.calls() if item["command"] == "stop"]
    assert stops == [["8"]]


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
