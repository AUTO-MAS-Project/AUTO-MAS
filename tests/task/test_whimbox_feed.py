#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

"""奇想盒日志流（LoguruFileFeed）行处理回归测试（纯函数，无 I/O）。

覆盖 CRLF 归一：上游 loguru 在 Windows 下落 CRLF，而下游（历史日志文本模式写盘、
通知正文）会再翻译一次换行，不归一会得到 ``\\r\\r\\n`` —— 报告里每行之间多一个空行。
"""

import asyncio
from datetime import datetime

from app.task.Whimbox.tools.feed import LoguruFileFeed


def _feed() -> tuple[LoguruFileFeed, list]:
    events: list = []

    async def on_event(event) -> None:
        events.append(event)

    return LoguruFileFeed(on_event, lambda: None), events


def test_crlf_lines_are_normalized_in_place():
    feed, events = _feed()
    lines = [
        "2026-09-24 22:15:26.801 | INFO     | main:run_one_dragon:80 - "
        "一条龙任务完成: 任务结果如下：\r\n",
        "❌美鸭梨挖掘未完成\r\n",
    ]

    asyncio.run(feed._on_log(lines, datetime.now()))

    assert "\r" not in feed.log_text
    assert feed.log_text.endswith("❌美鸭梨挖掘未完成\n")
    # 就地改写：监控器持有同一个 list 并持续追加，换引用会让后续新行读不到
    assert lines[0].endswith("任务结果如下：\n")
    assert [e.text for e in events] == lines

    # 后续回调追加的新行照样被采集
    lines.append("✅奇迹之旅已完成\r\n")
    asyncio.run(feed._on_log(lines, datetime.now()))
    assert feed.log_text.endswith("✅奇迹之旅已完成\n")
    assert events[-1].text == "✅奇迹之旅已完成\n"
