#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MAA 启动前的引导跳过，仅修改运行副本，不负责迁移与写盘。"""

# shortcut: 上游改动引导字段或整型比较后可能重新弹引导；提供跳过入口后改为调用该入口。
MAA_GUIDE_SKIP_VALUES = {"GuideStep": 2**31 - 1, "GuideTutorialVersion": 2**31 - 1}


def ensure_maa_guide_skipped(gui: dict) -> None:
    """按需将根级 Gui 的引导进度与教程版本标记为已完成。"""
    if all(
        type(gui.get(key)) is int and gui[key] == value
        for key, value in MAA_GUIDE_SKIP_VALUES.items()
    ):
        return
    gui.update(MAA_GUIDE_SKIP_VALUES)
