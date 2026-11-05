"""BetterGI 的任务失败结果优先于执行层的正常返回标记。"""

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.task.BetterGI.tools.one_dragon_report import parse_execution_layer_report


def log_entry(time, level, logger, message):
    return f"[{time}] [{level}] [Primary:S1:P1:T1] {logger}\n{message}\n"


@pytest.mark.parametrize(
    "task", ["自动秘境", "自动首领讨伐", "自动幽境危战", "自动地脉花"]
)
def test_dispatcher_failure_overrides_done_and_keeps_next_step(task):
    reason = "独立任务失败：配置与本次任务不匹配（invalid_parameter）"
    log = "".join(
        [
            log_entry("09:00:00.000", "INF", "Script.Log", f"MAS_STEP_BEGIN: a {task}"),
            log_entry(
                "09:00:01.000", "ERR", "Core.Script.Dependence.Dispatcher", reason
            ),
            log_entry("09:00:02.000", "INF", "Script.Log", f"MAS_STEP_DONE: a {task}"),
            log_entry(
                "09:00:03.000", "INF", "Script.Log", "MAS_STEP_BEGIN: b 自动秘境"
            ),
            log_entry("09:00:04.000", "INF", "Script.Log", "MAS_STEP_DONE: b 自动秘境"),
        ]
    )

    steps = parse_execution_layer_report(log)

    assert [step["ok"] for step in steps] == [False, True]
    assert steps[0]["issue_text"] == reason
    assert steps[0]["issue_count"] == 1
    assert steps[1]["issue_count"] == 0


@pytest.mark.parametrize(
    ("logger", "message"),
    [
        ("GameTask.TaskControl", "操作暂时失败，稍后重试"),
        ("Core.Script.Dependence.Dispatcher", "操作暂时失败，稍后重试"),
        ("Script.Log", "独立任务失败：用户脚本打印的普通消息"),
    ],
)
def test_recoverable_error_is_not_a_terminal_failure(logger, message):
    log = "".join(
        [
            log_entry("09:00:00", "INF", "Script.Log", "MAS_STEP_BEGIN: a 自动秘境"),
            log_entry("09:00:01", "ERR", logger, message),
            log_entry("09:00:02", "INF", "Script.Log", "MAS_STEP_DONE: a 自动秘境"),
        ]
    )

    steps = parse_execution_layer_report(log)

    assert steps[0]["ok"] is True
    assert steps[0]["issue_count"] == 1


