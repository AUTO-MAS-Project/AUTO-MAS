import uuid
from types import SimpleNamespace

import pytest

from app.core import Config
from app.models.config import HSRConfig, HSRUserConfig
from app.task.HSR.AutoProxy import HSRAutoProxyTask
from app.task.HSR.manager import HSRManager
from app.task.HSR.tools.run_model import HSRRunItem
from tests.config_support import activate_config
from tests.support.scheduler import create_runtime_tree


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rewards_outcomes", "weekly_outcomes", "expected_status", "expected_proxy_times"),
    [
        (("bad_config",), ("success",), "异常", 0),
        (("bad_config",), ("failed", "success"), "异常", 0),
        (("failed", "success"), ("success",), "完成", 1),
        (("success",), ("failed", "failed"), "异常", 1),
    ],
)
async def test_hsr_daily_count_and_account_status_after_retries(
    monkeypatch,
    isolated_app_paths,
    rewards_outcomes,
    weekly_outcomes,
    expected_status,
    expected_proxy_times,
):
    script_config = await activate_config(
        HSRConfig(Game={"Enabled": False}, Run={"RunTimesLimit": 2})
    )
    user_id = script_config.UserData.add(
        HSRUserConfig, payload={"Info": {"Name": "Test user", "RemainedDay": -1}}
    )
    await script_config.UserData.commit()
    user_config = script_config.UserData[user_id]
    original_date = user_config.Data.LastProxyDate
    script_id = uuid.uuid4()
    monkeypatch.setattr(Config, "ScriptConfig", {script_id: script_config})
    _, script, user = await create_runtime_tree(
        script_id=str(script_id), user_id=str(user_id)
    )
    manager = HSRManager(script)
    task = HSRAutoProxyTask(
        script_info=script,
        script_config=script_config,
        user_config=script_config.UserData,
        user_item=user,
        runtime=manager._runtime,
    )

    def scripted_module(*, phase, key, outcomes):
        results = iter(outcomes)

        async def run():
            outcome = next(results)
            if outcome == "bad_config":
                raise FileNotFoundError("三月七 config.yaml 不存在")
            return SimpleNamespace(
                success=outcome == "success", error="外部脚本执行失败"
            )

        return HSRRunItem(
            user_name=user.name,
            user_id=str(user_id),
            phase=phase,
            module_key=key,
            module_name=key,
            script="M7A",
            description="三月七执行结果",
            run=run,
        )

    queue = [
        scripted_module(phase="daily", key="Daily", outcomes=("success",)),
        scripted_module(phase="daily", key="ReceiveRewards", outcomes=rewards_outcomes),
        scripted_module(
            phase="weekly", key="DivergentUniverse", outcomes=weekly_outcomes
        ),
    ]
    monkeypatch.setattr(task, "_build_user_queue", lambda **_kwargs: queue)

    failure = None
    try:
        if expected_status == "异常":
            with pytest.raises(RuntimeError) as failure:
                await task.main_task()
        else:
            await task.main_task()
    finally:
        await task.callbacks.drain()

    await manager._apply_completion_writebacks()
    assert user.status == expected_status
    assert user_config.Data.ProxyTimes == expected_proxy_times
    assert (user_config.Data.LastProxyDate != original_date) is bool(
        expected_proxy_times
    )
    if failure is not None and rewards_outcomes == ("bad_config",):
        assert "已尝试 1 次，不可补跑" in str(failure.value)
        assert "三月七 config.yaml 不存在" in str(failure.value)
