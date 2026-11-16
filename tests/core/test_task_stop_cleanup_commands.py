"""停止确认期间完成设备、游戏与后置脚本清理，再交付本地结果。"""

import asyncio
import sys
from contextlib import suppress
from types import SimpleNamespace

import pytest

from app.models.config import BetterGIConfig, BetterGIUserConfig
from app.services import execute_script_task
from app.task.BetterGI.AutoProxy import AutoProxyTask as BetterGITask
from app.task.emulator_core import close_emulator
from app.utils.common.process.runner import ProcessRunner, create_subprocess
from app.utils.common.process.scope import TaskProcessScope, current_process_scope
from tests.config_support import activate_config
from tests.task_stop_support import StopTask, add_script


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["emulator", "game", "after_script"])
async def test_stop_confirms_cleanup_commands_before_saving_results(
    monkeypatch, tmp_path, isolated_app_paths, operation
):
    from app.services.common import custom_script

    ready = asyncio.Event()
    completed = tmp_path / "completed.txt"
    saved = tmp_path / "saved.txt"
    program = (
        "from pathlib import Path; "
        f"p=Path({str(completed)!r}); "
        "p.write_text(p.read_text()+'done\\n' if p.exists() else 'done\\n')"
    )
    script = tmp_path / "after.py"
    script.write_text(program, encoding="utf-8")
    monkeypatch.setattr(
        custom_script.custom_script_native,
        "build",
        lambda path: [sys.executable, "-I", str(path)],
    )
    real_create = asyncio.create_subprocess_exec

    async def create(program_path, *args, **kwargs):
        # 只替换系统 taskkill 边界，不触碰真实游戏进程。
        if str(program_path).lower() == "taskkill":
            return await real_create(sys.executable, "-I", "-c", program, **kwargs)
        return await real_create(program_path, *args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)

    class Emulator:
        async def close(self, index):
            await ProcessRunner.run_process(sys.executable, "-I", "-c", program)

    class Task(StopTask):
        async def main_task(self):
            if operation == "game":
                config = await activate_config(BetterGIConfig())
                uid = config.UserData.add(BetterGIUserConfig)
                await config.UserData.commit()
                item = await add_script(
                    info=self.task_info, script_id=str(config.uid), user_id=str(uid)
                )
                self.game = BetterGITask(
                    script_info=item, script_config=config, user_config=config.UserData
                )
            ready.set()
            await asyncio.Event().wait()

        async def final_task(self):
            if operation == "emulator":
                owner = SimpleNamespace(
                    emulator_manager=Emulator(),
                    script_config=SimpleNamespace(Emulator=SimpleNamespace(Index="1")),
                )
                assert await close_emulator(owner)
            elif operation == "game":
                await self.game._kill_game_processes(("mas-stop-test.exe",))
            else:
                assert await execute_script_task(script, "脚本后任务")
            saved.write_text("saved", encoding="utf-8")
            await super().final_task()

    task = Task()
    task.start()
    try:
        await asyncio.wait_for(ready.wait(), timeout=3)
        await asyncio.wait_for(task.stop(), timeout=3)
        assert completed.exists(), "停止时清理命令没有执行"
        assert completed.read_text() == "done\n"
        assert saved.read_text() == "saved"
        token = current_process_scope.set(task._stop_scope)
        try:
            with pytest.raises(asyncio.CancelledError):
                await create_subprocess(sys.executable, "-I", "-c", "pass")
        finally:
            current_process_scope.reset(token)
    finally:
        with suppress(asyncio.CancelledError):
            await task.stop()


@pytest.mark.asyncio
async def test_cleanup_confirmation_timeout_reaps_command_and_finishes_local_cleanup():
    ready, cleanup_started, released = asyncio.Event(), asyncio.Event(), asyncio.Event()
    process = None

    class Task(StopTask):
        STOP_CHECK_TIMEOUTS = {"update": 1.0, "finalize": 0.1}

        async def main_task(self):
            ready.set()
            await asyncio.Event().wait()

        async def final_task(self):
            nonlocal process
            try:
                process = await create_subprocess(
                    sys.executable, "-I", "-c", "import time; time.sleep(30)"
                )
                cleanup_started.set()
                await process.wait()
            finally:
                released.set()
                await super().final_task()

    task = Task()
    task.start()
    stopping = None
    try:
        await asyncio.wait_for(ready.wait(), timeout=3)
        stopping = task.request_stop()
        await asyncio.wait_for(cleanup_started.wait(), timeout=3)
        await asyncio.wait_for(task.accomplish.wait(), timeout=3)
        assert released.is_set()
        assert process is not None
        await asyncio.wait_for(process.wait(), timeout=3)
        assert process.returncode is not None
    finally:
        if stopping is not None:
            await asyncio.gather(stopping, return_exceptions=True)
        with suppress(asyncio.CancelledError):
            await task.stop()


@pytest.mark.asyncio
async def test_completed_confirmation_is_not_repeated_in_later_stage():
    scope = TaskProcessScope()
    confirmed = []

    async def first():
        confirmed.append("first")

    async def second():
        confirmed.append("second")

    try:
        scope.add_check("first", first, timeout=1)
        await scope.run_checks()
        scope.add_check("second", second, timeout=1)
        await scope.run_checks()
        assert confirmed == ["first", "second"]
    finally:
        await scope.force_close()
