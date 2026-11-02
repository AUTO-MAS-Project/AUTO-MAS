#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from __future__ import annotations

import asyncio
import re
import smtplib
import ssl
import traceback
from collections.abc import Sequence
from dataclasses import dataclass, field
from email.header import Header
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from html import escape as html_escape
from pathlib import Path
from typing import Literal

from app.models.notification import (
    NOTIFICATION_HTML_IMAGE_SOURCE_PATTERN,
    NOTIFICATION_IMAGE_URI_PATTERN,
    NotificationImage,
)
from app.models.notification.channel import MailDependencies, NotificationDeliveryError

SMTP_TIMEOUT_SECONDS = 15
_MAIL_IMAGE_TAG_PATTERN = re.compile(r"<img\b[^>]*>", re.IGNORECASE)


@dataclass(frozen=True)
class MailTransport:
    smtp_server: str
    from_address: str
    authorization_code: str = field(repr=False)


def _rewrite_mail_image_sources(
    content: str,
    replacements: dict[str, str],
    fallback_images: dict[str, NotificationImage],
) -> str:
    """把渲染器确认过的完整资源地址编码为邮件协议地址。"""

    def replace_failed_tag(match: re.Match[str]) -> str:
        tag = match.group(0)
        source = NOTIFICATION_HTML_IMAGE_SOURCE_PATTERN.search(tag)
        if source is None:
            return tag
        image_id = source.group("id")
        if image_id in fallback_images:
            return html_escape(fallback_images[image_id].alt)
        return tag

    if fallback_images:
        content = _MAIL_IMAGE_TAG_PATTERN.sub(replace_failed_tag, content)

    def encode_reference(match: re.Match[str]) -> str:
        replacement = replacements.get(match.group("id"))
        if replacement is None:
            return match.group(0)
        return html_escape(replacement, quote=True)

    return NOTIFICATION_IMAGE_URI_PATTERN.sub(encode_reference, content)


