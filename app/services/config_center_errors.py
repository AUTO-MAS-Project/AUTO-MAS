#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""配置中心的共享错误契约，独立于网络客户端实现。"""


class ConfigCenterError(RuntimeError):
    """配置中心交互失败，message 可直接展示给用户。

    status_code 沿用配置中心的 HTTP 状态；本地校验失败为 400，网络失败为 503，
    其余未细分的失败为 500。reason 是配置中心拒绝的类别（pendingLimit / conflict / tooLarge），
    供前端按类别给出本地化提示，其余情况为空。
    """

    def __init__(
        self, message: str, *, status_code: int = 500, reason: str | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason
