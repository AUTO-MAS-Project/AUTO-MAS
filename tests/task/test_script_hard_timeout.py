import asyncio
import ast
from datetime import datetime
from pathlib import Path

import pytest

from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.task.base import ScriptAutoProxyBase


class Proxy(ScriptAutoProxyBase):
    run_timeout_seconds = 0.025

    def __init__(self, behavior="hang", user=None):
        super().__init__()
        self.behavior = behavior
        self.cur_user_item = user or UserItem("test", "测试账号", "运行")
        self.cur_user_item.log_record[datetime.now()] = LogRecord(status="运行中")
        self.script_info = ScriptItem("script", "测试脚本", "运行")
        self.crashes = []
        self.finalized = False
        self.cancelled = False
        self.ticks = 0

    async def main_task(self):
        if self.behavior == "error":
            raise TimeoutError("内部超时")
        if self.behavior == "success":
            return
        try:
            while True:
                self.ticks += 1
                await asyncio.sleep(0.002)
        finally:
            self.cancelled = True

    async def final_task(self):
        await asyncio.sleep(0.01)
        self.saved_status = self.cur_user_item.result
        self.finalized = True

    async def on_crash(self, error):
        self.crashes.append(error)


async def run(proxy):
    async with asyncio.TaskGroup() as group:
        await proxy._execute_task(group)


def test_progress_does_not_extend_deadline_and_cleanup_precedes_next_account():
    async def scenario():
        first = Proxy()
        second = Proxy("success")
        await run(first)
        assert first.finalized and first.cancelled and first.accomplish.is_set()
        assert first.ticks > 1
        assert first.cur_user_item.status == "异常"
        assert "已终止" in first.saved_status
        assert not first.stopped_manually and not first.crashes
        await run(second)
        assert second.finalized and not second.cancelled
        assert "已终止" not in second.saved_status

    asyncio.run(scenario())


def test_internal_timeout_is_a_crash():
    async def scenario():
        proxy = Proxy("error")
        await run(proxy)
        assert len(proxy.crashes) == 1
        assert str(proxy.crashes[0]) == "内部超时"
        assert "已终止" not in proxy.saved_status

    asyncio.run(scenario())


def test_manual_cancel_is_not_reported_as_timeout():
    async def scenario():
        proxy = Proxy()
        proxy.run_timeout_seconds = 10
        task = asyncio.create_task(run(proxy))
        await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert proxy.finalized and proxy.stopped_manually
        assert "已终止" not in proxy.saved_status

    asyncio.run(scenario())


def test_timeout_before_log_creation_still_records_reason():
    async def scenario():
        proxy = Proxy()
        proxy.cur_user_item.log_record.clear()
        await run(proxy)
        assert "已终止" in proxy.saved_status

    asyncio.run(scenario())


def test_adapter_coverage_and_exemptions():
    root = Path("app/task")
    covered = {
        "MAA",
        "MaaEnd",
        "SRC",
        "Okww",
        "OkNte",
        "ZzzOd",
        "BAAH",
        "BetterGI",
        "Whimbox",
        "general",
    }
    actual = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(
                isinstance(base, ast.Name) and base.id == "ScriptAutoProxyBase"
                for base in node.bases
            ):
                actual.add(path.relative_to(root).parts[0])
    assert actual == covered
    from app.models.config import MaaConfig

    proxy = Proxy()
    proxy.script_config = MaaConfig()
    assert ScriptAutoProxyBase.run_timeout_seconds.fget(proxy) == 7200
    assert TaskExecuteBase._run_main_task is not ScriptAutoProxyBase._run_main_task


def test_repeated_cancel_waits_for_finalizer():
    async def scenario():
        proxy = Proxy()
        proxy.run_timeout_seconds = 10
        started = asyncio.Event()
        release = asyncio.Event()

        async def finalize():
            started.set()
            await release.wait()
            proxy.finalized = True

        proxy.final_task = finalize
        task = asyncio.create_task(run(proxy))
        await asyncio.sleep(0.005)
        task.cancel()
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert proxy.finalized and proxy.accomplish.is_set()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "name",
    [
        "Maa",
        "MaaEnd",
        "Src",
        "General",
        "Okww",
        "OkNte",
        "BetterGI",
        "ZzzOd",
        "BAAH",
        "Whimbox",
    ],
)
def test_hard_timeout_config_persistence_and_runtime(name, tmp_path):
    from app.models import config as configs
    from app.models import schema

    async def scenario():
        cls = getattr(configs, f"{name}Config")
        config = cls()
        path = tmp_path / f"{name}.json"
        await config.connect(path)
        assert config.get("Run", "HardTimeLimit") == 120
        await config.set("Run", "HardTimeLimit", 240)
        loaded = cls()
        await loaded.connect(path)
        assert loaded.get("Run", "HardTimeLimit") == 240
        proxy = Proxy()
        proxy.script_config = loaded
        assert ScriptAutoProxyBase.run_timeout_seconds.fget(proxy) == 240 * 60
        model = getattr(schema, f"{name}Config")
        assert (
            model.model_validate({"Run": {"HardTimeLimit": 240}}).Run.HardTimeLimit
            == 240
        )
        for invalid in (0, 10000):
            from pydantic import ValidationError

            with pytest.raises(ValidationError):
                model.model_validate({"Run": {"HardTimeLimit": invalid}})

    asyncio.run(scenario())


def test_exempt_configs_do_not_expose_hard_timeout():
    from app.models import config as configs
    from app.models import schema

    for name in ("MaaFW", "M9A", "MSS", "HSR"):
        config = getattr(configs, f"{name}Config")()
        assert not hasattr(config, "Run_HardTimeLimit")
        model = getattr(schema, f"{name}Config")
        run_model = model.model_fields["Run"].annotation.__args__[0]
        assert "HardTimeLimit" not in run_model.model_fields
