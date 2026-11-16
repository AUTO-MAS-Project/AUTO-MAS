"""混合启动仍保持 Runtime 归属，并完整回收任务进程树。"""

import asyncio
import json
import os
import subprocess
import sys
import textwrap
import uuid
from contextlib import suppress

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 任务 Job")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "launcher,first_breakaway,allow_breakaway,force_retry",
    [
        (launcher, first, allow, False)
        for launcher in ("async", "popen")
        for first in (False, True)
        for allow in (False, True)
    ]
    + [(launcher, True, True, True) for launcher in ("async", "popen")],
)
async def test_task_job_inside_runtime_job(
    launcher, first_breakaway, allow_breakaway, force_retry, record_property
):
    import ctypes

    import psutil
    import win32api
    import win32con
    import win32job
    import win32process

    name = f"AUTO_MAS_test_{uuid.uuid4().hex}"
    outer = win32job.CreateJobObject(None, name)
    info = win32job.QueryInformationJobObject(
        outer, win32job.JobObjectExtendedLimitInformation
    )
    info["BasicLimitInformation"]["LimitFlags"] = (
        win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        | (win32job.JOB_OBJECT_LIMIT_BREAKAWAY_OK if allow_breakaway else 0)
    )
    win32job.SetInformationJobObject(
        outer, win32job.JobObjectExtendedLimitInformation, info
    )
    code = textwrap.dedent("""
        import asyncio,ctypes,json,subprocess,sys
        import psutil,win32api,win32con,win32job
        from app.utils import process_platform
        from app.utils.common.process.runner import create_subprocess
        from app.utils.common.process.scope import TaskProcessScope,current_process_scope

        async def main():
            name,launcher,first_breakaway,allow_breakaway,force_retry=json.loads(sys.argv[1])
            outer=win32job.OpenJobObject(win32job.JOB_OBJECT_QUERY,False,name)
            scope=TaskProcessScope()
            unrelated=await asyncio.create_subprocess_exec(
                sys._base_executable,'-I','-c','import time; time.sleep(30)')
            retry_pending=force_retry
            if force_retry:
                native_async=asyncio.create_subprocess_exec
                native_popen=subprocess.Popen

                def check_flags(flags):
                    nonlocal retry_pending
                    if retry_pending and flags & process_platform.platform_process.breakaway_flags:
                        retry_pending=False
                        error=PermissionError('injected CREATE_BREAKAWAY_FROM_JOB rejection')
                        error.winerror=5
                        raise error

                async def spawn_async(*args,**kwargs):
                    check_flags(kwargs.get('creationflags',0))
                    return await native_async(*args,**kwargs)

                def spawn_popen(*args,**kwargs):
                    check_flags(kwargs.get('creationflags',0))
                    return native_popen(*args,**kwargs)

                asyncio.create_subprocess_exec=spawn_async
                subprocess.Popen=spawn_popen
            token=current_process_scope.set(scope)
            owned=[]
            descendants=[]
            memberships=[]
            try:
                for index,breakaway in enumerate((first_breakaway,not first_breakaway,first_breakaway)):
                    delay=0 if index==0 else 30
                    payload=(
                        'import subprocess,sys,time; '
                        "child=subprocess.Popen([sys.executable,'-I','-c','import time; time.sleep(30)'],"
                        'stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); '
                        f'print(child.pid,flush=True); time.sleep({delay})')
                    if launcher=='async':
                        process=await create_subprocess(
                            sys._base_executable,'-I','-c',payload,
                            breakaway=breakaway,stdout=subprocess.PIPE)
                        owned.append(process)
                        child_pid=int(await asyncio.wait_for(process.stdout.readline(),3))
                    else:
                        process=await asyncio.to_thread(
                            scope.popen,[sys._base_executable,'-I','-c',payload],
                            creationflags=process_platform.platform_process.breakaway_flags if breakaway else 0,
                            stdout=subprocess.PIPE)
                        owned.append(process)
                        child_pid=int(await asyncio.wait_for(asyncio.to_thread(process.stdout.readline),3))
                    descendants.append(psutil.Process(child_pid))
                    handle=win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION,False,child_pid)
                    try:
                        inherited=bool(win32job.IsProcessInJob(handle,outer))
                    finally:
                        handle.Close()
                    memberships.append(inherited)
                    expected=not breakaway or not allow_breakaway or (force_retry and index==0)
                    assert inherited == expected
                    if index==0:
                        if launcher=='async':
                            await asyncio.wait_for(process.wait(),3)
                        else:
                            await asyncio.to_thread(process.wait,timeout=3)
            finally:
                current_process_scope.reset(token)
                try:
                    await scope.force_close()
                    for process in owned:
                        if launcher=='async':
                            await asyncio.wait_for(process.wait(),3)
                        else:
                            await asyncio.to_thread(process.wait,timeout=3)
                    _,alive=await asyncio.to_thread(psutil.wait_procs,descendants,timeout=3)
                    assert not alive
                    assert unrelated.returncode is None
                    assert not retry_pending
                finally:
                    for child in descendants:
                        if child.is_running():
                            child.kill()
                    unrelated.kill()
                    await unrelated.wait()
                    outer.Close()
            print(json.dumps({'elevated':bool(ctypes.windll.shell32.IsUserAnAdmin()),
                              'memberships':memberships}),flush=True)
        asyncio.run(main())
    """)
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            code,
            json.dumps([name, launcher, first_breakaway, allow_breakaway, force_retry]),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        creationflags=0x00000004 | subprocess.CREATE_NO_WINDOW,
    )
    try:
        handle = win32api.OpenProcess(
            win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, process.pid
        )
        try:
            win32job.AssignProcessToJobObject(outer, handle)
        finally:
            handle.Close()
        for thread in psutil.Process(process.pid).threads():
            handle = win32api.OpenThread(
                win32con.THREAD_SUSPEND_RESUME, False, thread.id
            )
            try:
                win32process.ResumeThread(handle)
            finally:
                handle.Close()
        stdout, stderr = await asyncio.to_thread(process.communicate, timeout=20)
        assert process.returncode == 0, stderr.decode("utf-8", errors="replace")
        result = json.loads(stdout)
        assert result["elevated"] == bool(ctypes.windll.shell32.IsUserAnAdmin())
        record_property("elevated", result["elevated"])
        assert len(result["memberships"]) == 3
    finally:
        win32job.TerminateJobObject(outer, 1)
        outer.Close()
        if process.poll() is None:
            process.kill()
        await asyncio.to_thread(process.wait, timeout=5)