def test_terminal_failure_takes_priority_over_recoverable_error():
    log = "".join(
        [
            log_entry("09:00:00", "INF", "Script.Log", "MAS_STEP_BEGIN: a 自动秘境"),
            log_entry("09:00:01", "ERR", "GameTask.TaskControl", "正在重试"),
            log_entry(
                "09:00:02",
                "ERR",
                "Core.Script.Dependence.Dispatcher",
                "独立任务失败: 无法执行",
            ),
            log_entry("09:00:03", "INF", "Script.Log", "MAS_STEP_DONE: a 自动秘境"),
        ]
    )

    steps = parse_execution_layer_report(log)

    assert steps[0]["ok"] is False
    assert steps[0]["issue_count"] == 2
    assert steps[0]["issue_text"] == "独立任务失败: 无法执行"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("execution_finished", "native_enabled"),
    [(True, False), (False, False), (False, True)],
)
async def test_execution_failure_logs_name_builtin_and_custom_tasks(
    monkeypatch, tmp_path, execution_finished, native_enabled
):
    from app.models.task import ScriptItem, UserItem
    from app.task.BetterGI import AutoProxy as module

    # 进程与文件监控边界重放 BGI 输出，保留真实解析、计数及调度台日志交付。
    log = "".join(
        [
            log_entry("09:00:00", "INF", "Script.Log", "MAS_STEP_BEGIN: a 自动地脉花"),
            log_entry(
                "09:00:01", "INF", "Script.Log", "MAS_STEP_FAIL: a 自动地脉花 执行失败"
            ),
            log_entry("09:00:02", "INF", "Script.Log", "MAS_STEP_BEGIN: b 自动秘境"),
            log_entry("09:00:03", "INF", "Script.Log", "MAS_STEP_DONE: b 自动秘境"),
            log_entry(
                "09:00:04", "INF", "ScriptService", '→ 开始执行JS脚本: "自动购买商品"'
            ),
            log_entry("09:00:05", "ERR", "ScriptService", "购买失败"),
            log_entry(
                "09:00:06", "INF", "ScriptService", '→ 脚本执行结束: "自动购买商品"'
            ),
            log_entry(
                "09:00:07",
                "INF",
                "ScriptService",
                '配置组 "执行层段1" 执行结束'
                if execution_finished
                else "执行配置组任务时失败",
            ),
        ]
    )

    class Monitor:
        def __init__(self, time_range, time_format, on_log):
            self.on_log = on_log

        async def start_monitor_file(self, path, start):
            await self.on_log(log.splitlines(keepends=True), datetime.now())

        async def stop(self):
            pass

    monkeypatch.setattr(module, "LogMonitor", Monitor)
    script = ScriptItem("script", "BetterGI", "运行")
    proxy = SimpleNamespace(
        exec_group_names=["执行层段1"],
        cur_user_item=UserItem("user", "测试用户", "运行"),
        script_info=script,
        script_exe_path=Path("BetterGI.exe"),
        script_target_process_info=None,
        script_config=SimpleNamespace(
            Run=SimpleNamespace(UseAdmin=False, RunTimesLimit=1)
        ),
        bettergi_process_manager=SimpleNamespace(open_process=AsyncMock()),
        kill_managed_process=AsyncMock(return_value=True),
        _resolve_log_file_path=lambda: Path("better-genshin-impact.log"),
        log_time_range=(1, 13),
        log_time_format="%H:%M:%S.%f",
    )
    proxy._push_dispatch_log = module.AutoProxyTask._push_dispatch_log.__get__(proxy)
    if not execution_finished:
        # 从 main_task 走完后续原生阶段；只隔离游戏、更新、配置写盘及外部完成等待。
        proxy.prepare = AsyncMock()
        proxy.run_user_scripts_before = AsyncMock()
        proxy._switch_account = AsyncMock(return_value=True)
        proxy._backup_one_dragon_config = Mock()
        proxy._write_one_dragon_config = Mock()
        proxy.cur_user_uid = uuid4()
        proxy.cur_user_config = module.BetterGIUserConfig()
        proxy.script_root_path = tmp_path
        proxy.launch_config_name = "daily"
        proxy.bettergi_args = ["startOneDragon", "daily"]
        proxy.wait_event = asyncio.Event()
        proxy.run_book = False
        proxy.log_monitor = SimpleNamespace(
            start_monitor_file=AsyncMock(), stop=AsyncMock()
        )
        proxy._run_execution_layer = module.AutoProxyTask._run_execution_layer.__get__(
            proxy
        )
        proxy._native_one_dragon_has_tasks = (
            module.AutoProxyTask._native_one_dragon_has_tasks.__get__(proxy)
        )
        module.one_dragon.write_one_dragon(
            tmp_path, "daily", {"TaskEnabledList": {"领取邮件": native_enabled}}
        )

        async def native_finished():
            proxy.cur_user_log.status = "Success!"

        proxy._wait_for_bgi_result = AsyncMock(side_effect=native_finished)
        monkeypatch.setattr(module, "ensure_game_updated", AsyncMock(return_value=True))
        monkeypatch.setattr(module, "archive_mas_runtime_backup", Mock())
    warnings = []
    sink = module.logger.add(
        lambda message: warnings.append(message.record["message"]), level="WARNING"
    )
    try:
        if execution_finished:
            assert await module.AutoProxyTask._run_execution_layer(proxy) is True
        else:
            await module.AutoProxyTask.main_task(proxy)
            assert proxy.run_book is native_enabled
    finally:
        module.logger.remove(sink)

    assert proxy.partial_failed_steps == 2
    custom_warning = next(line for line in warnings if "个自定义项失败" in line)
    assert "自动购买商品" in custom_warning
    if execution_finished:
        summary = next(line for line in warnings if "个步骤失败" in line)
        assert "自动地脉花" in summary
        assert "自动购买商品" in summary
        assert "自动秘境" not in summary
    else:
        summary = next(line for line in warnings if "继续一条龙日常" in line)
        assert "自动地脉花" in summary
        assert "自动购买商品" in summary
        assert "自动秘境" not in summary
    dispatch_summary = script.log
    assert "自动地脉花" in dispatch_summary
    assert "自动购买商品" in dispatch_summary
    assert "自动秘境" not in dispatch_summary
