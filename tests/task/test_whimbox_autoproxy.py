#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

"""奇想盒自动代理的纯逻辑片段（当前：重试策略）。

``Run.RunTimesLimit`` 的重试只救「没有上游结论」的形态（进程提前退出 / 卡死）；
上游自己判负时只有**原因与上一轮不同**（情形在变）才继续重试，连着给出同一个结论
就收口——否则重试等于把整条一条龙再跑一遍（含重新启动游戏），而原因不会自己变。
"""

import pytest

from app.task.Whimbox.AutoProxy import _should_retry


@pytest.mark.parametrize(
    "status,same_reason,expected",
    [
        ("exited_early", False, True),
        ("stalled", False, True),
        (None, False, True),
        ("failed", False, True),
        ("failed", True, False),
        ("fatal", False, False),
        ("success", False, False),
    ],
)
def test_retry_follows_upstream_verdict(status, same_reason, expected):
    assert _should_retry(status, same_reason_as_last=same_reason) is expected
