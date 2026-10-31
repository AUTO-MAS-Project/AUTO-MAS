#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""General 分享业务的宿主装配，保持现有配置更新和网络客户端的生命周期。"""

from uuid import UUID

from app.config import ConfigEntry
from app.core import Config
from app.models.config import GeneralConfig
from app.services import ConfigCenter
from app.task.general.share_service import GeneralShareService


class _HostScripts:
    def get_script(self, uid: UUID) -> ConfigEntry | None:
        return Config.ScriptConfig[uid] if uid in Config.ScriptConfig else None

    async def update_script(self, uid: UUID, config: GeneralConfig) -> None:
        # 下载后重新查询 live 节点；同 Task 提交，沿用锁、信号和逐操作事务。
        await Config.ScriptConfig[uid].update(config, check_visibility=False)


general_share_service = GeneralShareService(
    scripts=_HostScripts(), config_center=ConfigCenter
)
