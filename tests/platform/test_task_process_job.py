"""混合启动仍保持 Runtime 归属，并完整回收任务进程树。"""

import asyncio
import json
import os
import subprocess
import sys
import textwrap
import time
import uuid
from contextlib import suppress

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows 任务 Job")


@pytest.mark.asyncio
@pytest.mark.parametrize("launch_mode", ["created", "adopted", "adopted_during"])
@pytest.mark.parametrize("cleanup", ["scope", "path", "cancel"])
async def test_script_breakaway_survives_task_cleanup(
    tmp_path, monkeypatch, launch_mode, cleanup
):
    """脚本主动脱离的游戏保留，普通后代清理；显式关闭游戏仍然有效。"""
    import psutil
    import win32api
    import win32con
    import win32job

    from app.utils.common.process.manager import ProcessInfo, ProcessManager
    from app.utils.common.process.operations import kill_process_by_pid
    from app.utils.common.process.runner import create_subprocess, stop_process
    from app.utils.common.process.scope import TaskProcessScope, current_process_scope

    gate, result_file = tmp_path / "gate", tmp_path / "result.json"
    early_gate, early_pid = tmp_path / "early_gate", tmp_path / "early_pid"
    code = textwrap.dedent("""
        import json,subprocess,sys,time
        from pathlib import Path
        gate,result,early_gate,early_pid=map(Path,sys.argv[1:])
        children=[]
        try:
            for flags in (0,subprocess.CREATE_BREAKAWAY_FROM_JOB):
                ready = early_gate if flags == 0 else gate
                while not ready.exists(): time.sleep(.01)
                child=subprocess.Popen(
                    [sys.executable,'-I','-c','import time; time.sleep(60)'],
                    creationflags=flags,stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                children.append(child.pid)
                if flags == 0: early_pid.write_text(str(child.pid))
            result.write_text(json.dumps({'pids':children}))
        except OSError as error:
            result.write_text(json.dumps({'pids':children,'error':str(error)}))
        time.sleep(60)
    """)
    scope = TaskProcessScope()
    token = current_process_scope.set(scope)
    parent = None
    children = []
    try:
        if launch_mode == "created":
            parent = await create_subprocess(
                sys._base_executable,
                "-I",
                "-c",
                code,
                str(gate),
                str(result_file),
                str(early_gate),
                str(early_pid),
            )
            early_gate.touch()
            gate.touch()
        else:
            parent = await asyncio.create_subprocess_exec(
                sys._base_executable,
                "-I",
                "-c",
                code,
                str(gate),
                str(result_file),
                str(early_gate),
                str(early_pid),
            )
            assign = win32job.AssignProcessToJobObject
            open_process = win32api.OpenProcess

            def open_and_start(access, inherit, pid):
                if (
                    launch_mode == "adopted_during"
                    and pid == parent.pid
                    and access & win32con.PROCESS_SET_QUOTA
                    and not early_gate.exists()
                ):
                    # 旧实现此时已经拍完快照，但尚未真正登记根进程。
                    early_gate.touch()
                    deadline = time.monotonic() + 5
                    while not early_pid.exists():
                        assert time.monotonic() < deadline
                        time.sleep(0.01)
                return open_process(access, inherit, pid)

            def assign_and_start(job, handle):
                assign(job, handle)
                # 登记时放行；生产暂停期间不能等子进程，恢复后再核对结果。
                early_gate.touch()
                gate.touch()

            monkeypatch.setattr(win32api, "OpenProcess", open_and_start)
            monkeypatch.setattr(win32job, "AssignProcessToJobObject", assign_and_start)
            scope.track(psutil.Process(parent.pid))

        async with asyncio.timeout(5):
            while not result_file.exists():
                await asyncio.sleep(0.01)
        result = json.loads(result_file.read_text())
        children = [psutil.Process(pid) for pid in result["pids"]]
        assert "error" not in result, result.get("error")
        worker, game = children
        if cleanup == "scope":
            await scope.force_close()
        elif cleanup == "path":
            assert await kill_process_by_pid(parent.pid)
        else:
            await stop_process(parent, kill_tree=True)
        await asyncio.wait_for(parent.wait(), 3)
        _, alive = await asyncio.to_thread(psutil.wait_procs, [worker], timeout=3)
        assert not alive, "普通子进程必须随任务清理"
        assert game.is_running(), "已主动脱离的游戏不应被任务清理关闭"

        # 不关闭时已确认游戏存活；用户选择关闭时，独立游戏关闭入口仍须有效。
        manager = ProcessManager()
        await manager.search_process(
            ProcessInfo(pid=game.pid), timeout_seconds=3, owned=False
        )
        await manager.kill()
        assert not game.is_running()
    finally:
        current_process_scope.reset(token)
        if not scope.closed:
            await scope.force_close()
        for child in children:
            with suppress(psutil.NoSuchProcess):
                child.kill()
                await asyncio.to_thread(child.wait, timeout=3)
        if parent is not None:
            with suppress(ProcessLookupError):
                parent.kill()
            await asyncio.wait_for(parent.wait(), 3)


