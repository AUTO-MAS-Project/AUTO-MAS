import asyncio
from types import SimpleNamespace

import pytest

from app.task.OkNte.tools import runtime
from app.task.OkNte.tools.runtime import OkNteProcessManager, runtime_executables
from app.task.Okww.tools.startup import start_okww
from app.utils import ProcessInfo
from app.utils.common.process import manager as process_manager

pytestmark = pytest.mark.asyncio

_DOWNLOAD = "Downloading onnxocr_ppocrv6-0.0.1-py3-none-any.whl (32.7 MB)"
_UPDATE_FAILURE = (
    "Update to version v1.5.10 failed: Command failed (python.exe -m pip install "
    "-r requirements.txt): exit code: 2"
)
_UPDATE_RECORD_FAILED = "Failed to record update progress: access denied"
_UPDATE_SAVE_FAILED = (
    "Update completed, but its state could not be saved: access denied"
)
_FAILED_UPDATE = {
    8: _DOWNLOAD,
    75: ("ERROR", "WARNING: Retrying after ReadTimeoutError"),
    85: ("ERROR", "pip._vendor.urllib3.exceptions.ReadTimeoutError: Read timed out."),
    89: "Rollback complete. The app is back on version v1.5.8.",
    90: ("ERROR", _UPDATE_FAILURE),
}


@pytest.mark.parametrize(
    ("progress", "runtime_at", "cancel_at", "expected_end", "tracking"),
    [
        pytest.param({8: _DOWNLOAD}, 400, None, 400, "auto", id="silent-download"),
        pytest.param({8: _DOWNLOAD}, 400, None, 400, "custom", id="custom-target"),
        pytest.param({8: _DOWNLOAD}, 400, None, 400, "gui", id="gui-target"),
        pytest.param(
            {2: "Fetching updates for existing repository...", 3: "Fetch complete."},
            None,
            None,
            60,
            "auto",
            id="routine-update-check",
        ),
        pytest.param({}, None, None, 60, "auto", id="ignores-previous-launch"),
        pytest.param({8: _DOWNLOAD}, None, None, 60, "standalone", id="standalone"),
        pytest.param(
            {8: _DOWNLOAD, 250: _DOWNLOAD}, None, None, 908, "auto", id="stale-repeat"
        ),
        pytest.param(
            dict.fromkeys(range(10, 330, 30), _DOWNLOAD),
            None,
            None,
            340,
            "auto",
            id="continuous-repeat",
        ),
        pytest.param(
            {second: f"Downloading package-{second}.whl" for second in (8, 800, 1600)},
            None,
            None,
            1800,
            "auto",
            id="total-limit",
        ),
        pytest.param({8: _DOWNLOAD}, None, 100, 100, "auto", id="cancel"),
        pytest.param(_FAILED_UPDATE, None, None, 90, "auto", id="update-failed"),
        pytest.param(_FAILED_UPDATE, None, None, 90, "okww", id="okww-update-failed"),
        pytest.param(
            {2: ("APP_SERVICE", "v1.5.10"), 3: ("ERROR", _UPDATE_RECORD_FAILED)},
            None,
            None,
            3,
            "auto",
            id="update-progress-cannot-be-recorded",
        ),
        pytest.param(
            {8: _DOWNLOAD, 90: ("ERROR", _UPDATE_SAVE_FAILED)},
            None,
            None,
            90,
            "okww",
            id="update-result-cannot-be-saved",
        ),
    ],
)
async def test_launcher_startup(
    tmp_path, monkeypatch, progress, runtime_at, cancel_at, expected_end, tracking
):
    custom_name = "custom-runtime.exe"
    program = tmp_path / "ok-nte.exe"
    program.touch()
    if tracking == "standalone":
        (tmp_path / "_internal").mkdir()

    manager = OkNteProcessManager(
        SimpleNamespace(
            Info=SimpleNamespace(RootPath=tmp_path),
            Script=SimpleNamespace(
                IfTrackProcess=True,
                TrackProcessName=custom_name if tracking in {"custom", "gui"} else "",
                TrackProcessExe="",
                TrackProcessCmdline="",
            ),
        )
    )
    logs = tmp_path / "logs"
    logs.mkdir()
    log = logs / "app.2026-11-24"
    app_id = "ok-ww" if tracking == "okww" else "ok-nte"
    emitter = "pyappify_lib::emitter:"
    log.write_text(f"{emitter} INFO [{app_id}]: {_DOWNLOAD}\n", encoding="utf-8")

    elapsed = 0
    fields = {
        "name": custom_name if tracking == "custom" else "ok-nte.exe",
        "exe": str(runtime_executables(tmp_path)[0]),
        "cmdline": ["ok-nte.exe"],
        "create_time": 1000 + (runtime_at or 0),
    }
    body = SimpleNamespace(
        pid=123, as_dict=lambda *, attrs: {attr: fields[attr] for attr in attrs}
    )
    clock = SimpleNamespace(monotonic=lambda: elapsed, time=lambda: 1000 + elapsed)
    monkeypatch.setattr(runtime, "time", clock)
    monkeypatch.setattr("app.task.pyappify_startup.time", clock)
    monkeypatch.setattr(process_manager, "time", clock)

    def running_processes():
        return [body] if runtime_at is not None and elapsed >= runtime_at else []

    monkeypatch.setattr(process_manager.psutil, "process_iter", running_processes)

    async def launch(*args, **kwargs):
        pass

    real_sleep = asyncio.sleep

    async def tick(delay):
        nonlocal elapsed
        if asyncio.current_task() is task:
            elapsed += 1
            if elapsed in progress:
                with log.open("a", encoding="utf-8") as stream:
                    entry = progress[elapsed]
                    level, message = (
                        entry if isinstance(entry, tuple) else ("INFO", entry)
                    )
                    if level == "APP_SERVICE":
                        stream.write(
                            f"pyappify_lib::app_service: Updating {app_id} to version {message}\n"
                        )
                    else:
                        stream.write(f"{emitter} {level} [{app_id}]: {message}\n")
        await real_sleep(0)

    async def run_in_thread(func, *args):
        return func(*args)

    monkeypatch.setattr(manager, "open_process", launch)
    monkeypatch.setattr(asyncio, "sleep", tick)
    monkeypatch.setattr(asyncio, "to_thread", run_in_thread)

    existing_tasks = asyncio.all_tasks()

    async def report(_):
        return None

    if tracking == "okww":
        startup = start_okww(
            manager, program, [], target=ProcessInfo(name="pythonw.exe"), on_log=report
        )
    else:
        startup = manager.open_oknte(program, use_custom_target=tracking != "gui")
    task = asyncio.create_task(startup)
    if cancel_at is not None:
        while not task.done() and elapsed < cancel_at:
            await real_sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    elif runtime_at is None:
        with pytest.raises(RuntimeError) as error:
            await task
        terminal_line = progress.get(expected_end)
        if terminal_line == ("ERROR", _UPDATE_FAILURE):
            assert f"{app_id.upper()} 启动器更新至 v1.5.10 失败" in str(error.value)
            assert "下载依赖时读取超时" in str(error.value)
        elif terminal_line == ("ERROR", _UPDATE_RECORD_FAILED):
            assert "v1.5.10" in str(error.value)
            assert "无法记录升级进度" in str(error.value)
        elif terminal_line == ("ERROR", _UPDATE_SAVE_FAILED):
            assert "无法保存升级结果" in str(error.value)
        assert manager.target_process is None
    else:
        await task
        assert manager.target_process is body
    assert expected_end <= elapsed <= expected_end + 1
    assert not (asyncio.all_tasks() - existing_tasks)
