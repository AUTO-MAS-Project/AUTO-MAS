#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""通知编排与渠道服务共用的内部消息类型。"""

import re
from dataclasses import dataclass
from typing import Literal

NotificationFormat = Literal["text", "markdown", "html"]
ImagePresentation = Literal["html", "markdown", "base64"]
SummaryPolicy = Literal["never", "preferred", "if_over_limit"]
BodyTitlePolicy = Literal["never", "always", "when_title_missing"]

NOTIFICATION_IMAGE_SCHEME = "notify-image://"
# 渲染器和传输适配共用图片地址语法，保证资源 ID 按完整边界匹配。
NOTIFICATION_IMAGE_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.-]*"
NOTIFICATION_IMAGE_URI_PATTERN = re.compile(
    rf"{re.escape(NOTIFICATION_IMAGE_SCHEME)}(?P<id>{NOTIFICATION_IMAGE_ID_PATTERN})"
)
NOTIFICATION_HTML_IMAGE_SOURCE_PATTERN = re.compile(
    rf"(?P<prefix>\bsrc\s*=\s*)(?P<quote>['\"]){re.escape(NOTIFICATION_IMAGE_SCHEME)}"
    rf"(?P<id>{NOTIFICATION_IMAGE_ID_PATTERN})(?P=quote)",
    re.IGNORECASE,
)
NOTIFICATION_SIGNATURE = "AUTO-MAS 敬上"

# 能力解析和 Webhook 发送适配必须使用同一组协议标识。
DEFAULT_WEBHOOK_TEMPLATE = '{"title": "{title}", "content": "{content}"}'
WECOM_ROBOT_HOST = "qyapi.weixin.qq.com"
WECOM_ROBOT_PATH = "/cgi-bin/webhook/send"


def image_reference(image_id: str) -> str:
    """返回正文模板里引用图片资源的内部地址。"""

    return f"{NOTIFICATION_IMAGE_SCHEME}{image_id}"


@dataclass(frozen=True)
class NotificationImage:
    """通知图片资源，可由内存数据或现有 URL 提供。"""

    id: str
    data: bytes | None = None
    url: str | None = None
    alt: str = ""
    mime_type: str = "image/png"

    def __post_init__(self) -> None:
        if re.fullmatch(NOTIFICATION_IMAGE_ID_PATTERN, self.id) is None:
            raise ValueError("通知图片资源 ID 格式无效")
        if self.data is None and not self.url:
            raise ValueError("通知图片资源必须提供 data 或 url")


@dataclass(frozen=True)
class NotificationSummary:
    """供紧凑目标使用的业务摘要。"""

    text: str
    title: str | None = None
    # 正文超出目标限制时使用；与系统通知等渠道展示的紧凑文字分开。
    overflow_text: str | None = None


@dataclass(frozen=True)
class NotifyPayload:
    """业务提供的通用通知内容，不包含渠道协议字段。"""

    title: str
    text: str
    summary: NotificationSummary | None = None
    markdown: str | None = None
    html: str | None = None
    images: tuple[NotificationImage, ...] = ()
    append_signature: bool = True
    signature_sep: str = "\n\n"
    # 用于正文需要独立标题、但目标协议没有单独标题字段的通知。
    body_title: str | None = None

    def __post_init__(self) -> None:
        image_ids = [image.id for image in self.images]
        if len(image_ids) != len(set(image_ids)):
            raise ValueError("通知图片资源 ID 必须唯一")


@dataclass(frozen=True)
class NotificationCapabilities:
    """一个具体投递目标在当前配置下的有效内容与图片能力。"""

    formats: tuple[NotificationFormat, ...] = ("text",)
    image_presentations: frozenset[ImagePresentation] = frozenset()
    append_signature: bool = True
    max_content_utf8_bytes: int | None = None
    body_title_policy: BodyTitlePolicy = "never"
    title_in_template: bool = False
    double_text_newlines: bool = False


@dataclass(frozen=True)
class RenderedNotification:
    """为一个目标准备好的内容，发送重试期间保持不变。"""

    title: str
    content: str
    format: NotificationFormat
    images: tuple[NotificationImage, ...] = ()
    text_fallback: str | None = None
    summary_used: bool = False
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class WebhookTargetSnapshot:
    """创建投递目标时读取的 Webhook 配置快照。"""

    name: str
    enabled: bool
    url: str
    template: str
    headers: str
    method: Literal["GET", "POST"]

    def get(self, group: str, name: str) -> str | bool:
        """提供与配置对象一致的只读字段访问，供渠道服务组装请求。"""

        values = {
            ("Info", "Name"): self.name,
            ("Info", "Enabled"): self.enabled,
            ("Data", "Url"): self.url,
            ("Data", "Template"): self.template,
            ("Data", "Headers"): self.headers,
            ("Data", "Method"): self.method,
        }
        try:
            return values[(group, name)]
        except KeyError as exc:
            raise AttributeError(f"Webhook 配置项 '{group}.{name}' 不存在") from exc
