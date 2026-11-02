#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

"""奇想盒统计通知的正文组装（纯逻辑，直接断言正文）。

结果块只有 ✅/⏭️/❌ 三态、不带原因，「未完成原因」段放的是上游 ❌/🛑 行原文；
缺该字段时（例如没抓到失败提示）不应出现空标题。
"""

from html import unescape

import app.core.notify.formats.whimbox as notify_mod
from app.models.notification import resolve_content

BASE_MESSAGE = {
    "user_info": "u1",
    "start_time": "t0",
    "end_time": "t1",
    "user_result": "一条龙任务已完成",
    "result_block": "任务结果如下：\n❌朝夕心愿未完成",
    "failure_notes": ['❌ 路线"朝夕心愿_采集"不存在，请先下载该路线'],
}


def _payload_of(message: dict):
    """直接构造正文，不依赖发送器或任务对象。"""

    return notify_mod.build_statistics_payload(title="标题", message=message)


def test_failure_notes_render_to_text_and_html():
    payload = _payload_of(BASE_MESSAGE)
    for body in (payload.text, resolve_content(payload.html)):
        assert "未完成原因（上游提示原文）" in body
        assert '路线"朝夕心愿_采集"' in unescape(body)
    # 结果块仍按原文透传（块头在文本版保留、在 HTML 版由模板标题承载）
    assert "任务结果如下：" in payload.text
    assert "任务结果如下：" not in resolve_content(payload.html)


def test_no_notes_section_without_notes():
    message = {k: v for k, v in BASE_MESSAGE.items() if k != "failure_notes"}
    payload = _payload_of(message)
    assert "未完成原因" not in payload.text
    assert "未完成原因" not in resolve_content(payload.html)
