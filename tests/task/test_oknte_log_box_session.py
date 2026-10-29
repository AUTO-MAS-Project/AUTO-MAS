"""NTE 托管采集与原有同步交付的输出对照，仅使用本地日志样例。"""

import asyncio
from types import SimpleNamespace

import pytest

from app.log_box import LogCollect, log_box
from app.log_box.report import build_user_result_text
from app.task.OkNte.push_log import OKNTE_LOG_SPEC, OKNTE_PUSH_RULES, oknte_resolve


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
    legacy = None
    if mode != "关闭":
        legacy = LogCollect(path, sink=lambda *entry: previous.push_log.append(entry))
        legacy.open()
        for rule in OKNTE_PUSH_RULES:
            legacy.collect(*rule)
    managed = log_box.get_user_session(
        OKNTE_LOG_SPEC, user=current, mode=mode, paths=path
    )
    with path.open("a", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")
    monkeypatch.setattr("app.log_box.pipeline.time.time", lambda: 1793228520.0)
    if legacy is not None:
        legacy.close(oknte_resolve)
    asyncio.run(managed.close())
    assert current.push_log == previous.push_log
    for has_uncompleted in (False, True):
        assert build_user_result_text([current], has_uncompleted) == (
            build_user_result_text([previous], has_uncompleted)
        )
