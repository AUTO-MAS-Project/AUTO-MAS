"""modavd CLI 的 JSON、选路、状态与时限契约测试。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Sequence

import pytest

from app.models.emulator import DeviceStatus
from app.utils.common.emulator2.avd import manager as manager_module
from app.utils.common.emulator2.avd import service as service_module
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
        ("creating", "", DeviceStatus.STARTING),
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
async def test_manager_create_maps_all_options_and_fps(tmp_path: Path) -> None:
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
async def test_manager_create_timeout_preserves_cli_error_cause(tmp_path: Path) -> None:
    manager_exe = tmp_path / "sdk" / "emulator" / "emulator.exe"
    cli = _FakeManagerCli()
    cli.create_error = CLIError("timeout", "超时", "查看日志")
    manager = _AvdCore(manager_exe, 60, False, cli=cli)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError) as exc_info:
        await manager.create_instance("x", native_index=7)
    assert isinstance(exc_info.value.__cause__, CLIError)
    assert exc_info.value.__cause__.code == "timeout"


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