@pytest.mark.asyncio
async def test_failed_job_cleanup_still_reaps_the_other_group(monkeypatch):
    import win32job

    from app.utils.common.process.runner import create_subprocess
    from app.utils.common.process.scope import TaskProcessScope, current_process_scope

    scope = TaskProcessScope()
    token = current_process_scope.set(scope)
    processes = []
    terminate = win32job.TerminateJobObject
    try:
        for breakaway in (False, True):
            processes.append(
                await create_subprocess(
                    sys._base_executable,
                    "-I",
                    "-c",
                    "import time; time.sleep(30)",
                    breakaway=breakaway,
                )
            )

        failed = False

        def fail_first(job, code):
            nonlocal failed
            if not failed:
                failed = True
                raise OSError("injected Job termination failure")
            terminate(job, code)

        monkeypatch.setattr(win32job, "TerminateJobObject", fail_first)
        with pytest.raises(ExceptionGroup):
            await scope.force_close()
        assert scope.cleanup_failed
        await asyncio.wait_for(processes[1].wait(), 3)
        assert processes[0].returncode is None
    finally:
        current_process_scope.reset(token)
        for process in processes:
            with suppress(ProcessLookupError):
                process.kill()
            await asyncio.wait_for(process.wait(), 3)
        if not scope.closed:
            await scope.force_close()


