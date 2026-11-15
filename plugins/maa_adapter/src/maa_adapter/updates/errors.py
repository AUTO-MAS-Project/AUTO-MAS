#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MAA 更新中不能降级为普通警告的安装或写入异常。"""


class MaaUpdateUnsafeError(RuntimeError):
    """更新后无法确认安装可用或写入完成，不能继续启动账号任务。"""
