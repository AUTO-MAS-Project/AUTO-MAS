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

"""按目标能力选择正文表达并降级图片引用。"""

import re
from html import escape, unescape

from app.models.notification import (
    NOTIFICATION_HTML_IMAGE_SOURCE_PATTERN,
    NOTIFICATION_IMAGE_ID_PATTERN,
    NOTIFICATION_IMAGE_SCHEME,
    NOTIFICATION_IMAGE_URI_PATTERN,
    NOTIFICATION_SIGNATURE,
    NotificationCapabilities,
    NotificationFormat,
    NotificationImage,
    NotifyPayload,
    RenderedNotification,
    SummaryPolicy,
)

_HTML_IMAGE_TAG_PATTERN = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_HTML_IMAGE_ALT_PATTERN = re.compile(
    r"\balt\s*=\s*(?P<quote>['\"])(?P<alt>.*?)(?P=quote)", re.IGNORECASE
)
_MARKDOWN_IMAGE_PATTERN = re.compile(
    rf"!\[(?P<alt>[^\]]*)\]\({re.escape(NOTIFICATION_IMAGE_SCHEME)}"
    rf"(?P<id>{NOTIFICATION_IMAGE_ID_PATTERN})\)"
)


def render_for_target(
    payload: NotifyPayload,
    capabilities: NotificationCapabilities,
    *,
    summary_policy: SummaryPolicy = "never",
    use_summary_title: bool = False,
) -> RenderedNotification:
    """依据一份消息和目标能力准备本次投递内容。

    This function is deterministic: it reads no configuration, performs no network
    requests, and leaves the input message unchanged.
    """

    selected_format, content = _select_format(payload, capabilities)
    title = payload.title
    used_summary = False

    if payload.summary is not None:
        if summary_policy == "preferred" and payload.summary.text:
            selected_format = "text"
            content = payload.summary.text
            used_summary = True

    if (
        used_summary
        and use_summary_title
        and payload.summary is not None
        and payload.summary.title
    ):
        title = payload.summary.title

    image_by_id = {image.id: image for image in payload.images}
    content, referenced_images, diagnostics = _render_content(
        payload,
        capabilities,
        selected_format,
        content,
        title,
        image_by_id,
    )

    byte_limit = capabilities.max_content_utf8_bytes
    over_limit = (
        payload.summary is not None
        and summary_policy == "if_over_limit"
        and byte_limit is not None
        and len(content.encode("utf-8")) > byte_limit
    )
    if over_limit and payload.summary is not None:
        if not payload.summary.text:
            diagnostics.append("正文超过目标字节上限，但没有可用的非空业务摘要")
        else:
            assert byte_limit is not None
            full_size = len(content.encode("utf-8"))
            selected_format = "text"
            content = payload.summary.text
            used_summary = True
            if use_summary_title and payload.summary.title:
                title = payload.summary.title
            content, referenced_images, diagnostics = _render_content(
                payload,
                capabilities,
                selected_format,
                content,
                title,
                image_by_id,
            )
            diagnostics.append(
                f"正文为 {full_size} UTF-8 字节，超过目标上限 "
                f"{byte_limit}；已改用业务摘要"
            )
            summary_size = len(content.encode("utf-8"))
            if summary_size > byte_limit:
                diagnostics.append(
                    f"业务摘要为 {summary_size} UTF-8 字节，仍超过目标上限 "
                    f"{byte_limit}"
                )

    if "base64" in capabilities.image_presentations:
        target_images = tuple(
            image for image in payload.images if image.data is not None
        )
        for image in payload.images:
            if image.data is None:
                diagnostics.append(
                    f"图片 {image.id} 只有 URL，当前图片槽位需要本地数据；已保留正文"
                )
    else:
        target_images = tuple(referenced_images.values())

    text_fallback = None
    if selected_format == "html" and "text" in capabilities.formats:
        text_fallback, _, _ = _render_content(
            payload,
            capabilities,
            "text",
            payload.text,
            title,
            image_by_id,
        )

    return RenderedNotification(
        title=title,
        content=content,
        format=selected_format,
        images=target_images,
        text_fallback=text_fallback,
        summary_used=used_summary,
        diagnostics=tuple(dict.fromkeys(diagnostics)),
    )