@pytest.mark.asyncio
async def test_installer_created_during_stop_is_reaped(monkeypatch):
    from threading import Event

    from app.utils.common.process.scope import TaskProcessScope

    scope = TaskProcessScope()
    created, release = Event(), Event()
    processes = []
    popen = subprocess.Popen

    class DelayedPopen(popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            processes.append(self)
            created.set()
            assert release.wait(5)

    monkeypatch.setattr(subprocess, "Popen", DelayedPopen)
    worker = asyncio.create_task(
        asyncio.to_thread(
            scope.popen,
            [sys._base_executable, "-I", "-c", "import time; time.sleep(30)"],
        )
    )
    try:
        assert await asyncio.to_thread(created.wait, 3)
        await scope.force_close()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await worker
        await asyncio.to_thread(processes[0].wait, timeout=3)
    finally:
        release.set()
        await asyncio.gather(worker, return_exceptions=True)
        for process in processes:
            if process.poll() is None:
                process.kill()
            await asyncio.to_thread(process.wait, timeout=3)
        if not scope.closed:
            await scope.force_close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "child_before_registration,intermediate",
    [(False, False), (True, False), (False, True)],
)
async def test_adopted_process_descendants_stop_after_parent_exit(
    tmp_path, child_before_registration, intermediate
):
    """接管进程的已有及后续子进程都须随任务停止，任务外进程不受影响。"""
    import psutil

    from app.utils.common.process.manager import ProcessInfo, ProcessManager
    from app.utils.common.process.scope import TaskProcessScope, current_process_scope

    scope = TaskProcessScope()
    gate, pid_file, heartbeat = (
        tmp_path / name for name in ("gate", "pid", "heartbeat")
    )
    marker = f"mas-adoption-test-{uuid.uuid4().hex}"
    child_code = (
        "import os,sys,time; from pathlib import Path; "
        "Path(sys.argv[1]).write_text(str(os.getpid())); "
        "p=Path(sys.argv[2]); "
        "\nfor i in range(600):\n p.write_text(str(i)); time.sleep(.02)"
    )
    launch = (
        "subprocess.Popen([sys.executable,'-I','-c',sys.argv[2],"
        "sys.argv[3],sys.argv[4],sys.argv[5]])"
    )
    if intermediate:
        wrapper = "import subprocess,sys; subprocess.Popen([sys.executable,'-I','-c',*sys.argv[1:]])"
        launch = (
            f"subprocess.Popen([sys.executable,'-I','-c',{wrapper!r},sys.argv[2],"
            "sys.argv[3],sys.argv[4],sys.argv[5]])"
        )
    parent_code = (
        "import subprocess,sys,time; from pathlib import Path; "
        "gate=Path(sys.argv[1]); "
        f"\ndef start():\n {launch}"
        "\nif sys.argv[6]=='before': start()"
        "\nwhile not gate.exists(): time.sleep(.01)"
        "\nif sys.argv[6]=='after': start()"
    )
    unrelated = await asyncio.create_subprocess_exec(
        sys._base_executable, "-I", "-c", "import time; time.sleep(30)"
    )
    parent = await asyncio.create_subprocess_exec(
        sys._base_executable,
        "-I",
        "-c",
        parent_code,
        str(gate),
        child_code,
        str(pid_file),
        str(heartbeat),
        marker,
        "before" if child_before_registration else "after",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    child = None
    output = asyncio.create_task(parent.communicate())
    try:
        if child_before_registration:
            async with asyncio.timeout(5):
                while not pid_file.exists():
                    await asyncio.sleep(0.01)
        token = current_process_scope.set(scope)
        try:
            manager = ProcessManager()
            await manager.search_process(ProcessInfo(pid=parent.pid), timeout_seconds=3)
        finally:
            current_process_scope.reset(token)
        gate.touch()
        async with asyncio.timeout(5):
            while (
                not pid_file.exists()
                or parent.returncode is None
                or not heartbeat.exists()
            ):
                await asyncio.sleep(0.01)
        child = psutil.Process(int(pid_file.read_text()))
        child.create_time()
        assert marker in child.cmdline()
        assert not output.done(), "子进程应仍占用父进程的输出管道"
        await asyncio.wait_for(scope.force_close(), timeout=3)
        _, alive = await asyncio.to_thread(psutil.wait_procs, [child], timeout=1)
        assert not alive, "接管的父进程退出后，其子进程仍然存活"
        before = heartbeat.read_text()
        await asyncio.sleep(0.08)
        assert heartbeat.read_text() == before
        await asyncio.wait_for(asyncio.shield(output), timeout=1)
        assert unrelated.returncode is None
    finally:
        gate.touch()
        if child is None and pid_file.exists():
            child = psutil.Process(int(pid_file.read_text()))
        if child is not None:
            with suppress(psutil.NoSuchProcess):
                child.kill()
                await asyncio.to_thread(child.wait, timeout=3)
        with suppress(ProcessLookupError):
            parent.kill()
        await asyncio.wait_for(asyncio.shield(output), timeout=3)
        if not scope.closed:
            await scope.force_close()
        unrelated.kill()
        await unrelated.wait()


@pytest.mark.asyncio
@pytest.mark.parametrize("job_fails", [False, True])
async def test_failed_adoption_still_reaps_known_process_and_keeps_failure(
    monkeypatch, job_fails
):
    from app.utils.common.process.scope import TaskProcessScope

    scope = TaskProcessScope()
    process = await asyncio.create_subprocess_exec(
        sys._base_executable, "-I", "-c", "import time; time.sleep(30)"
    )

    def deny_adoption(pid, create_time):
        raise PermissionError("injected ownership registration failure")

    monkeypatch.setattr(scope._job, "adopt", deny_adoption)
    if job_fails:

        def deny_job_kill():
            raise PermissionError("injected Job termination failure")

        monkeypatch.setattr(scope._job, "kill", deny_job_kill)
    try:
        with pytest.raises(PermissionError):
            scope.track(process)
        assert scope.cleanup_failed
        if job_fails:
            with pytest.raises(PermissionError):
                await asyncio.wait_for(scope.force_close(), 3)
        else:
            await asyncio.wait_for(scope.force_close(), 3)
        await asyncio.wait_for(process.wait(), 3)
        assert scope.cleanup_failed, "终止已知进程不能把不完整的归属登记报告为成功"
    finally:
        with suppress(ProcessLookupError):
            process.kill()
        await process.wait()
        if not scope.closed:
            await scope.force_close()


@pytest.mark.asyncio
async def test_launcher_exit_before_adoption_keeps_successor_tracking(
    tmp_path, monkeypatch
):
    import psutil

    from app.utils.common.process.manager import ProcessInfo, ProcessManager
    from app.utils.common.process.scope import TaskProcessScope, current_process_scope

    script, gate, pid_file = (tmp_path / name for name in ("relay.py", "gate", "pid"))
    script.write_text(
        "import os,subprocess,sys,time\n"
        "from pathlib import Path\n"
        "gate=Path(sys.argv[1])\n"
        "if not gate.exists():\n"
        " gate.touch()\n"
        " print('ready',flush=True)\n"
        " sys.stdin.readline()\n"
        " subprocess.Popen([sys.executable,'-I',*sys.argv],stdin=subprocess.DEVNULL,"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        "else:\n"
        " Path(sys.argv[2]).write_text(str(os.getpid()))\n"
        " time.sleep(30)\n",
        encoding="utf-8",
    )
    command = [sys._base_executable, "-I", str(script), str(gate), str(pid_file)]
    launcher = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    scope = TaskProcessScope()
    successor = None
    adopt = scope._job.adopt

    def exit_before_adoption(pid, create_time):
        if pid == launcher.pid:
            # 扫描已命中，接管尚未开始：让真实启动器正常退出并交给后继。
            launcher.stdin.write(b"go\n")
            launcher.stdin.flush()
            assert launcher.wait(timeout=3) == 0
            launcher._handle.Close()
        return adopt(pid, create_time)

    monkeypatch.setattr(scope._job, "adopt", exit_before_adoption)
    token = current_process_scope.set(scope)
    try:
        assert launcher.stdout.readline() == b"ready\r\n"
        manager = ProcessManager(reseek_target=True)
        await manager.search_process(ProcessInfo(cmdline=command), timeout_seconds=3)
        assert not scope.cleanup_failed
        assert await manager.is_running(), "短命启动器退出后应继续跟踪接力进程"
        assert manager.main_pid != launcher.pid
        async with asyncio.timeout(3):
            while not pid_file.exists():
                await asyncio.sleep(0.01)
        successor = psutil.Process(int(pid_file.read_text()))
        assert manager.main_pid == successor.pid
        await scope.force_close()
        await asyncio.to_thread(successor.wait, timeout=3)
        assert not successor.is_running()
        assert not scope.cleanup_failed
    finally:
        current_process_scope.reset(token)
        if launcher.poll() is None:
            launcher.kill()
        launcher.wait(timeout=3)
        launcher.stdin.close()
        launcher.stdout.close()
        if successor is None and pid_file.exists():
            with suppress(psutil.NoSuchProcess):
                successor = psutil.Process(int(pid_file.read_text()))
        if successor is not None:
            with suppress(psutil.NoSuchProcess):
                successor.kill()
                successor.wait(timeout=3)
        if not scope.closed:
            await scope.force_close()


@pytest.mark.asyncio
async def test_stale_process_identity_does_not_adopt_reused_pid():
    import psutil

    from app.utils.windows.process import WindowsTaskProcessJob

    process = await asyncio.create_subprocess_exec(
        sys._base_executable, "-I", "-c", "import time; time.sleep(30)"
    )
    job = WindowsTaskProcessJob()
    try:
        created = psutil.Process(process.pid).create_time()
        job.adopt(process.pid, created - 1)
        job.kill()
        assert process.returncode is None, "旧身份不能接管并结束复用 PID 的其他进程"
        assert psutil.pid_exists(process.pid)
    finally:
        with suppress(ProcessLookupError):
            process.kill()
        await process.wait()
        job.close()


@pytest.mark.asyncio
async def test_lookup_of_existing_process_does_not_take_stop_ownership():
    from app.utils.common.process.manager import ProcessInfo, ProcessManager
    from app.utils.common.process.scope import TaskProcessScope, current_process_scope

    existing = await asyncio.create_subprocess_exec(
        sys._base_executable, "-I", "-c", "import time; time.sleep(30)"
    )
    scope = TaskProcessScope()
    token = current_process_scope.set(scope)
    try:
        manager = ProcessManager()
        await manager.search_process(
            ProcessInfo(pid=existing.pid), timeout_seconds=3, owned=False
        )
    finally:
        current_process_scope.reset(token)
    try:
        await asyncio.wait_for(scope.force_close(), 3)
        assert existing.returncode is None, "查找现有窗口不应取得结束该进程的权限"
    finally:
        existing.kill()
        await existing.wait()
        if not scope.closed:
            await scope.force_close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "backend_admin,finish", [(False, "exit"), (False, "denied"), (True, "kill")]
)
async def test_uac_launch_preserves_session_and_reports_external_cleanup(
    monkeypatch, backend_admin, finish
):
    import psutil
    import pywintypes
    import win32api
    import win32con

    from app.utils.common.process import manager as module
    from app.utils.common.process.scope import TaskProcessScope, current_process_scope

    command = [
        sys._base_executable,
        "-I",
        "-c",
        "import sys; print('ready', flush=True); sys.stdin.readline()",
        f"mas-uac-session-{uuid.uuid4().hex}",
    ]
    processes = []

    def launch(program, args, cwd):
        process = subprocess.Popen(
            [program, *args],
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        processes.append(process)
        assert process.stdout.readline() == b"ready\r\n"

    open_process = win32api.OpenProcess

    def open_with_integrity_boundary(access, inherit, pid):
        if (
            not backend_admin
            and processes
            and pid == processes[0].pid
            and access & (win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE)
        ):
            raise pywintypes.error(5, "OpenProcess", "injected UAC integrity boundary")
        return open_process(access, inherit, pid)

    scope = TaskProcessScope()
    token = current_process_scope.set(scope)
    try:
        with monkeypatch.context() as native:
            # 仅替换 UAC 启动和权限边界；进程扫描、会话跟踪与清理使用真实实现。
            native.setattr(module, "is_admin", lambda: backend_admin, raising=False)
            native.setattr(
                module.process_platform.platform_process,
                "prepare_elevated",
                lambda: launch,
            )
            native.setattr(win32api, "OpenProcess", open_with_integrity_boundary)
            manager = module.ProcessManager()
            await manager.open_process(
                command[0],
                *command[1:],
                elevated=True,
                target_process=module.ProcessInfo(cmdline=command),
            )
            assert await manager.is_running(), "UAC 启动成功后配置会话应继续等待用户"
            assert not scope.cleanup_failed
            process = processes[0]
            if finish == "exit":
                process.stdin.write(b"\n")
                process.stdin.flush()
                await asyncio.to_thread(process.wait, timeout=3)
                assert not await manager.is_running()
                await scope.force_close()
                assert not scope.cleanup_failed
            elif finish == "denied":
                kill = psutil.Process.kill

                def deny_external_stop(target):
                    if target.pid == process.pid:
                        raise psutil.AccessDenied(target.pid)
                    return kill(target)

                native.setattr(psutil.Process, "kill", deny_external_stop)
                with pytest.raises(RuntimeError, match="部分任务进程未能强制终止"):
                    await scope.force_close()
                assert scope.cleanup_failed
                assert await manager.is_running(), "没有结束权限不能把清理报告为成功"
            else:
                await scope.force_close()
                await asyncio.to_thread(process.wait, timeout=3)
                assert not await manager.is_running()
                assert not scope.cleanup_failed
    finally:
        current_process_scope.reset(token)
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
            process.stdin.close()
            process.stdout.close()
        if not scope.closed:
            await scope.force_close()


@pytest.mark.asyncio
@pytest.mark.parametrize("child_exits", [True, False])
async def test_adoption_open_failure_distinguishes_exited_and_live_child(
    tmp_path, monkeypatch, child_exits
):
    """A dead child must not block adoption; access denial for a live child must."""
    import time

    import psutil
    import pywintypes
    import win32api

    from app.utils.common.process.scope import TaskProcessScope

    ready, reaped = tmp_path / "ready", tmp_path / "reaped"
    sleeper = "import time; time.sleep(30)"
    launcher = (
        "import json,os,subprocess,sys,time; from pathlib import Path; "
        f"p=subprocess.Popen([sys.executable,'-I','-c',{sleeper!r}]); "
        "Path(sys.argv[1]).write_text(json.dumps([os.getpid(),p.pid])); "
        "time.sleep(30)"
    )
    parent_code = (
        "import subprocess,sys,time; from pathlib import Path; "
        "p=subprocess.Popen([sys.executable,'-I','-c',sys.argv[1],sys.argv[2]]); "
        f"s=subprocess.Popen([sys.executable,'-I','-c',{sleeper!r}]); "
        "\nwhile p.poll() is None: time.sleep(.01)"
        "\np._handle.Close(); Path(sys.argv[3]).touch(); time.sleep(30)"
    )
    parent = await asyncio.create_subprocess_exec(
        sys._base_executable, "-I", "-c", parent_code, launcher, str(ready), str(reaped)
    )
    unrelated = await asyncio.create_subprocess_exec(
        sys._base_executable, "-I", "-c", sleeper
    )
    scope = TaskProcessScope()
    known = []
    try:
        async with asyncio.timeout(3):
            while not ready.exists() or not ready.read_text():
                await asyncio.sleep(0.01)
        child_pid, grandchild_pid = json.loads(ready.read_text())
        known = psutil.Process(parent.pid).children(recursive=True)
        assert {child_pid, grandchild_pid} <= {p.pid for p in known}
        open_process = win32api.OpenProcess

        def exit_or_deny_before_open(access, inherit, pid):
            if pid == child_pid:
                if not child_exits:
                    raise pywintypes.error(5, "OpenProcess", "injected access denial")
                child = psutil.Process(pid)
                child.kill()
                child.wait(timeout=3)
                # Wait for the real parent to close its dead child's final handle.
                deadline = time.monotonic() + 3
                while not reaped.exists():
                    if time.monotonic() >= deadline:
                        raise TimeoutError("parent did not reap exited child")
                    time.sleep(0.01)
            return open_process(access, inherit, pid)

        with monkeypatch.context() as native:
            native.setattr(win32api, "OpenProcess", exit_or_deny_before_open)
            if child_exits:
                scope.track(parent)
                assert not scope.cleanup_failed
            else:
                with pytest.raises(pywintypes.error):
                    scope.track(parent)
                assert scope.cleanup_failed
        await asyncio.wait_for(scope.force_close(), 3)
        await asyncio.wait_for(parent.wait(), 3)
        _, alive = await asyncio.to_thread(psutil.wait_procs, known, timeout=1)
        assert not alive, "remaining siblings and descendants must still be reaped"
        assert unrelated.returncode is None
    finally:
        for target in known:
            with suppress(psutil.NoSuchProcess):
                target.kill()
        with suppress(ProcessLookupError):
            parent.kill()
        await parent.wait()
        unrelated.kill()
        await unrelated.wait()
        if not scope.closed:
            await scope.force_close()
