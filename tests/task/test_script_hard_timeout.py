import asyncio
from datetime import datetime

import pytest

from app.models.task import LogRecord, ScriptItem, UserItem
from app.task.base import ScriptAutoProxyBase
from tests.config_support import activate_config


class Proxy(ScriptAutoProxyBase):
    run_timeout_seconds = 0.1

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
        assert not first.stopped_manually and (not first.crashes)
        await run(second)
        assert second.finalized and (not second.cancelled)
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
    from app.config.wire import config_contract
    from app.models import config as configs

    async def scenario():
        from maa_adapter.config.script import MaaConfig

        cls = MaaConfig if name == "Maa" else getattr(configs, f"{name}Config")
        config = cls()
        path = tmp_path / f"{name}.yaml"
        await activate_config(config, path)
        assert config.Run.HardTimeLimit == 120
        proxy = Proxy()
        proxy.script_config = config
        assert ScriptAutoProxyBase.run_timeout_seconds.fget(proxy) == 7200
        await config.update(
            type(config).model_validate({"Run": {"HardTimeLimit": 240}}),
            check_visibility=False,
        )
        loaded = cls()
        await activate_config(loaded, path)
        assert loaded.Run.HardTimeLimit == 240
        proxy.script_config = loaded
        assert ScriptAutoProxyBase.run_timeout_seconds.fget(proxy) == 240 * 60
        model = config_contract(cls)
        assert (
            model.model_validate({"Run": {"HardTimeLimit": 240}}).Run.HardTimeLimit
            == 240
        )
        for invalid in (0, 10000):
            from pydantic import ValidationError

            with pytest.raises(ValidationError):
                model.model_validate({"Run": {"HardTimeLimit": invalid}})

    asyncio.run(scenario())


def test_hard_timeout_setting_persists_to_runtime(tmp_path):
    from app.config.wire import config_contract
    from app.models.config import GeneralConfig

    async def scenario():
        config = GeneralConfig()
        path = tmp_path / "general.yaml"
        await activate_config(config, path)
        model = config_contract(GeneralConfig)
        payload = model.model_validate({"Run": {"HardTimeLimit": 240}})
        await config.update(
            GeneralConfig.model_validate(payload.model_dump(exclude_unset=True)),
            check_visibility=False,
        )

        loaded = GeneralConfig()
        await activate_config(loaded, path)
        assert loaded.Run.HardTimeLimit == 240
        proxy = Proxy()
        proxy.script_config = loaded
        assert ScriptAutoProxyBase.run_timeout_seconds.fget(proxy) == 240 * 60

        for invalid in (0, 10000):
            from pydantic import ValidationError

            with pytest.raises(ValidationError):
                model.model_validate({"Run": {"HardTimeLimit": invalid}})

    asyncio.run(scenario())
