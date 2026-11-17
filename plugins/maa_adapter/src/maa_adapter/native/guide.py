#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MAA 运行副本的引导跳过标记。"""

# shortcut: 上游改动引导字段或整型比较后可能重新弹引导；提供跳过入口后改为调用该入口。
MAA_GUIDE_SKIP_VALUES = {"GuideStep": 2**31 - 1, "GuideTutorialVersion": 2**31 - 1}
