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

from __future__ import annotations

import re
from _thread import RLock as RLockType
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property
from threading import RLock
from typing import Any, Literal, Protocol, cast

NotificationFormat = Literal["text", "markdown", "html"]
ImagePresentation = Literal["html", "markdown", "base64", "rich_media"]
SummaryPolicy = Literal["never", "preferred", "if_over_limit"]
BodyTitlePolicy = Literal["never", "always", "when_title_missing"]


class NotificationContentError(RuntimeError):
    """可选表达生成失败；不携带模板上下文或账号数据。"""


@dataclass(frozen=True)
class DeferredContent[T]:
    """按需生成一份可选表达，同一通知的多个目标和重试共用结果。"""

    factory: Callable[[], T]
    # 在事件循环上解析依赖，返回不再做冷导入的工作函数。
    prepare_factory: Callable[[], Callable[[], T]] | None = field(
        default=None, repr=False, compare=False
    )
    dependencies: tuple[DeferredContent[Any], ...] = field(
        default=(), repr=False, compare=False
    )

    def __post_init__(self) -> None:
        # 执行状态不进入 dataclass 字段或 Pydantic 的外部契约。
        self.__dict__["_content_lock"] = RLock()

    @property
    def _lock(self) -> RLockType:
        return self.__dict__["_content_lock"]

    @cached_property
    def _prepared(self) -> tuple[Callable[[], T] | None, str | None]:
        try:
            return (
                self.prepare_factory()
                if self.prepare_factory is not None
                else self.factory,
                None,
            )
        except Exception as exc:
            return None, type(exc).__name__

    def prepare_for_render(self) -> None:
        for dependency in self.dependencies:
            dependency.prepare_for_render()
        # 依赖失败仍作为该可选表达的失败，由目标渲染决定是否降级。
        _ = self._prepared

    @cached_property
    def _result(self) -> tuple[T | None, str | None]:
        with self._lock:
            if "_result" in self.__dict__:
                return self.__dict__["_result"]
            factory, error = self._prepared
            try:
                result = (factory(), None) if factory is not None else (None, error)
            except Exception as exc:
                result = None, type(exc).__name__
            # cached_property 在 Python 3.12 不串行化并发读取，必须在释放锁前登记。
            self.__dict__["_result"] = result
            return result

    def resolve(self) -> T:
        value, error = self._result
        if error is not None:
            raise NotificationContentError(error)
        return cast(T, value)


def resolve_content[T](content: T | DeferredContent[T]) -> T:
    return content.resolve() if isinstance(content, DeferredContent) else content


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
    markdown: str | DeferredContent[str] | None = None
    html: str | DeferredContent[str] | None = None
    images: (
        tuple[NotificationImage, ...] | DeferredContent[tuple[NotificationImage, ...]]
    ) = ()
    append_signature: bool = True
    signature_sep: str = "\n\n"
    # 用于正文需要独立标题、但目标协议没有单独标题字段的通知。
    body_title: str | None = None
    presentation: Literal["default", "announcement"] = "default"

    def __post_init__(self) -> None:
        if isinstance(self.images, DeferredContent):
            return
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


class NotificationRenderer(Protocol):
    async def render(
        self,
        payload: NotifyPayload,
        capabilities: NotificationCapabilities,
        *,
        summary_policy: SummaryPolicy = "never",
        use_summary_title: bool = False,
    ) -> RenderedNotification: ...


@dataclass(frozen=True)
class WebhookTargetSnapshot:
    """创建投递目标时读取的 Webhook 配置快照。"""

    name: str
    enabled: bool
    url: str
    template: str
    headers: str
    method: Literal["GET", "POST"]


@dataclass(frozen=True)
class LocalNotice:
    """一次本地系统弹窗的内容与显示时长。"""

    title: str
    message: str
    ticker: str
    duration_seconds: int
