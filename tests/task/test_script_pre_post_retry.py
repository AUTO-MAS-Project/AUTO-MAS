import asyncio
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import psutil
import pytest

from app.models.task import LogRecord, ScriptItem, UserItem
from app.task.base import ScriptAutoProxyBase


class Proxy(ScriptAutoProxyBase):
    """执行前置脚本后失败，验证基类负责成对收尾。"""

    run_timeout_seconds = 10

    def __init__(self, user_config):
        super().__init__()
        self.cur_user_config = user_config
        self.cur_user_item = UserItem("test", "测试账号", "运行")
        self.cur_user_item.log_record[datetime.now()] = LogRecord(status="运行中")
        self.script_info = ScriptItem("script", "测试脚本", "运行")
        self.crashed = False
        self.finalized = False

    async def main_task(self):
        await self.run_user_scripts_before()
        raise RuntimeError("任务失败")

    async def final_task(self):
        self.finalized = True

    async def on_crash(self, error):
        self.crashed = True


async def _run(proxy):
    async with asyncio.TaskGroup() as group:
        await proxy._execute_task(group)


@pytest.mark.asyncio
async def test_cancelled_account_before_script_never_opens_emulator(tmp_path):
    """真实前置脚本的后台服务持管道时，停止仍阻断后续账号动作并完成收尾。"""
    from app.models.config import SrcUserConfig

    pid_file = tmp_path / "pids.txt"
    before = tmp_path / "before.py"
    before.write_text(
        "import os, subprocess, sys\nfrom pathlib import Path\n"
        "child = subprocess.Popen([sys.executable, '-I', '-c', "
        "'import time; time.sleep(30)'], stdin=subprocess.DEVNULL, "
        "stdout=sys.stdout, stderr=sys.stderr, close_fds=True)\n"
        f"Path({str(pid_file)!r}).write_text(f'{{os.getpid()}} {{child.pid}}')\n",
        encoding="utf-8",
    )
    open_emulator = AsyncMock()

    class AccountProxy(Proxy):
        async def main_task(self):
            await self.run_user_scripts_before()
            await open_emulator()

    config = SrcUserConfig()
    await config.activate()
    config.Info.IfScriptBeforeTask = True
    await config.commit()
    config.Info.ScriptBeforeTask = str(before)
    await config.commit()
    proxy = AccountProxy(config)
    running = asyncio.create_task(_run(proxy))
    child = None
    try:
        async with asyncio.timeout(5):
            while not pid_file.exists():
                await asyncio.sleep(0.01)
            parent_pid, child_pid = map(int, pid_file.read_text().split())
            child = psutil.Process(child_pid)
            while psutil.pid_exists(parent_pid):
                await asyncio.sleep(0.01)
        running.cancel()
        done, _ = await asyncio.wait({running}, timeout=3)
        assert done, "前置脚本的后台服务不能让停止一直等待"
        open_emulator.assert_not_awaited()
        with pytest.raises(asyncio.CancelledError):
            await running
        assert proxy.stopped_manually and proxy.finalized and not proxy.crashed
    finally:
        if child is not None:
            with suppress(psutil.NoSuchProcess):
                child.kill()
            await asyncio.to_thread(child.wait, timeout=5)
        if not running.done():
            running.cancel()
        await asyncio.gather(running, return_exceptions=True)


def _record_scripts(monkeypatch, module="app.task.base"):
    calls = []

    async def fake_execute(script_path, task_name):
        calls.append(Path(script_path))
        return True

    monkeypatch.setattr(f"{module}.execute_script_task", fake_execute)
    return calls


@pytest.mark.parametrize(
    "config_name",
    ["MaaUserConfig", "SrcUserConfig", "GeneralUserConfig"],
)
def test_user_scripts_pair_on_terminal_failure(config_name, tmp_path, monkeypatch):
    """任务失败仍执行后置脚本，重复收尾不会再次执行。"""

    from app.models import config as configs

    calls = _record_scripts(monkeypatch)
    before = tmp_path / "before.bat"
    before.write_text("@echo off", encoding="utf-8")
    after = tmp_path / "after.bat"
    after.write_text("@echo off", encoding="utf-8")

    async def scenario():
        cfg = getattr(configs, config_name)()
        await cfg.activate()
        cfg.Info.IfScriptBeforeTask = True
        await cfg.commit()
        cfg.Info.ScriptBeforeTask = str(before)
        await cfg.commit()
        cfg.Info.IfScriptAfterTask = True
        await cfg.commit()
        cfg.Info.ScriptAfterTask = str(after)
        await cfg.commit()
        proxy = Proxy(cfg)
        await _run(proxy)
        assert calls == [before, after]
        await proxy.run_user_scripts_after()
        return proxy

    proxy = asyncio.run(scenario())

    assert calls == [before, after]
    assert proxy.crashed and proxy.finalized


def test_after_skipped_when_before_never_ran(tmp_path, monkeypatch):
    """前置检查失败、尚未执行前置脚本时，后置脚本也不执行。"""

    from app.models import config as configs

    calls = _record_scripts(monkeypatch)
    after = tmp_path / "after.bat"
    after.write_text("@echo off", encoding="utf-8")

    class NoHookProxy(Proxy):
        async def main_task(self):
            raise RuntimeError("前置检查失败")

    async def scenario():
        cfg = configs.GeneralUserConfig()
        await cfg.activate()
        cfg.Info.IfScriptAfterTask = True
        await cfg.commit()
        cfg.Info.ScriptAfterTask = str(after)
        await cfg.commit()
        proxy = NoHookProxy(cfg)
        await _run(proxy)
        return proxy

    proxy = asyncio.run(scenario())
    assert calls == []
    assert proxy.crashed and proxy.finalized


def test_hsr_before_after_scripts(tmp_path, monkeypatch):
    """HSR 独立实现的用户级前后脚本：开启时各执行一次，关闭时跳过。"""

    calls = _record_scripts(monkeypatch, "app.task.HSR.tools.extra_script")
    from app.task.HSR.tools.extra_script import (
        run_script_after_task,
        run_script_before_task,
    )

    before = tmp_path / "before.bat"
    before.write_text("@echo off", encoding="utf-8")
    after = tmp_path / "after.bat"
    after.write_text("@echo off", encoding="utf-8")

    async def scenario():
        from app.models.config import HSRUserConfig

        cfg = HSRUserConfig()
        await cfg.activate()
        cfg.Info.IfScriptBeforeTask = True
        await cfg.commit()
        cfg.Info.ScriptBeforeTask = str(before)
        await cfg.commit()
        cfg.Info.IfScriptAfterTask = True
        await cfg.commit()
        cfg.Info.ScriptAfterTask = str(after)
        await cfg.commit()
        await run_script_before_task(cfg)
        await run_script_after_task(cfg)

        off = HSRUserConfig()
        await off.activate()
        off.Info.IfScriptBeforeTask = False
        await off.commit()
        off.Info.IfScriptAfterTask = False
        await off.commit()
        await run_script_before_task(off)
        await run_script_after_task(off)

    asyncio.run(scenario())
    assert calls == [before, after]
