import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

import app.task.OkNte.AutoProxy as oknte
from app.task.OkNte.AutoProxy import SIGN_MODE_SPLIT, AutoProxyTask, compile_log_signs
from tests.runtime_support import RuntimeStub as SimpleNamespace


@pytest.mark.parametrize(
    ("body", "successful"),
    [
        (
            "DailyRoutineTask:开始任务: 异象追猎\nAnomalyHunter:info_set 当前体力 266\nDailyRoutineTask:任务失败: 异象追猎\n",
            False,
        ),
        (
            "DailyRoutineTask:开始任务: 异象追猎\nAnomalyHunter:info_set 当前体力 20\nAnomalyHunter:体力不足，退出异象追猎任务\nDailyRoutineTask:任务失败: 异象追猎\n",
            True,
        ),
        (
            "DailyRoutineTask:开始任务: 异象追猎\nAnomalyHunter:info_set 当前体力 20\nAnomalyHunter:体力不足，退出异象追猎任务\nDailyRoutineTask:任务失败: 异象追猎\nDailyRoutineTask:开始任务: 喷泉签到\nDailyRoutineTask:任务失败: 喷泉签到\n",
            False,
        ),
        (
            "DailyRoutineTask:开始任务: 异象追猎\nAnomalyHunter:info_set 当前体力 0\nAnomalyHunter:体力不足，退出异象追猎任务\nDailyRoutineTask:任务失败: 异象追猎\n",
            False,
        ),
    ],
)
def test_daily_result_controls_retry(body, successful):
    async def scenario():
        proxy = AutoProxyTask.__new__(AutoProxyTask)
        proxy.cur_user_log = SimpleNamespace(content=[], status="")
        proxy.cur_user_item = SimpleNamespace(status="运行")
        proxy.script_info = SimpleNamespace(log="", log_first_line=0)
        proxy.wait_event = asyncio.Event()
        proxy.error_log = compile_log_signs("", SIGN_MODE_SPLIT)
        proxy.success_log = compile_log_signs(
            "Successfully Executed Task", SIGN_MODE_SPLIT
        )
        proxy.task_index = 2
        proxy.daily_activity_required = True
        log = (
            body
            + "DailyRoutineTask:info_set success ['日常领取']\nTaskExecutor:Successfully Executed Task\n"
        )
        await proxy.check_log(log.splitlines(keepends=True), datetime.now())
        assert (proxy.cur_user_log.status == "Success!") is successful
        assert proxy.cur_user_item.status == ("完成" if successful else "异常")
        assert proxy.wait_event.is_set()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("run_limit", "failure", "starts"), [(1, True, 1), (2, True, 2), (2, False, 1)]
)
def test_attempt_limit_controls_process_restarts(
    monkeypatch, run_limit, failure, starts
):
    """运行总次数包含首次执行；保留真实判态、等待与重试循环。"""

    async def scenario():
        proxy = AutoProxyTask.__new__(AutoProxyTask)
        user = SimpleNamespace(
            name="测试账号", status="运行", maintenance_skipped=False, log_record={}
        )

        async def add_log(when, record):
            user.log_record[when] = record
            return record

        user.add_log_record = add_log
        proxy.user_state = lambda _: user
        proxy.cur_user_item = user
        proxy.cur_user_uid = "test"
        proxy.script_info = SimpleNamespace(log="", log_first_line=0)
        proxy.wait_event = asyncio.Event()
        proxy.run_book = False
        proxy._maintenance_reason = None
        proxy.task_index = 2
        proxy.daily_activity_required = True
        proxy.script_exe_path = "ok-nte.exe"
        proxy.oknte_args = ["-t", "2", "-e"]
        proxy.exit_on_finish = True
        proxy.script_config = SimpleNamespace(
            Run=SimpleNamespace(RunTimesLimit=run_limit),
            Game=SimpleNamespace(
                Enabled=False, LaunchBeforeTask=False, AccountSwitch=False
            ),
            Script=SimpleNamespace(UpdateConfigMode="Never"),
        )
        proxy.error_log = compile_log_signs("", SIGN_MODE_SPLIT)
        proxy.success_log = compile_log_signs(
            "Successfully Executed Task", SIGN_MODE_SPLIT
        )
        # 隔离配置准备、进程、通知和维护检测；不替换判态或循环。
        for name in (
            "prepare",
            "_reset_daily_proxy_count",
            "run_user_scripts_before",
            "_log_game_config_summary",
            "set_oknte",
            "_push_dispatch_log",
            "kill_managed_process",
            "_kill_oknte_process",
        ):
            setattr(proxy, name, AsyncMock())
        proxy.skip_on_game_maintenance = AsyncMock(return_value=False)
        proxy.clear_maintenance_hit = AsyncMock()
        proxy._mas_should_close_game_on_retry = lambda: False
        proxy._resolve_log_file_path = lambda: None
        proxy.oknte_process_manager = SimpleNamespace(open_oknte=AsyncMock())

        async def replay(*args):
            body = (
                "2026-11-07 21:06:42,285 INFO TaskExecutor DailyRoutineTask:开始任务: 异象追猎\n"
                "2026-11-07 21:07:31,876 INFO TaskExecutor DailyRoutineTask:任务失败: 异象追猎\n"
                if failure
                else ""
            )
            # 取本轮实机输出的前缀与退出语；保留领取成功以暴露此前的误判。
            body += "DailyRoutineTask:info_set success ['日常领取']\nTaskExecutor:Successfully Executed Task, Exiting Game and App!\n"
            asyncio.get_running_loop().call_soon(
                lambda: asyncio.create_task(
                    proxy.check_log(body.splitlines(keepends=True), datetime.now())
                )
            )

        proxy.log_monitor = SimpleNamespace(start_monitor_file=replay, stop=AsyncMock())
        proxy.watch_game_maintenance = AsyncMock()
        monkeypatch.setattr(oknte.Notify, "send_notice", AsyncMock())
        monkeypatch.setattr(oknte.asyncio, "sleep", AsyncMock())
        await proxy.main_task()
        assert proxy.oknte_process_manager.open_oknte.await_count == starts
        assert proxy.run_book is (not failure)

    asyncio.run(scenario())
