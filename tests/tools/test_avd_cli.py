"""modavd CLI 的 JSON、选路、状态与时限契约测试。"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Sequence

import pytest

from app.models.emulator import DeviceStatus, EmulatorRuntimePolicy
from app.utils.common.emulator2.avd import cli as cli_module
from app.utils.common.emulator2.avd import manager as manager_module
from app.utils.common.emulator2.avd import service as service_module
from app.utils.common.emulator2.avd import update_stage as stage_module
from app.utils.common.emulator2.avd import updater as updater_module
from app.utils.common.emulator2.avd.cli import (
    CREATE_PROCESS_MARGIN_SECONDS,
    CREATE_TIMEOUT_SECONDS,
    SUPPORTED_PROTOCOL,
    CLIError,
    ModAvdCli,
    ModAvdUnavailable,
    ProcessOutput,
    _run_process,
    map_cli_error,
    map_status,
    resolve_cli,
)
from app.utils.common.emulator2.avd.host import AdbPortConflict
from app.utils.common.emulator2.avd.manager import _AvdCore
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
        return {"protocol": SUPPORTED_PROTOCOL}

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
async def test_start_stop_restart_flags_and_timeouts(tmp_path: Path) -> None:
    fake = _FakeRunner(ProcessOutput(0, '{"ok":true,"data":{}}', ""))
    cli = _cli(tmp_path, fake)

    await cli.start(3, window=True, timeout=10)
    args, process_timeout = fake.calls[-1][0], fake.calls[-1][1]
    assert args[4:] == ["start", "3", "--window", "--timeout", "10"]
    assert process_timeout >= 190

    await cli.stop(3)
    assert fake.calls[-1][0][4:] == ["stop", "3"]
    assert fake.calls[-1][1] == 90

    await cli.restart(3, force=True, timeout=20)
    assert fake.calls[-1][0][4:] == [
        "restart",
        "3",
        "--timeout",
        "20",
        "--force",
    ]

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
    assert "--timeout" in calls[0][0]
    assert "--timeout" not in calls[1][0]
    assert (
        calls[0][1]
        == calls[1][1]
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
        ("create_failed", "", DeviceStatus.ERROR),
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
    called = False

    async def cleanup(_process: asyncio.subprocess.Process) -> None:
        nonlocal called
        called = True

    with pytest.raises(CLIError) as exc_info:
        await _run_process(
            [sys.executable, str(script)], timeout=0.05, timeout_handler=cleanup
        )
    assert called is True
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
        return {"version": "0.36.0", "protocol": SUPPORTED_PROTOCOL}

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
        return {"version": "0.2.0", "protocol": SUPPORTED_PROTOCOL}

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
#: ``calls.log``；``plan.json`` 按命令给出数据、错误、原样输出、退出码，``hold`` 让进程活着直到
#: 收到 ``stop``，``bridge_seconds`` 先起一个命令行带 ``modavd-bridge.ps1`` 的子进程（装桥）。
_FAKE_MODAVD = r"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
state = Path(os.environ["FAKE_MODAVD_STATE"])
args = sys.argv[1:]
root = args[args.index("--root") + 1] if "--root" in args else ""
command = args[args.index("--json") + 1]
rest = args[args.index("--json") + 2 :]
with (state / "calls.log").open("a", encoding="utf-8") as log:
    log.write(json.dumps({"at": time.time(), "root": root, "command": command, "args": rest}) + "\n")
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
            args: Sequence[str],
            timeout: float,
            timeout_handler: object = None,
            breakaway: bool = False,
        ) -> ProcessOutput:
            self.launched.append((time.monotonic(), list(args)[1:]))
            return await real_run_process(
                [sys.executable, "-I", str(self.script), *list(args)[1:]],
                timeout,
                timeout_handler=timeout_handler,  # type: ignore[arg-type]
                breakaway=breakaway,
            )

        # ModAvdCli 默认 runner 在构造时取模块里的 _run_process，换掉它就覆盖所有调用点
        monkeypatch.setattr(cli_module, "_run_process", run)

    def plan(self, **commands: dict) -> None:
        (self.state / "plan.json").write_text(
            json.dumps(commands, ensure_ascii=False), encoding="utf-8"
        )

    def calls(self) -> list[dict]:
        log = self.state / "calls.log"
        if not log.exists():
            return []
        return [
            json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
        ]

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
    fake.plan(start={"data": {}}, restart={"data": {}})
    monkeypatch.setattr(cli_module, "START_STAGGER_SECONDS", 0.6)
    monkeypatch.setattr(cli_module, "_next_start_at", 0.0)

    await asyncio.gather(
        ModAvdCli(tmp_path / "a").start(7, timeout=60),
        ModAvdCli(tmp_path / "b").restart(8, timeout=60),
    )

    times = sorted(at for at, args in fake.launched)
    assert len(times) == 2
    assert times[1] - times[0] >= 0.5
    assert {item["root"] for item in fake.calls()} == {
        str(tmp_path / "a"),
        str(tmp_path / "b"),
    }


@pytest.mark.asyncio
async def test_power_close_uses_stop_all_and_keeps_partial_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    root = _root_with_exe(tmp_path)
    fake.plan(
        version={"data": {"version": "0.1.0", "protocol": SUPPORTED_PROTOCOL}},
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

    assert result == {str(root): "closed"}
    stop_calls = [item for item in fake.calls() if item["command"] == "stop"]
    assert [item["args"] for item in stop_calls] == [["--all"]]


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
    version = {"data": {"version": "0.2.0", "protocol": SUPPORTED_PROTOCOL}}
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

    # 新建程序中途被结束：mas-avd.json 还记着 creating，modavd 按新建失败报，照常能关
    fake.plan(
        version=version,
        status={"data": {**creating, "status": "create_failed", "busy": ""}},
        stop={"data": {}},
    )
    assert await manager.close("7") == DeviceStatus.OFFLINE
    assert fake.commands()[-1] == "stop"


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
async def test_running_instance_keeps_its_window_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeModavd(tmp_path, monkeypatch)
    root = _root_with_exe(tmp_path)
    fake.plan(
        version={"data": {"version": "0.2.0", "protocol": SUPPORTED_PROTOCOL}},
        start={"data": {"instance": {"index": 7, "status": "online"}}},
        window={"data": {"index": 7, "windows": 0}},
        status={"data": {"index": 7, "status": "online"}},
    )
    monkeypatch.setattr(_AvdCore, "_check_components", lambda self: None)
    running = {"qemu": _Qemu("qemu-system-x86_64-headless.exe", "-no-window")}
    monkeypatch.setattr(
        manager_module.host, "find_qemu_process", lambda avd, port: running["qemu"]
    )
    # 静默模式开着：任务拉起要无头，模拟器页手动启动要窗口
    manager = await manager_module.build_manager(
        str(root / "sdk" / "emulator" / "emulator.exe"), 60, runtime_policy=_policy()
    )

    # 正无头运行时手动要窗口：明确拒绝，不能当成已在运行接管
    with pytest.raises(RuntimeError, match="先关机再启动"):
        await manager.open("7", manual=True)
    with pytest.raises(RuntimeError, match="要窗口请先关机"):
        await manager.setVisible("7", True, manual=True)
    assert not {"start", "window"} & set(fake.commands())
    # 脚本每轮调的显示照旧不抛
    await manager.setVisible("7", True)

    # 任务拉起和运行方式一致，照常接着用
    assert (await manager.open("7")).status == DeviceStatus.ONLINE
    # 任务要无头、实例带窗口：照常接着用，静默模式随后会把窗口隐藏
    running["qemu"] = _Qemu("qemu-system-x86_64.exe")
    await manager.open("7")
    await manager.open("7", manual=True)
    assert fake.commands().count("start") == 3
