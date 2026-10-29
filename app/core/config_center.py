#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""配置中心客户端的宿主装配，API 与 General 分享共用授权和跳转状态。"""

from app.core import Config
from app.services.config_center import ConfigCenterClient


class _HostAppearanceUploads:
    def read(self) -> str:
        return Config.setting.Data.ShareAppearanceUploads

    async def write(self, content: str) -> None:
        # 同 Task 更新单个字段，沿用配置框架的锁、信号与提交边界。
        await Config.setting.update(
            type(Config.setting).model_validate(
                {"Data": {"ShareAppearanceUploads": content}}
            ),
            check_visibility=False,
        )


config_center_client = ConfigCenterClient(
    get_proxy=lambda: Config.proxy,
    appearance_uploads=_HostAppearanceUploads(),
)
