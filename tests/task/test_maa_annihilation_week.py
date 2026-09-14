import asyncio
from datetime import datetime
from types import SimpleNamespace

from app.task.MAA.AutoProxy import (
    AutoProxyTask,
    _annihilation_weekly_completion_marker,
    _annihilation_weekly_deferral_marker,
    _has_completed_annihilation_week,
)
from app.utils.constants import MAA_TASKS


def test_week_completed_when_annihilation_done_before_proxy() -> None:
    # MAA 未进到副本门口（无理智识别行），完成即周内剿灭在代理前已完成
    assert (
        _has_completed_annihilation_week("开始任务: 剿灭作战\n完成任务: 剿灭作战")
        is True
    )


def test_week_completed_when_progress_reaches_cap() -> None:
    assert (
        _has_completed_annihilation_week(
            "理智: 106/205\n完成任务: 剿灭作战\n剿灭模式 : 1800 / 1800"
        )
        is True
    )
    assert (
        _has_completed_annihilation_week(
            "理智: 5/210\n剿灭模式 : 1850 / 1800\n完成任务: 剿灭作战"
        )
        is True
    )


def test_week_not_completed_without_cap_progress() -> None:
    # 开战了但理智不足没能打满进度
    assert (
        _has_completed_annihilation_week(
            "理智: 5/210\n完成任务: 剿灭作战\n剿灭模式 : 1480 / 1800"
        )
        is False
    )
    # 进到副本门口却因理智不足没有开战
    assert (
        _has_completed_annihilation_week(
            "理智: 24/210\n开始任务: 剿灭作战\n完成任务: 剿灭作战"
        )
        is False
    )
    # 没有完成行不参与判定
    assert _has_completed_annihilation_week("剿灭模式 : 1480 / 1800") is False


def test_completion_marker_carries_weekly_progress() -> None:
    # 完成判定与进度来自同一次解析，供调用方直接展示
    assert _annihilation_weekly_completion_marker(
        "理智: 5/210\n剿灭模式 : 1800 / 1800\n完成任务: 剿灭作战"
    ) == (True, (1800, 1800))
    # 未进到副本门口时没有进度行
    assert _annihilation_weekly_completion_marker("完成任务: 剿灭作战") == (True, None)


def test_deferral_marker_for_insufficient_sanity() -> None:
    # 打到一半理智见底：给出已打到的进度，留待下次调度续打
    assert _annihilation_weekly_deferral_marker(
        "理智: 5/210\n完成任务: 剿灭作战\n剿灭模式 : 1480 / 1800"
    ) == ("剿灭理智不足，本次未打满：1480/1800", (1480, 1800))
    # 进到门口没开战：没有进度行
    assert _annihilation_weekly_deferral_marker(
        "理智: 24/210\n开始任务: 剿灭作战\n完成任务: 剿灭作战"
    ) == ("剿灭理智不足，本次未开战", None)


def test_no_deferral_marker_when_cap_skip_or_unfinished() -> None:
    # 已打满不算理智不足
    assert (
        _annihilation_weekly_deferral_marker(
            "理智: 5/210\n剿灭模式 : 1800 / 1800\n完成任务: 剿灭作战"
        )
        is None
    )
    # 没进过副本（周内已完成）不算理智不足
    assert _annihilation_weekly_deferral_marker("完成任务: 剿灭作战") is None
    # 没有完成行说明本次尝试没有正常收尾，交给失败重试
    assert (
        _annihilation_weekly_deferral_marker("理智: 5/210\n剿灭模式 : 1480 / 1800")
        is None
    )


async def _nothing(*args, **kwargs):
    return None


async def _running() -> bool:
    """MAA 进程仍在运行：日志未出现完成行时不能提前收尾。"""

    return True


def _annihilation_task_for_check_log() -> AutoProxyTask:
    task = object.__new__(AutoProxyTask)
    task.cur_user_log = SimpleNamespace(content=[], status="")
    task.script_info = SimpleNamespace(log="")
    task.task_dict = dict.fromkeys(MAA_TASKS, False)
    task.task_dict["StartUp"] = True
    task.task_dict["Fight"] = True
    task.mode = "Annihilation"
    task.run_book = {"GreenTicketStore": True, "Annihilation": False, "Routine": False}
    task.wait_event = SimpleNamespace(set=lambda: None)
    task.cur_user_config = SimpleNamespace(set=_nothing)
    task.maa_process_manager = SimpleNamespace(is_running=_running)
    task.script_config = SimpleNamespace(
        get=lambda _section, key: 40 if key == "AnnihilationTimeLimit" else None
    )
    task.if_game_hot_update = False
    task.is_log_stalled = lambda *args, **kwargs: False
    task._annihilation_weekly_completion_recorded = False
    task._annihilation_weekly_deferral_marker = None
    task.cur_user_item = SimpleNamespace(name="测试用户")
    return task


