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

from app.task.Whimbox.AutoProxy import _should_retry


def test_retry_without_upstream_verdict():
    # 没有上游结论的形态：重试（重试机制的原本用途）
    assert _should_retry("exited_early")
    assert _should_retry("stalled")
    assert _should_retry(None)  # 异常路径未留判定


def test_upstream_verdict_retries_only_when_reason_changes():
    # 上游判负：原因与上一轮不同 → 情形在变，继续重试
    assert _should_retry("failed", same_reason_as_last=False)
    # 同一原因连续出现 → 收口，不再把整条一条龙重跑一遍
    assert not _should_retry("failed", same_reason_as_last=True)


def test_no_retry_for_environment_fatal_and_success():
    assert not _should_retry("fatal")  # 缺管理员权限不会因重试而出现
    assert not _should_retry("success")  # 调用方在此之前已收口