def _render_content(
    payload: NotifyPayload,
    capabilities: NotificationCapabilities,
    content_format: NotificationFormat,
    content: str,
    title: str,
    image_by_id: dict[str, NotificationImage],
) -> tuple[str, dict[str, NotificationImage], list[str]]:
    """按同一顺序完成正文格式中的资源、标题、换行和签名处理。"""

    diagnostics: list[str] = []
    referenced_images: dict[str, NotificationImage] = {}
    if content_format == "html":
        content = _render_html_images(
            content,
            image_by_id,
            capabilities,
            referenced_images,
            diagnostics,
        )
    elif content_format == "markdown":
        content = _render_markdown_images(
            content,
            image_by_id,
            capabilities,
            diagnostics,
        )
    else:
        content = _render_text_images(content, image_by_id, diagnostics)

    content = _append_body_title(
        content,
        payload,
        title=title,
        content_format=content_format,
        capabilities=capabilities,
    )

    if content_format == "text" and capabilities.double_text_newlines:
        content = content.replace("\n", "\n\n")

    if payload.append_signature and capabilities.append_signature:
        if content_format == "html":
            if NOTIFICATION_SIGNATURE not in content:
                content = f"{content}<p>{escape(NOTIFICATION_SIGNATURE)}</p>"
        else:
            content = f"{content}{payload.signature_sep}{NOTIFICATION_SIGNATURE}"

    return content, referenced_images, diagnostics


def _select_format(
    payload: NotifyPayload,
    capabilities: NotificationCapabilities,
) -> tuple[NotificationFormat, str]:
    """按目标给出的优先级，选择业务实际提供的第一种正文。"""

    for content_format in capabilities.formats:
        content = (
            payload.text
            if content_format == "text"
            else getattr(payload, content_format)
        )
        if content is not None:
            return content_format, content
    raise ValueError("通知目标未声明可用的纯文本正文")


def _render_html_images(
    content: str,
    image_by_id: dict[str, NotificationImage],
    capabilities: NotificationCapabilities,
    referenced_images: dict[str, NotificationImage],
    diagnostics: list[str],
) -> str:
    """处理 HTML 的内部图片地址；CID 编码留给邮件服务。"""

    def replace_tag(match: re.Match[str]) -> str:
        tag = match.group(0)
        source = NOTIFICATION_HTML_IMAGE_SOURCE_PATTERN.search(tag)
        if source is None:
            return tag

        image_id = source.group("id")
        image = image_by_id.get(image_id)
        alt_match = _HTML_IMAGE_ALT_PATTERN.search(tag)
        alt = unescape(alt_match.group("alt")) if alt_match else ""
        alt = alt or (image.alt if image is not None else "")
        if image is None:
            diagnostics.append(
                f"正文引用了不存在的图片 {image_id}；已移除图片并保留替代文字"
            )
            return escape(alt)

        if "html" not in capabilities.image_presentations:
            diagnostics.append(f"目标不支持正文图片 {image_id}；已保留替代文字")
            return escape(alt)

        if image.data is not None:
            referenced_images.setdefault(image.id, image)
            return tag
        if image.url:
            old_source = (
                f"{source.group('quote')}{NOTIFICATION_IMAGE_SCHEME}"
                f"{image_id}{source.group('quote')}"
            )
            new_source = (
                f"{source.group('quote')}{escape(image.url, quote=True)}"
                f"{source.group('quote')}"
            )
            return tag.replace(old_source, new_source, 1)

        diagnostics.append(f"图片 {image_id} 没有可用来源；已保留替代文字")
        return escape(alt)

    rendered = _HTML_IMAGE_TAG_PATTERN.sub(replace_tag, content)
    return _render_unplaced_image_refs(
        rendered,
        image_by_id,
        diagnostics,
        preserve_ids=set(referenced_images),
    )


