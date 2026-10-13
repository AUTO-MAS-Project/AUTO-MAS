#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

"""奇想盒统计通知的正文组装（纯逻辑，打桩 dispatch 后断言正文）。

结果块只有 ✅/⏭️/❌ 三态、不带原因，「未完成原因」段放的是上游 ❌/🛑 行原文；
缺该字段时（例如没抓到失败提示）不应出现空标题。
"""

import asyncio
from unittest.mock import AsyncMock, patch

from app.task.Whimbox.tools import notify as notify_mod

BASE_MESSAGE = {
    "user_info": "u1",
    "start_time": "t0",
    "end_time": "t1",
    "user_result": "一条龙任务已完成",
    "result_block": "任务结果如下：\n❌朝夕心愿未完成",
    "failure_notes": ['❌ 路线"朝夕心愿_采集"不存在，请先下载该路线'],
}


def _payload_of(message: dict):
    """跑一遍 push_notification，返回交给 dispatch 的 NotifyPayload。"""

    with (
        patch.object(
            notify_mod, "dispatch", new=AsyncMock(return_value=None)
        ) as dispatch,
        patch.object(notify_mod, "statistic_targets", return_value=["T"]),
    ):
        asyncio.run(
            notify_mod.push_notification(
                "统计信息", "标题", message, user_config=object()
            )
        )
        return dispatch.await_args.args[0]


def test_failure_notes_render_to_text_and_html():
    payload = _payload_of(BASE_MESSAGE)
    for body in (payload.text, payload.html):
        assert "未完成原因（上游提示原文）" in body
        assert '路线"朝夕心愿_采集"' in body
    # 结果块仍按原文透传（块头在文本版保留、在 HTML 版由模板标题承载）
    assert "任务结果如下：" in payload.text
    assert "任务结果如下：" not in payload.html


def test_no_notes_section_without_notes():
    message = {k: v for k, v in BASE_MESSAGE.items() if k != "failure_notes"}
    payload = _payload_of(message)
    assert "未完成原因" not in payload.text
    assert "未完成原因" not in payload.html
