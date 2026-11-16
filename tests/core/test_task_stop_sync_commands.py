"""同步更新工具与异步补丁工具都须随所属任务结束。"""

import asyncio
import subprocess
import sys
import uuid
from contextlib import suppress

import psutil
import pytest

from app.utils.common.process.runner import run_process_sync
from app.utils.common.process.scope import TaskProcessScope, current_process_scope


def _heartbeat_command(tmp_path):
    marker = f"mas-script-stop-{uuid.uuid4().hex}"
    pid_file, heartbeat = tmp_path / "child.pid", tmp_path / "heartbeat"
    child = (
        "import os,sys,time; from pathlib import Path; "
        "Path(sys.argv[1]).write_text(str(os.getpid())); p=Path(sys.argv[2]); "
        "\nfor i in range(1500):\n p.write_text(str(i)); time.sleep(.02)"
    )
    wrapper = (
        "import subprocess,sys; "
        "subprocess.Popen([sys.executable,'-I','-c',sys.argv[1],*sys.argv[2:]])"
    )
    return (
        [
            sys._base_executable,
            "-I",
            "-c",
            wrapper,
            child,
            str(pid_file),
            str(heartbeat),
            marker,
        ],
        pid_file,
        heartbeat,
        marker,
    )


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "win32", reason="Windows 任务进程组")
@pytest.mark.parametrize("entry", ["sync_update", "wuthering_patch"])
async def test_update_helpers_stop_writing_after_task_scope_closes(
    tmp_path, monkeypatch, entry
):
    command, pid_file, heartbeat, marker = _heartbeat_command(tmp_path)
    native_spawn = asyncio.create_subprocess_exec
    unrelated = await native_spawn(
        sys._base_executable, "-I", "-c", "import time; time.sleep(30)"
    )
    scope = TaskProcessScope()
    token = current_process_scope.set(scope)
    child = None
    expected_stop_errors = ()
    try:
        if entry == "sync_update":
            operation = asyncio.create_task(
                asyncio.to_thread(
                    run_process_sync, command, capture_output=True, timeout=15
                )
            )
        else:
            from app.services.common.wuthering_waves import updater

            expected_stop_errors = (updater.HpatchzApplyError,)

            async def patch_binary(*args, **kwargs):
                return await native_spawn(*command, **kwargs)

            monkeypatch.setattr(asyncio, "create_subprocess_exec", patch_binary)
            operation = asyncio.create_task(
                updater._run_hpatchz(
                    tmp_path / "hpatchz.exe",
                    tmp_path,
                    tmp_path / "blob",
                    tmp_path / "out",
                )
            )
    finally:
        current_process_scope.reset(token)
    try:
        async with asyncio.timeout(5):
            while not heartbeat.exists():
                await asyncio.sleep(0.01)
        child = psutil.Process(int(pid_file.read_text()))
        child.create_time()
        assert marker in child.cmdline()
        assert not operation.done(), "后代仍占用输出管道，应尚未收到 EOF"
        await asyncio.wait_for(scope.force_close(), 3)
        _, alive = await asyncio.to_thread(psutil.wait_procs, [child], timeout=1)
        assert not alive, "任务结束后更新工具的后代仍在写文件"
        before = heartbeat.read_text()
        await asyncio.sleep(0.08)
        assert heartbeat.read_text() == before
        with suppress(*expected_stop_errors):
            await asyncio.wait_for(asyncio.shield(operation), 2)
        assert unrelated.returncode is None
    finally:
        if child is None and pid_file.exists():
            child = psutil.Process(int(pid_file.read_text()))
        if child is not None:
            with suppress(psutil.NoSuchProcess):
                child.kill()
                await asyncio.to_thread(child.wait, timeout=3)
        if not scope.closed:
            await scope.force_close()
        with suppress(*expected_stop_errors):
            await asyncio.wait_for(asyncio.shield(operation), 3)
        unrelated.kill()
        await unrelated.wait()


@pytest.mark.asyncio
async def test_scoped_sync_command_preserves_output_and_timeout(tmp_path):
    scope = TaskProcessScope()
    token = current_process_scope.set(scope)
    try:
        result = await asyncio.to_thread(
            run_process_sync,
            [
                sys._base_executable,
                "-I",
                "-c",
                "import sys; print('output'); print('error', file=sys.stderr); raise SystemExit(7)",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        assert (result.returncode, result.stdout.strip(), result.stderr.strip()) == (
            7,
            "output",
            "error",
        )
        with pytest.raises(subprocess.TimeoutExpired):
            await asyncio.to_thread(
                run_process_sync,
                [sys._base_executable, "-I", "-c", "import time; time.sleep(30)"],
                capture_output=True,
                timeout=0.1,
            )
        assert not scope.cleanup_failed
    finally:
        current_process_scope.reset(token)
        await scope.force_close()