def _render_markdown_images(
    content: str,
    image_by_id: dict[str, NotificationImage],
    capabilities: NotificationCapabilities,
    diagnostics: list[str],
) -> str:
    """把 Markdown 图片引用换成 URL 图片或可读替代文字。"""

    def replace_image(match: re.Match[str]) -> str:
        image_id = match.group("id")
        image = image_by_id.get(image_id)
        alt = match.group("alt") or (image.alt if image is not None else "")
        if image is None:
            diagnostics.append(
                f"正文引用了不存在的图片 {image_id}；已保留替代文字"
            )
            return alt
        if "markdown" in capabilities.image_presentations and image.url:
            return f"![{alt or image.alt}]({image.url})"
        diagnostics.append(f"目标无法直接显示图片 {image_id}；已保留替代文字")
        return alt or image.alt

    rendered = _MARKDOWN_IMAGE_PATTERN.sub(replace_image, content)
    return _render_unplaced_image_refs(rendered, image_by_id, diagnostics)


def _render_text_images(
    content: str,
    image_by_id: dict[str, NotificationImage],
    diagnostics: list[str],
) -> str:
    """纯文本没有图片位置，遇到资源引用时退回替代文字。"""

    def replace_ref(match: re.Match[str]) -> str:
        image_id = match.group("id")
        image = image_by_id.get(image_id)
        if image is None:
            diagnostics.append(
                f"正文引用了不存在的图片 {image_id}；已移除图片并保留替代文字"
            )
            return ""
        diagnostics.append(f"纯文本目标无法显示图片 {image_id}；已保留替代文字")
        return image.alt

    return NOTIFICATION_IMAGE_URI_PATTERN.sub(replace_ref, content)


def _render_unplaced_image_refs(
    content: str,
    image_by_id: dict[str, NotificationImage],
    diagnostics: list[str],
    *,
    preserve_ids: set[str] | None = None,
) -> str:
    """清理未放入受支持 HTML/Markdown 图片位置的资源地址。"""

    def replace_ref(match: re.Match[str]) -> str:
        image_id = match.group("id")
        if (
            preserve_ids
            and image_id in preserve_ids
            and _is_html_image_source_reference(content, match)
        ):
            return match.group(0)
        image = image_by_id.get(image_id)
        if image is None:
            diagnostics.append(
                f"正文引用了不存在的图片 {image_id}；已移除图片引用"
            )
            return ""
        diagnostics.append(
            f"图片 {image_id} 的引用格式不受支持；已保留替代文字"
        )
        return escape(image.alt)

    return NOTIFICATION_IMAGE_URI_PATTERN.sub(replace_ref, content)


def _is_html_image_source_reference(
    content: str,
    reference: re.Match[str],
) -> bool:
    """只保留已验证的 ``<img src="notify-image://…">`` 引用。"""

    tag_start = content.rfind("<", 0, reference.start())
    if tag_start < 0 or content.rfind(">", 0, reference.start()) > tag_start:
        return False
    tag_match = _HTML_IMAGE_TAG_PATTERN.match(content, tag_start)
    if tag_match is None:
        return False
    source = NOTIFICATION_HTML_IMAGE_SOURCE_PATTERN.search(tag_match.group(0))
    if source is None:
        return False
    source_start = tag_start + source.start() + source.group(0).find(
        NOTIFICATION_IMAGE_SCHEME
    )
    return reference.start() == source_start and reference.end() == (
        source_start + len(reference.group(0))
    )


def _append_body_title(
    content: str,
    payload: NotifyPayload,
    *,
    title: str,
    content_format: NotificationFormat,
    capabilities: NotificationCapabilities,
) -> str:
    """按目标的标题呈现策略，把标题放在正文前。"""

    policy = capabilities.body_title_policy
    if policy == "never" or content_format == "html":
        return content
    if policy == "when_title_missing":
        if capabilities.title_in_template or not payload.body_title:
            return content
        heading = payload.body_title
    else:
        heading = payload.body_title or title
        if content.startswith(f"【{payload.title}】"):
            return content

    if content_format == "markdown":
        heading = f"**{heading}**"
    return f"{heading}\n\n{content}"
