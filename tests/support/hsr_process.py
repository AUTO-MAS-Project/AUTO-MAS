"""Isolated M7A process fixtures shared by lifecycle and review tests."""

import asyncio
import os
import sys
from contextlib import suppress

import psutil
import pytest

from app.models.config import HSRConfig
from app.task.HSR.tools import m7a_runtime, native_control
from app.task.HSR.tools.account_switch import configure_m7a_runner
from app.utils import ProcessManager
from app.utils.common.process import runner as process_runner


@pytest.fixture
def simulator(tmp_path, monkeypatch):
    # 模拟脚本输出固定为 UTF-8；显式 GBK 字节流模拟中文系统的原生输出。
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")
    monkeypatch.setattr(
        process_runner, "ENCODINGS", ("utf-8", "utf-8-sig", "gbk", "gb18030")
    )
    original_open = ProcessManager.open_process
    original_runner = native_control.M7ARunner
    processes = []
    config = tmp_path / "config.yaml"
    config.write_bytes(b"sentinel: unchanged\n")
    (tmp_path / "March7th Assistant.exe").touch()

    async def open_python(manager, program, *args, **kwargs):
        ready = tmp_path / f"python-ready-{len(processes)}"
        kwargs["env"] = {
            **(kwargs.get("env") or os.environ),
            "PYTHONIOENCODING": "utf-8",
            "AUTO_MAS_SIMULATOR_READY": str(ready),
        }
        await original_open(
            manager,
            sys.executable,
            "-u",
            str(tmp_path / "simulate.py"),
            *args,
            **kwargs,
        )
        processes.append(manager.main_process)
        # 命令预算验证脚本生命周期，不把 CI 上 Python 解释器冷启动算进去。
        await wait_until(ready.exists)

    def short_grace(*args, **kwargs):
        return original_runner(*args, completion_grace_timeout=0.15, **kwargs)

    monkeypatch.setattr(ProcessManager, "open_process", open_python)
    monkeypatch.setattr(native_control, "M7ARunner", short_grace)

    def build(body, *, callback=None, managed=False, platform=None):
        startup = (
            "import os, pathlib\n"
            "pathlib.Path(os.environ['AUTO_MAS_SIMULATOR_READY']).touch()\n"
        )
        (tmp_path / "simulate.py").write_text(startup + body, encoding="utf-8")
        config = HSRConfig(Game={"Platform": platform}) if platform else None
        if managed:
            runner = m7a_runtime.M7ARunner(
                tmp_path,
                completion_grace_timeout=0.15,
                output_line_callback=callback,
            )
            if config is not None:
                configure_m7a_runner(runner, config)
            return runner
        return native_control.M7ADirectControlSession(
            tmp_path, lambda _: None, script_config=config
        )

    yield build, tmp_path, processes
    assert config.read_bytes() == b"sentinel: unchanged\n"


async def wait_until(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.005)


async def cleanup(processes, root):
    # 只清理本用例创建的模拟后代，客户端策略不应杀掉游戏一类的后代。
    pid_file = root / "child.pid"
    if pid_file.exists():
        with suppress(psutil.NoSuchProcess):
            child = psutil.Process(int(pid_file.read_text()))
            child.kill()
            await asyncio.to_thread(psutil.wait_procs, [child], timeout=1)
    for proc in processes:
        if proc.returncode is None:
            with suppress(ProcessLookupError):
                proc.kill()
        await asyncio.wait_for(proc.wait(), timeout=3)


def inherited_child(*, code=7, marker=False, tail=False):
    child = (
        "import time, sys; time.sleep(0.04); "
        "print('无法切换到指定游戏界面', file=sys.stderr, flush=True); time.sleep(30)"
        if tail
        else "import time; time.sleep(30)"
    )
    return (
        "import subprocess, pathlib, sys\n"
        f"child = subprocess.Popen([sys.executable, '-u', '-c', {child!r}], close_fds=False)\n"
        "pathlib.Path('child.pid').write_text(str(child.pid))\n"
        "print('native output', flush=True)\n"
        + ("print('停止运行', flush=True)\n" if marker else "")
        + f"sys.exit({code})\n"
    )
