#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright (C) 2024-2025 DLmaster361
#   Copyright (C) 2025-2026 AUTO-MAS Team

from __future__ import annotations

import html
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from app.utils import get_logger

if TYPE_CHECKING:
    from app.models.config import Webhook

logger = get_logger("通知服务")


class Notification:
    """Compatibility facade for the pluginized notification service."""

    _missing_warned = False

    def _service(self) -> Any | None:
        try:
            from app.plugins.manager import PluginManager

            return PluginManager.service.get("notify")
        except Exception as e:
            logger.warning(f"获取 notify 插件服务失败: {type(e).__name__}: {e}")
            return None

    def _missing_service(self) -> None:
        if self._missing_warned:
            return
        self._missing_warned = True
        logger.warning("notify 插件服务未启用，通知请求已跳过")

    async def _call(self, method: str, *args: Any, default: Any = None, **kwargs: Any) -> Any:
        service = self._service()
        if service is None:
            self._missing_service()
            return default

        handler = getattr(service, method, None)
        if not callable(handler):
            logger.warning(f"notify 插件服务缺少方法: {method}")
            return default
        return await handler(*args, **kwargs)

    async def push_plyer(self, title: str, message: str, ticker: str, t: int) -> bool:
        return bool(
            await self._call(
                "send_system",
                title=title,
                message=message,
                ticker=ticker,
                timeout=t,
                default=False,
            )
        )

    async def send_mail(
        self, mode: Literal["文本", "网页"], title: str, content: str, to_address: str
    ) -> bool:
        return bool(
            await self._call(
                "send_mail",
                mode=mode,
                title=title,
                content=content,
                to_address=to_address,
                default=False,
            )
        )

    def render_mail_template(
        self,
        template_name: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        try:
            from notification_mail.template_renderer import render_template

            return render_template(template_name, context)
        except ModuleNotFoundError:
            source_root = Path.cwd() / "plugins/notification_mail/src"
            normalized = str(source_root)
            if source_root.exists() and normalized not in sys.path:
                sys.path.insert(0, normalized)
            try:
                from notification_mail.template_renderer import render_template

                return render_template(template_name, context)
            except Exception as e:
                logger.warning(
                    f"从本地插件源码渲染邮件模板失败，将回退为简易 HTML: {template_name}, error={type(e).__name__}: {e}"
                )
        except Exception as e:
            logger.warning(
                f"渲染邮件模板失败，将回退为简易 HTML: {template_name}, error={type(e).__name__}: {e}"
            )
        payload = context or {}
        title = html.escape(str(payload.get("title") or "AUTO-MAS 通知"))
        lines = []
        for key, value in payload.items():
            if key == "title":
                continue
            lines.append(
                f"<p><strong>{html.escape(str(key))}：</strong>{html.escape(str(value))}</p>"
            )
        return (
            "<!DOCTYPE html><html><body>"
            f"<h2>{title}</h2>"
            + "".join(lines)
            + "</body></html>"
        )

    async def ServerChanPush(self, title: str, content: str, send_key: str) -> bool:
        return bool(
            await self._call(
                "send_serverchan",
                title=title,
                content=content,
                send_key=send_key,
                default=False,
            )
        )

    async def WebhookPush(self, title: str, content: str, webhook: Webhook) -> bool:
        return bool(
            await self._call(
                "send_webhook",
                title=title,
                content=content,
                webhook=webhook,
                default=False,
            )
        )

    async def _WebHookPush(self, title: str, content: str, webhook_url: str) -> bool:
        return bool(
            await self._call(
                "send_legacy_webhook",
                title=title,
                content=content,
                webhook_url=webhook_url,
                default=False,
            )
        )

    async def CompanyWebHookBotPushImage(self, image_path: Path, webhook_url: str) -> bool:
        return bool(
            await self._call(
                "send_webhook_image",
                image_path=image_path,
                webhook_url=webhook_url,
                default=False,
            )
        )

    async def send_koishi(
        self,
        message: str,
        msgtype: str = "text",
        client_name: str = "Koishi",
    ) -> bool:
        return bool(
            await self._call(
                "send_koishi",
                message=message,
                msgtype=msgtype,
                client_name=client_name,
                default=False,
            )
        )

    async def send(
        self,
        *,
        title: str,
        text: str,
        kind: str = "generic",
        serverchan_content: str | None = None,
        koishi_message: str | None = None,
        data: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, bool]:
        return await self._call(
            "send",
            title=title,
            text=text,
            kind=kind,
            serverchan_content=serverchan_content,
            koishi_message=koishi_message,
            data=data,
            extra=extra,
            default={},
        )

    async def should_send_task_result(self, message: dict[str, Any]) -> bool:
        return bool(
            await self._call(
                "should_send_task_result",
                message=message,
                default=False,
            )
        )

    async def should_send_statistic(self) -> bool:
        return bool(await self._call("should_send_statistic", default=False))

    async def should_send_six_star(self) -> bool:
        return bool(await self._call("should_send_six_star", default=False))

    async def send_test_notification(self) -> dict[str, bool]:
        return await self._call("send_test_notification", default={})


Notify = Notification()
