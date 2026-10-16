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


def _get_registry() -> ChannelRegistry:
    global _registry
    if _registry is None:
        from app.notification_channels.discovery import (
            discover_channels,
            register_channels,
        )
        from app.utils import get_logger

        manifests, discovery_errors = discover_channels()
        registry, registration_errors = register_channels(manifests)
        for diagnostic in (*discovery_errors, *registration_errors):
            get_logger("通知服务").warning(
                f"通知渠道 {diagnostic.channel} 不可用 ({diagnostic.stage}): {diagnostic.reason}"
            )
        _registry = registry
    return _registry


def get_notify_channels() -> tuple[NotifyChannel, ...]:
    """目录读取不依赖传输装配；未装配时仍禁止发送。"""
    registry = _get_registry()
    return tuple(sorted((*registry.channels, _POLICY), key=lambda c: (c.order, c.key)))


def initialize_notification_channels() -> None:
    """配置就绪后、开放发送入口前装配；连接仍由原管理器持有。"""
    from app.services.notification import Notify

    if Notify.initialized:
        return
    import smtplib

    from app.core.config import Config
    from app.models.notification_channel import ChannelDependencies, MailTransport
    from app.utils import get_logger, resource_path

    registry = _get_registry()
    system_notify = None
    if "system" in registry.by_id:
        try:
            from plyer import notification

            # 在事件循环线程解析 plyer 的惰性后端，再交给工作线程调用。
            system_notify = notification.notify
        except Exception as exc:
            get_logger("通知服务").warning(f"系统通知依赖不可用: {type(exc).__name__}")

    def read_mail() -> MailTransport:
        return MailTransport(
            smtp_server=Config.get("Notify", "SMTPServerAddress"),
            from_address=Config.get("Notify", "FromAddress"),
            authorization_code=Config.get("Notify", "AuthorizationCode"),
        )

    def read_proxy() -> Any:
        import httpx

        # 沿用 Config.proxy 的校验/无效值回退，但不记录含凭据的代理地址。
        url = Config.proxy_url
        if not url:
            return None
        try:
            return httpx.Proxy(url)
        except Exception as exc:
            get_logger("通知服务").warning(f"通知代理配置无效: {type(exc).__name__}")
            return None

    def http_client(**kwargs: Any) -> Any:
        import httpx

        return httpx.AsyncClient(**kwargs)

    def get_client(name: str) -> Any:
        from app.utils.websocket import ws_client_manager

        return ws_client_manager.get_client(name)

    async def send_qq(**kwargs: Any) -> bool | None:
        from app.services.openclaw_qq import openclaw_qq_manager

        return await openclaw_qq_manager.send(**kwargs)

    async def send_cmcc(**kwargs: Any) -> None:
        from app.services.cmcc_newmsg import send_cmcc_newmsg

        await send_cmcc_newmsg(**kwargs)

    dependencies = ChannelDependencies(
        read_mail=read_mail,
        read_proxy=read_proxy,
        system_enabled=lambda: bool(Config.get("Notify", "IfPushPlyer")),
        smtp_factory=smtplib.SMTP_SSL,
        http_factory=http_client,
        system_notify=system_notify,
        system_icon=resource_path("icons", "AUTO-MAS.ico").as_posix(),
        get_client=get_client,
        send_qq=send_qq,
        send_cmcc=send_cmcc,
        logger=get_logger("通知服务"),
    )
    Notify.bind(registry.bind(dependencies))