class Sender:
    def __init__(self, dependencies: MailDependencies) -> None:
        self.dependencies = dependencies

    async def send_mail(
        self,
        mode: Literal["文本", "网页"],
        title: str,
        content: str,
        to_address: str,
        *,
        images: Sequence[NotificationImage] = (),
    ) -> None:
        """
        推送邮件通知

        Parameters
        ----------
        mode: Literal["文本", "网页"]
            邮件内容模式, 支持 "文本" 和 "网页"
        title: str
            邮件标题
        content: str
            邮件内容
        to_address: str
            收件人地址
        images: Sequence[NotificationImage], optional
            网页模式下随信内嵌的图片；文本模式忽略
        """

        config = self.dependencies.config
        transport = MailTransport(
            smtp_server=config.get("SMTPServerAddress"),
            from_address=config.get("FromAddress"),
            authorization_code=config.get("AuthorizationCode"),
        )
        try:
            if transport.smtp_server == "":
                raise ValueError("邮件通知的SMTP服务器地址不能为空")
            if transport.authorization_code == "":
                raise ValueError("邮件通知的授权码不能为空")
            if not bool(
                re.match(
                    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                    transport.from_address,
                )
            ):
                raise ValueError("邮件通知的发送邮箱格式错误或为空")
            if not bool(
                re.match(
                    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                    to_address,
                )
            ):
                raise ValueError("邮件通知的接收邮箱格式错误或为空")
        except ValueError as exc:
            # 此处仅包含本渠道的固定校验文案，不含地址、授权码或第三方异常。
            self.dependencies.logger.warning(f"邮件通知配置错误: {exc}")
            raise

        email_images = []
        if mode == "网页":
            replacements: dict[str, str] = {}
            fallback_images: dict[str, NotificationImage] = {}
            for image in images:
                if image.data is None:
                    replacements[image.id] = image.url or image.alt
                    continue
                try:
                    subtype = image.mime_type.split("/", 1)[-1]
                    part = MIMEImage(image.data, _subtype=subtype)
                except Exception as exc:
                    fallback_images[image.id] = image
                    self.dependencies.logger.warning(
                        f"网页邮件图片 {image.id} 无法内嵌，已保留替代文字: {type(exc).__name__}"
                    )
                    continue
                part.add_header("Content-ID", f"<{image.id}>")
                part.add_header(
                    "Content-Disposition",
                    "inline",
                    filename=f"{image.id}.{subtype}",
                )
                replacements[image.id] = f"cid:{image.id}"
                email_images.append(part)
            content = _rewrite_mail_image_sources(
                content, replacements, fallback_images
            )

        # 定义邮件正文
        if mode == "文本":
            message = MIMEText(content, "plain", "utf-8")
        elif mode == "网页" and email_images:
            message = MIMEMultipart("related")
        elif mode == "网页":
            message = MIMEMultipart("alternative")
        message["From"] = formataddr(
            (
                Header("AUTO-MAS通知服务", "utf-8").encode(),
                transport.from_address,
            )
        )  # 发件人显示的名字
        message["To"] = formataddr(
            (Header("AUTO-MAS用户", "utf-8").encode(), to_address)
        )  # 收件人显示的名字
        message["Subject"] = str(Header(title, "utf-8"))

        if mode == "网页":
            message.attach(MIMEText(content, "html", "utf-8"))
            for part in email_images:
                message.attach(part)

        smtp_server = transport.smtp_server
        from_address = transport.from_address
        authorization_code = transport.authorization_code

        def send() -> None:
            stage = "连接"
            smtp_obj = None
            try:
                with self.dependencies.smtp_factory(
                    smtp_server,
                    465,
                    timeout=SMTP_TIMEOUT_SECONDS,
                ) as smtp_obj:
                    stage = "握手"
                    if not smtp_obj.local_hostname.isascii():
                        smtp_obj.local_hostname = smtp_obj.local_hostname.encode(
                            "idna"
                        ).decode("ascii")
                    stage = "认证"
                    smtp_obj.login(from_address, authorization_code)
                    stage = "发送"
                    smtp_obj.sendmail(from_address, to_address, message.as_string())
                    stage = "关闭连接"
            except Exception as exc:
                frames = traceback.extract_tb(exc.__traceback__)
                if any(
                    Path(frame.filename).name == "smtplib.py"
                    and frame.name in {"ehlo", "helo", "ehlo_or_helo_if_needed"}
                    for frame in frames
                ):
                    stage = "握手"
                hostname = getattr(smtp_obj, "local_hostname", None)
                hostname_is_ascii = (
                    hostname.isascii() if isinstance(hostname, str) else None
                )
                # 只记录状态和栈位置，不附带异常原文、源码行或局部变量。
                self.dependencies.logger.warning(
                    f"邮件发送诊断: 阶段={stage}, 异常={type(exc).__name__}, "
                    f"EHLO主机名ASCII={hostname_is_ascii}, "
                    f"授权码ASCII={authorization_code.isascii()}, 调用位置: "
                    + " -> ".join(
                        f"{Path(frame.filename).name}:{frame.lineno} in {frame.name}"
                        for frame in frames
                    )
                )
                raise

        try:
            await asyncio.to_thread(send)
        except smtplib.SMTPRecipientsRefused as exc:
            temporary = any(400 <= code < 500 for code, _ in exc.recipients.values())
            raise NotificationDeliveryError(
                "邮件收件人被拒绝", kind="rejected", retryable=temporary
            ) from exc
        except smtplib.SMTPResponseException as exc:
            temporary = 400 <= exc.smtp_code < 500
            raise NotificationDeliveryError(
                "邮件服务器拒绝请求",
                kind="transport"
                if temporary
                else "configuration"
                if isinstance(exc, smtplib.SMTPAuthenticationError)
                else "rejected",
                retryable=temporary,
            ) from exc
        except (smtplib.SMTPNotSupportedError, ssl.SSLCertVerificationError) as exc:
            raise NotificationDeliveryError(
                "邮件服务器配置不可用", kind="configuration", retryable=False
            ) from exc
        except (OSError, smtplib.SMTPServerDisconnected) as exc:
            raise NotificationDeliveryError(
                "邮件连接失败", kind="transport", retryable=True
            ) from exc
        self.dependencies.logger.success(f"邮件发送成功: {title}")
