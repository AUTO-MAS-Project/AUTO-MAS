import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
    (
        "rewards_outcomes",
        "weekly_outcomes",
        "game_stop",
        "expected_status",
        "expected_proxy_times",
    ),
    [
        (("bad_config",), ("success",), None, "异常", 0),
        (("bad_config",), ("failed", "success"), None, "异常", 0),
        (("failed", "success"), ("success",), None, "完成", 1),
        (("success",), ("failed", "failed"), None, "异常", 1),
        pytest.param(
            ("failed", "success"), (), "delayed", "完成", 1, id="delayed-game-stop"
        ),
        pytest.param(("failed",), (), "blocked", "异常", 0, id="blocked-game-stop"),
    ],
)
async def test_hsr_daily_count_and_account_status_after_retries(
    monkeypatch,
    isolated_app_paths,
    tmp_path,
    rewards_outcomes,
    weekly_outcomes,
    game_stop,
    expected_status,
    expected_proxy_times,
):
    script_config = await activate_config(
        HSRConfig(Game={"Enabled": game_stop is not None}, Run={"RunTimesLimit": 2})
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
    if game_stop is not None:
        game_path = tmp_path / "StarRail.exe"
        game_path.touch()
        old_process_running = True
        window_visible = True

        async def stop_game():
            nonlocal old_process_running, window_visible
            if window_visible or game_stop == "blocked":
                # 退出期间窗口先消失，绑定适配器仍能找到旧进程。
                window_visible = False
                raise RuntimeError("无法确认游戏进程已经关闭")
            old_process_running = False

        async def start_game(*_args, **_kwargs):
            nonlocal window_visible
            if old_process_running:
                raise RuntimeError("无法同时管理多个进程")
            window_visible = True

        start_process = AsyncMock(side_effect=start_game)
        manager._runtime.game_process_manager = SimpleNamespace(
            kill=stop_game, clear=AsyncMock(), open_process=start_process
        )
        for module in ("AutoProxy", "tools.account_switch"):
            monkeypatch.setattr(
                f"app.task.HSR.{module}.has_process_window",
                AsyncMock(side_effect=lambda *_args: window_visible),
            )
        monkeypatch.setattr(
            "app.task.HSR.tools.account_switch.client_executable_path",
            lambda _config: game_path,
        )
        monkeypatch.setattr("app.task.HSR.AutoProxy.HSR_GAME_READY_DELAY_SECONDS", 0)

    task = HSRAutoProxyTask(
        script_info=script,
        script_config=script_config,
        user_config=script_config.UserData,
        user_item=user,
        runtime=manager._runtime,
        prepare_m7a_config=AsyncMock(),
    )
    if game_stop is not None:
        monkeypatch.setattr(
            task._account_switcher, "_wait_after_game_process_detected", AsyncMock()
        )
        monkeypatch.setattr(
            task._account_switcher, "_wait_for_game_process_after_launch", AsyncMock()
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
    ]
    if weekly_outcomes:
        queue.append(
            scripted_module(
                phase="weekly", key="DivergentUniverse", outcomes=weekly_outcomes
            )
        )
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
    if game_stop == "delayed":
        start_process.assert_awaited_once_with(game_path, cwd=game_path.parent)
    elif game_stop == "blocked":
        assert failure is not None
        assert "无法确认游戏进程已经关闭" in str(failure.value)
        start_process.assert_not_awaited()
