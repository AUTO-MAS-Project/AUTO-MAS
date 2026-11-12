#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""鸣潮维护弹窗判据，供登录流程与运行期监视共用。"""

from collections.abc import Iterable


class GameMaintenanceDetected(RuntimeError):
    """登录被维护弹窗阻断，由代理流程转成维护跳过。"""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


def find_game_maintenance_text(texts: Iterable[str]) -> str | None:
    """只消费已有维护锚点，不把普通连接失败或公告判成维护。"""
    # 临时补位：上游尚无维护结果入口（ok-wuthering-waves/discussions/1707），
    # 提供后改为复用。沿用口头确认的「服务器未开放」，尚无维护截图及其它语言样本。
    return next((text for text in texts if "服务器未开放" in text), None)