@pytest.mark.asyncio
async def test_failed_adoption_resumes_the_running_script(tmp_path, monkeypatch):
    """登记失败也必须恢复脚本，不能留下被 MAS 暂停的线程。"""
    import psutil
    import win32job

    from app.utils.common.process.scope import TaskProcessScope

    heartbeat = tmp_path / "heartbeat"
    parent = await asyncio.create_subprocess_exec(
        sys._base_executable,
        "-I",
        "-c",
        "import sys,time; from pathlib import Path; p=Path(sys.argv[1]); "
        "\nfor i in range(600):\n p.write_text(str(i)); time.sleep(.02)",
        str(heartbeat),
    )
    scope = TaskProcessScope()
    try:
        async with asyncio.timeout(5):
            while not heartbeat.exists():
                await asyncio.sleep(0.01)

        def deny_assignment(job, handle):
            raise PermissionError("injected Job assignment failure")

        monkeypatch.setattr(win32job, "AssignProcessToJobObject", deny_assignment)
        with pytest.raises(PermissionError, match="injected Job assignment failure"):
            scope.track(psutil.Process(parent.pid))
        before = heartbeat.read_text()
        async with asyncio.timeout(3):
            while heartbeat.read_text() in ("", before):
                await asyncio.sleep(0.01)
        assert parent.returncode is None
    finally:
        await scope.force_close()
        with suppress(ProcessLookupError):
            parent.kill()
        await asyncio.wait_for(parent.wait(), 3)


@pytest.mark.asyncio
async def test_game_launched_by_mas_is_closed_only_explicitly():
    """MAS 提前启动的游戏也不能被任务的兜底清理抢先关闭。"""
    from app.utils.common.process.manager import ProcessManager
    from app.utils.common.process.scope import TaskProcessScope, current_process_scope

    scope = TaskProcessScope()
    manager = ProcessManager()
    token = current_process_scope.set(scope)
    try:
        await manager.open_process(
            sys._base_executable,
            "-I",
            "-c",
            "import time; time.sleep(60)",
            breakaway=True,
            owned=False,
        )
        await scope.force_close()
        assert await manager.is_running()
        await manager.kill()
        assert not await manager.is_running()
    finally:
        current_process_scope.reset(token)
        await manager.kill()
        if not scope.closed:
            await scope.force_close()


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
@pytest.mark.parametrize(
    "child_before_registration,intermediate",
    [(False, False), (True, False), (False, True)],
)
async def test_adoption_reaps_descendants_but_never_a_looked_up_foreign_process(
    tmp_path, monkeypatch, child_before_registration, intermediate
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
        # 只隔离宿主进程目录；身份、后代查询与 Job 操作仍使用真实进程。
        known = [psutil.Process(unrelated.pid), psutil.Process(parent.pid)]

        def iter_known(attrs):
            for process in known:
                process.info = process.as_dict(attrs=attrs)
                yield process

        monkeypatch.setattr(psutil, "process_iter", iter_known)
        if child_before_registration:
            async with asyncio.timeout(5):
                while not pid_file.exists():
                    await asyncio.sleep(0.01)
        token = current_process_scope.set(scope)
        try:
            observer = ProcessManager()
            await observer.search_process(
                ProcessInfo(pid=unrelated.pid), timeout_seconds=3, owned=False
            )
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
