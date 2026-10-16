#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""宿主渠道目录、窄配置视图与依赖装配。"""

from __future__ import annotations

from typing import Any, Mapping

from app.models.notification_channel import (
    SCOPE_GLOBAL,
    NotifyChannel,
    NotifyChannelField,
)
from app.models.notification_channel import ChannelTarget as ChannelTarget
from app.notification_channels.registry import ChannelRegistry

_POLICY_FIELDS: Mapping[str, tuple[NotifyChannelField, ...]] = {
    SCOPE_GLOBAL: (
        NotifyChannelField(
            group="Notify",
            name="SendTaskResultTime",
            label_key="setting.notify.resultTime",
            control="select",
            options=(
                ("不推送", "setting.pushTime.never"),
                ("任何时刻", "setting.pushTime.always"),
                ("仅失败时", "setting.pushTime.failOnly"),
            ),
            tip_key="setting.notify.resultTimeTip",
        ),
        NotifyChannelField(
            group="Notify",
            name="IfSendStatistic",
            label_key="setting.notify.statistics",
            control="bool",
            tip_key="setting.notify.statisticsTip",
        ),
        NotifyChannelField(
            group="Notify",
            name="IfSendSixStar",
            label_key="setting.notify.recruit",
            control="bool",
            tip_key="setting.notify.recruitTip",
        ),
    )
}

_POLICY = NotifyChannel(
    key="policy",
    name_key="setting.notify.contentSection",
    desc_key="",
    icon="",
    group="builtin",
    order=90,
    doc_url=None,
    scopes=frozenset({SCOPE_GLOBAL}),
    kind="policy",
    custom_block=None,
    enable_field=None,
    summary_key=None,
    summary_fields=(),
    fields=_POLICY_FIELDS,
)

_registry: ChannelRegistry | None = None


class TargetConfigView:
    """只将 Notify 字段和目标集合暴露给内置渠道。"""

    def __init__(self, config: Any) -> None:
        self.__config = config

    def get(self, group: str, name: str) -> Any:
        if group != "Notify":
            raise ValueError("通知渠道只能读取 Notify 配置")
        return self.__config.get(group, name)

    @property
    def Notify_CustomWebhooks(self) -> Any:
        return self.__config.Notify_CustomWebhooks


def get_notify_channels() -> tuple[NotifyChannel, ...]:
    if _registry is None:
        raise RuntimeError("通知渠道尚未装配")
    return tuple(sorted((*_registry.channels, _POLICY), key=lambda c: (c.order, c.key)))


def initialize_notification_channels() -> None:
    """配置就绪后、开放发送入口前装配；连接仍由原管理器持有。"""
    global _registry
    from app.services.notification import Notify

    if Notify.initialized:
        return
    import smtplib

    import httpx
    from plyer import notification

    from app.core.config import Config
    from app.models.notification_channel import ChannelDependencies, MailTransport
    from app.services.cmcc_newmsg import send_cmcc_newmsg
    from app.services.openclaw_qq import openclaw_qq_manager
    from app.utils import get_logger, resource_path
    from app.utils.websocket import ws_client_manager

    def read_mail() -> MailTransport:
        return MailTransport(
            smtp_server=Config.get("Notify", "SMTPServerAddress"),
            from_address=Config.get("Notify", "FromAddress"),
            authorization_code=Config.get("Notify", "AuthorizationCode"),
        )

    dependencies = ChannelDependencies(
        read_mail=read_mail,
        read_proxy=lambda: Config.proxy,
        system_enabled=lambda: bool(Config.get("Notify", "IfPushPlyer")),
        smtp_factory=smtplib.SMTP_SSL,
        http_factory=httpx.AsyncClient,
        system_notify=notification.notify,
        system_icon=resource_path("icons", "AUTO-MAS.ico").as_posix(),
        get_client=ws_client_manager.get_client,
        send_qq=openclaw_qq_manager.send,
        send_cmcc=send_cmcc_newmsg,
        logger=get_logger("通知服务"),
    )
    # 下一阶段改为只从内置清单发现，注册项已经是唯一行为来源。
    from app.notification_channels.cmcc import register as register_cmcc
    from app.notification_channels.koishi import register as register_koishi
    from app.notification_channels.mail import register as register_mail
    from app.notification_channels.openclaw_qq import register as register_openclaw_qq
    from app.notification_channels.serverchan import register as register_serverchan
    from app.notification_channels.system import register as register_system
    from app.notification_channels.webhook import register as register_webhook

    registry = ChannelRegistry(
        [
            register_system(),
            register_mail(),
            register_serverchan(),
            register_cmcc(),
            register_webhook(),
            register_koishi(),
            register_openclaw_qq(),
        ]
    )
    bound = registry.bind(dependencies)
    Notify.bind(bound)
    _registry = registry