def test_insufficient_sanity_ends_the_attempt_without_failure() -> None:
    task = _annihilation_task_for_check_log()

    asyncio.run(
        task.check_log(
            [
                "开始任务: 剿灭作战\n",
                "理智: 5/210\n",
                "剿灭模式 : 1480 / 1800\n",
                "完成任务: 剿灭作战\n",
                "任务已全部完成！\n",
            ],
            datetime.now(),
        )
    )

    # 不得被判成部分任务失败，否则外层会整轮重开 MAA
    assert task.cur_user_log.status == "MAA 剿灭理智不足"
    assert task._annihilation_weekly_deferral_marker is not None


def test_deferral_takes_effect_only_after_the_attempt_ends() -> None:
    task = _annihilation_task_for_check_log()
    task._annihilation_weekly_deferral_marker = ("剿灭理智不足，本次未开战", None)

    asyncio.run(
        task.check_log(["理智: 24/210\n", "开始任务: 剿灭作战\n"], datetime.now())
    )

    # MAA 还在跑，结果未定，不能提前收尾
    assert task.cur_user_log.status == "MAA 正常运行中"


def _annihilation_task_for_main_task(status: str) -> AutoProxyTask:
    task = object.__new__(AutoProxyTask)
    task.task_info = SimpleNamespace(is_queue_task=False)
    script_config = {
        "RunTimesLimit": 1,
        "TaskTransitionMethod": "NoAction",
        "Index": "0",
    }
    task.script_config = SimpleNamespace(
        get=lambda _section, key: script_config.get(key)
    )
    task.cur_user_log = SimpleNamespace(content=[], status=status)
    task.cur_user_item = SimpleNamespace(name="测试用户", status="运行", log_record={})
    task.cur_user_config = SimpleNamespace(
        get=lambda section, key: "Official" if key == "Server" else False,
        set=_nothing,
    )
    task.cur_user_uid = "test-uid"
    task.check_result = "Pass"
    task.run_book = {"GreenTicketStore": True, "Annihilation": False, "Routine": True}
    task.maa_process_manager = SimpleNamespace(kill=_nothing, open_process=_nothing)
    task.maa_log_monitor = SimpleNamespace(stop=_nothing, start_monitor_file=_nothing)
    task.emulator_manager = SimpleNamespace(open=_nothing, close=_nothing)
    task.script_info = SimpleNamespace(log="", script_id="script", name="脚本")
    task.maa_exe_path = "MAA.exe"
    task.maa_root_path = "MAA"
    task.wait_event = SimpleNamespace(
        clear=lambda: None, wait=_nothing, set=lambda: None
    )
    return task


def test_main_task_stops_retrying_annihilation_when_insufficient_sanity(
    monkeypatch,
) -> None:
    task = _annihilation_task_for_main_task("MAA 剿灭理智不足")
    pushed: list[str] = []

    async def _record_push_plyer(*args, **kwargs) -> None:
        pushed.append(args[0])

    monkeypatch.setattr("app.task.MAA.AutoProxy.Notify.push_plyer", _record_push_plyer)
    monkeypatch.setattr(AutoProxyTask, "prepare", _nothing)
    monkeypatch.setattr(AutoProxyTask, "set_maa", _nothing)
    monkeypatch.setattr(AutoProxyTask, "_resolve_log_file_path", lambda self: "gui.log")
    monkeypatch.setattr(AutoProxyTask, "_sync_maa_config_updates", _nothing)
    monkeypatch.setattr("app.task.MAA.AutoProxy.update_maa", _nothing)
    # System.kill_process 会真的去杀 MAA.exe，测试里必须挡住
    monkeypatch.setattr("app.task.MAA.AutoProxy.System.kill_process", _nothing)

    async def _mark_insufficient_sanity(*args, **kwargs) -> None:
        # 日志监看回调在真实运行里已经用 check_log 把状态改成了理智不足
        task.cur_user_log.status = "MAA 剿灭理智不足"

    task.maa_log_monitor.start_monitor_file = _mark_insufficient_sanity

    asyncio.run(task.main_task())

    # 理智不足不重试也不推异常通知，本模式就此收尾
    assert task.run_book["Annihilation"] is True
    assert pushed == []
