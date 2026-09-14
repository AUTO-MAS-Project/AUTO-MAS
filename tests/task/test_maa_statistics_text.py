#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""MAA 统计信息报告正文的纯逻辑测试。"""

from app.task.MAA.tools.notify import _statistic_text


def _base_message() -> dict:
    return {
        "start_time": "2026-09-12 13:00:00",
        "end_time": "2026-09-12 14:00:00",
        "sanity": "120/130",
        "sanity_full_at": "未知",
        "maa_result": "代理任务全部完成",
    }


def test_statistic_text_appends_cultivate_achievement() -> None:
    message = _base_message()
    message["cultivate_achievement"] = "小满 已达到精2、银灰 已达到精1"
    text = _statistic_text(message)
    assert (
        "MAA执行结果: 代理任务全部完成\n养成达成: 小满 已达到精2、银灰 已达到精1\n"
        in text
    )


def test_statistic_text_omits_cultivate_line_when_absent() -> None:
    text = _statistic_text(_base_message())
    assert "养成达成" not in text
