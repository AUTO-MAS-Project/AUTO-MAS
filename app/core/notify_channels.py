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

import inspect
from typing import Any, Mapping

from app.config import config_manager
from app.models.notification_channel import (
    SCOPE_GLOBAL,
    CommandExecutor,
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
        return getattr(self.__config.Notify, name)

    @property
    def Notify_CustomWebhooks(self) -> Any:
        return self.__config.Notify_CustomWebhooks


class RuntimeConfigView:
    """传输仅能读写原有 Notify 字段；校验、加密和保存仍由配置层处理。"""

    def __init__(self, config: Any) -> None:
        self.__config = config
        self.__receivers: list[Any] = []

    def get(self, name: str) -> Any:
        return getattr(self.__config.Notify, name)

    async def update(self, values: Mapping[str, Any]) -> None:
        # 机器人凭据、接收模式与目标是成组更新，任一字段被信号拒绝时整体回退。
        async with config_manager.transaction():
            await self.__config.update(
                type(self.__config).model_validate({"Notify": dict(values)}),
                check_visibility=False,
            )

    def bind(self, name: str, callback: Any) -> None:
        async def on_changed(sender, event):
            result = callback(event.value)
            if inspect.isawaitable(result):
                await result

        self.__receivers.append(on_changed)
        self.__config.connect(on_changed, phase="runtime", group="Notify", field=name)


def _get_registry() -> ChannelRegistry:
    global _registry
    if _registry is None:
        from app.notification_channels.discovery import (
            discover_channels,
            register_channels,
        )
        from app.utils import get_logger

        manifests, discovery_errors = discover_channels()
        registry, diagnostics = register_channels(
            manifests, discovery_errors=discovery_errors
        )
        for diagnostic in diagnostics:
            get_logger("通知服务").warning(
                f"通知渠道 {diagnostic.channel} 不可用 ({diagnostic.stage}): {diagnostic.reason}"
            )
        _registry = registry
    return _registry


def get_notify_channels() -> tuple[NotifyChannel, ...]:
    """目录读取不依赖传输装配；未装配时仍禁止发送。"""
    registry = _get_registry()
    return tuple(sorted((*registry.channels, _POLICY), key=lambda c: (c.order, c.key)))


def get_notify_channel_failures() -> tuple[str, ...]:
    """目录不完整时明确保留不确定性，不假定损坏渠道未启用。"""

    return tuple(f"通知渠道目录未确认（{key}）" for key in _get_registry().unresolved)


def read_notification_proxy() -> str | None:
    import httpx

    from app.core.config import Config
    from app.utils import get_logger

    # 沿用 Config.proxy 的校验/无效值回退，但不记录含凭据的代理地址。
    url = Config.proxy_url
    if not url:
        return None
    try:
        # 只校验格式，HTTP 与 WebSocket 共用原始代理地址。
        httpx.Proxy(url)
        return url
    except Exception as exc:
        get_logger("通知服务").warning(f"通知代理配置无效: {type(exc).__name__}")
        return None


def initialize_notification_channels(
    *, command_executor: CommandExecutor | None = None
) -> None:
    """配置就绪后装配单个渠道实例；连接在后台初始化阶段统一启动。"""
    from app.services.notification import Notify

    if Notify.initialized:
        return
    import smtplib

    from app.core.config import Config
    from app.models.notification_channel import ChannelDependencies
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

    def http_client(**kwargs: Any) -> Any:
        import httpx

        return httpx.AsyncClient(**kwargs)

    def websocket_connect(*args: Any, **kwargs: Any) -> Any:
        from websockets.asyncio.client import connect

        return connect(*args, **kwargs)

    def websocket_manager() -> Any:
        from app.utils.websocket import WSClientManager

        return WSClientManager()

    dependencies = ChannelDependencies(
        config=RuntimeConfigView(Config.setting),
        read_proxy=read_notification_proxy,
        smtp_factory=smtplib.SMTP_SSL,
        http_factory=http_client,
        websocket_connect=websocket_connect,
        websocket_manager_factory=websocket_manager,
        system_notify=system_notify,
        system_icon=resource_path("icons", "AUTO-MAS.ico").as_posix(),
        logger=get_logger("通知服务"),
        command_executor=command_executor,
    )
    Notify.bind(registry.bind(dependencies))


def get_channel_sender(key: str) -> Any:
    """API 与发送链路共用已装配的渠道实例。"""
    from app.services.notification import Notify

    return Notify.channel_sender(key)
