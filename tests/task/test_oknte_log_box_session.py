"""NTE 托管采集与原有同步交付的输出对照，仅使用本地日志样例。"""

import asyncio
from types import SimpleNamespace

import pytest

from app.task.general.manager import GeneralManager
from app.task.OkNte.AutoProxy import AutoProxyTask
from app.task.OkNte.push_log import OKNTE_PUSH_RULES, oknte_resolve
from app.utils import log_box


def build_user_result_text(users, has_uncompleted):
    manager = SimpleNamespace(script_info=SimpleNamespace(user_list=users))
    return GeneralManager._render_user_results(manager, has_uncompleted=has_uncompleted)


@pytest.mark.parametrize("mode", ["关闭", "逐条", "汇总"])
@pytest.mark.parametrize(
    "lines",
    [
        ["任务完成: 邮件领取", "任务完成: 日常领取"],
        ["任务失败: 日常领取", "无法找到活跃度奖励领取框"],
        ["任务失败: 异象界域", "任务完成: 异象界域"],
        ["info_set skipped ['邮件领取', '日常领取']"],
        ["当前体力 240", "双倍次数: 1, 单倍次数: 2", "任务完成: 异象界域"],
        ["当前体力 240", "共计消耗体力: 120", "任务完成: 异象追猎"],
        [],
    ],
)
def test_nte_reports_match_existing_collect(tmp_path, monkeypatch, mode, lines):
    path = tmp_path / "ok-script.log"
    path.write_text("任务完成: 运行前旧日志\n", encoding="utf-8")
    previous, current = [
        SimpleNamespace(
            name="NTE 用户",
            result="执行完成",
            status="完成",
            push_log=[],
            push_log_mode=mode,
        )
        for _ in range(2)
    ]
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.cur_user_item = current
    proxy._prepare_log_details(
        path, mode=mode, enabled=mode != "关闭", rotated_name=None
    )
    path.write_text(
        "任务完成: 运行前旧日志\n" + "\n".join(lines) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr("app.task.OkNte.AutoProxy.time.time", lambda: 1793228520.0)
    if mode != "关闭":
        pipeline = log_box.LogPipeline()
        for rule in OKNTE_PUSH_RULES:
            pipeline.add_rule(*rule)
        pipeline.postprocessors.append(oknte_resolve)
        for line in lines:
            pipeline.feed(line, timestamp=1793228520.0)
        previous.push_log.extend(
            (e.log_type, e.text, e.timestamp) for e in pipeline.finish()
        )

    async def scenario():
        await asyncio.gather(proxy._close_log_details(), proxy._close_log_details())
        await proxy._close_log_details()

    asyncio.run(scenario())
    assert current.push_log == previous.push_log
    for has_uncompleted in (False, True):
        assert build_user_result_text([current], has_uncompleted) == (
            build_user_result_text([previous], has_uncompleted)
        )
