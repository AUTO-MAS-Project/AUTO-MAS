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

import base64
import hashlib
import ipaddress
import json
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from app.models.notification import (
    DEFAULT_WEBHOOK_TEMPLATE,
    WECOM_ROBOT_HOST,
    WECOM_ROBOT_PATH,
    NotificationImage,
    WebhookTargetSnapshot,
)

if TYPE_CHECKING:
    from httpx import Proxy

from app.core.notify.channels.common import RemoteHTTPError, http_delivery_errors
from app.models.notification.channel import HttpDependencies, NotificationDeliveryError

UTC4 = timezone(timedelta(hours=4))
# OneBot 图片段里的占位写法，前端预设与这里必须一致。
WEBHOOK_IMAGE_PLACEHOLDER = "base64://{image_base64}"
# 企业微信群机器人图片消息只收 JPG/PNG，原图不超过 2MB。
WECOM_IMAGE_MAX_BYTES = 2 * 1024 * 1024


def webhook_body_failure(text: str, url: str = "") -> str | None:
    """从 HTTP 2xx 的响应体里识别机器人平台的业务失败。

    钉钉、企业微信自定义机器人被关键词/签名校验拦下、飞书 token 无效、OneBot
    动作失败时都回 200，只在 JSON 里写 ``errcode`` / ``code`` / ``status``；
    只看状态码会把这些记成「推送成功」，用户以为通知没发。识别出失败时返回
    不含响应原文的错误码，正常或看不懂的响应返回 None。
    """

    if not text:
        return None
    try:
        body = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(body, dict):
        return None

    # 钉钉 / 企业微信：成功一律 errcode 0。
    errcode = body.get("errcode")
    if isinstance(errcode, int) and not isinstance(errcode, bool) and errcode != 0:
        return f"errcode={errcode}"
    # OneBot v11：status 为 failed 才算失败，retcode 只是补充。
    if str(body.get("status", "")).lower() == "failed":
        retcode = body.get("retcode")
        return f"retcode={retcode}" if type(retcode) is int else "status=failed"
    # 飞书：只在飞书域名下解读 code，别的服务常拿 code=200 当成功。
    host = (urlparse(url).hostname or "").lower()
    if host.endswith(("feishu.cn", "larksuite.com")):
        code = body.get("code")
        if isinstance(code, int) and not isinstance(code, bool) and code != 0:
            return f"code={code}"
    return None


def _webhook_client_kwargs(url: str, proxy: str | Proxy | None) -> dict:
    """根据 Webhook 目标地址生成 httpx 客户端参数。

    本地/内网目标（loopback、RFC1918 私网等）绕过代理并忽略环境变量中的
    代理设置，避免 localhost 推送被系统代理劫持后返回误导性的 502；
    外部目标沿用全局代理配置（含环境变量代理，保持历史行为）。
    """
    hostname = urlparse(url).hostname or ""
    try:
        addr = ipaddress.ip_address(hostname)
        is_local = addr.is_loopback or addr.is_private
    except ValueError:
        is_local = hostname.lower() == "localhost"
    if is_local:
        return {"timeout": 10, "trust_env": False}
    return {"timeout": 10, "proxy": proxy}


def _is_webhook_image_placeholder(obj: object) -> bool:
    """是不是 OneBot 预设里那段 ``base64://{image_base64}`` 图片。"""

    return (
        isinstance(obj, dict)
        and obj.get("type") == "image"
        and isinstance(obj.get("data"), dict)
        and obj["data"].get("file") == WEBHOOK_IMAGE_PLACEHOLDER
    )


def _is_wecom_robot(url: str) -> bool:
    """是不是企业微信群机器人的 Webhook 地址。"""

    parsed = urlparse(url)
    return (parsed.hostname or "").lower() == WECOM_ROBOT_HOST and (
        parsed.path == WECOM_ROBOT_PATH
    )


class Sender:
    def __init__(self, dependencies: HttpDependencies) -> None:
        self.dependencies = dependencies

    async def WebhookPush(
        self,
        title: str,
        content: str,
        webhook: WebhookTargetSnapshot,
        *,
        images: Sequence[NotificationImage] = (),
    ) -> None:
        """
        Webhook 推送通知

        Parameters
        ----------
        title: str
            通知标题
        content: str
            通知内容
        webhook: WebhookTargetSnapshot
            目标准备或草稿测试时固定的只读快照
        images: Sequence[NotificationImage], optional
            可选图片资源，由 Webhook 协议适配器编码
        """
        proxy = self.dependencies.read_proxy()
        image = images[-1] if images else None
        image_base64 = (
            base64.b64encode(image.data).decode("ascii")
            if image is not None and image.data is not None
            else ""
        )
        if not webhook.enabled:
            return

        if webhook.url == "":
            self.dependencies.logger.warning("Webhook URL 不能为空")
            raise ValueError("Webhook URL 不能为空")

        # 解析模板
        template = webhook.template or DEFAULT_WEBHOOK_TEMPLATE

        # 替换模板变量
        try:
            # 准备模板变量
            template_vars = {
                "title": title,
                "content": content,
                "image_base64": image_base64,
                "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": datetime.now().strftime("%H:%M:%S"),
                # 游戏日（东 4 区），与历史记录归档的日期分组一致。
                # {date} 保持本地日期语义不变。
                "gamedate": datetime.now(tz=UTC4).strftime("%Y-%m-%d"),
            }

            self.dependencies.logger.debug("开始解析 Webhook 消息模板")

            # 先尝试作为JSON模板处理
            try:
                # 解析模板为JSON对象，然后替换其中的变量
                template_obj = json.loads(template)

                # 递归替换JSON对象中的变量
                def replace_variables(obj):
                    if isinstance(obj, dict):
                        # 普通任务报告没有图片时，OneBot 图片模板仍需投递可读正文。
                        if not image_base64 and _is_webhook_image_placeholder(obj):
                            return {
                                "type": "text",
                                "data": {"text": f"{title}\n\n{content}"},
                            }
                        return {k: replace_variables(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        # 「文本 + 图片」模板没图时只去掉图片段，别把正文发两遍。
                        if not image_base64 and any(
                            not _is_webhook_image_placeholder(item) for item in obj
                        ):
                            obj = [
                                item
                                for item in obj
                                if not _is_webhook_image_placeholder(item)
                            ]
                        return [replace_variables(item) for item in obj]
                    elif isinstance(obj, str):
                        result = obj
                        for key, value in template_vars.items():
                            result = result.replace(f"{{{key}}}", str(value))
                        return result
                    else:
                        return obj

                data = replace_variables(template_obj)
                self.dependencies.logger.debug("Webhook JSON 模板解析成功")

            except json.JSONDecodeError:
                # 如果不是有效的JSON，作为字符串模板处理
                self.dependencies.logger.debug("模板不是有效JSON，作为字符串模板处理")
                formatted_template = template
                for key, value in template_vars.items():
                    # 转义特殊字符以避免JSON解析错误
                    safe_value = (
                        str(value)
                        .replace('"', '\\"')
                        .replace("\n", "\\n")
                        .replace("\r", "\\r")
                    )
                    formatted_template = formatted_template.replace(
                        f"{{{key}}}", safe_value
                    )

                # 再次尝试解析为JSON
                try:
                    data = json.loads(formatted_template)
                    self.dependencies.logger.debug("Webhook 字符串模板已解析为 JSON")
                except json.JSONDecodeError:
                    # 最终作为纯文本发送
                    data = formatted_template
                    self.dependencies.logger.debug("Webhook 模板将作为纯文本发送")

        except Exception as e:
            self.dependencies.logger.warning(
                f"模板解析失败，使用默认格式: {type(e).__name__}"
            )
            data = {"title": title, "content": content}

        # 准备请求头
        headers = {"Content-Type": "application/json"}
        headers.update(json.loads(webhook.headers))

        url = webhook.url

        with http_delivery_errors():
            async with self.dependencies.http_factory(
                **_webhook_client_kwargs(url, proxy)
            ) as client:
                if webhook.method == "POST":
                    if isinstance(data, str):
                        response = await client.post(
                            url=url, content=data, headers=headers
                        )
                    elif data is None:
                        # httpx 的 json=None 会发送空请求体，JSON null 需显式发送。
                        response = await client.post(
                            url=url, content="null", headers=headers
                        )
                    else:
                        response = await client.post(
                            url=url, json=data, headers=headers
                        )
                elif webhook.method == "GET":
                    if isinstance(data, dict):
                        # Flatten params to ensure all values are str or list of str
                        params = {}
                        for k, v in data.items():
                            if isinstance(v, (dict, list)):
                                params[k] = json.dumps(v, ensure_ascii=False)
                            else:
                                params[k] = str(v)
                    else:
                        params = {"message": str(data)}
                    response = await client.get(url=url, params=params, headers=headers)

        # 检查响应
        if not response.is_success:
            self.dependencies.logger.warning(
                f"Webhook 推送失败: HTTP {response.status_code}"
            )
            raise RemoteHTTPError(
                response.status_code, f"[{webhook.name}] HTTP {response.status_code}"
            )
        failure = webhook_body_failure(response.text, url)
        if failure is not None:
            self.dependencies.logger.warning(f"Webhook 服务端拒绝: {failure}")
            raise NotificationDeliveryError(
                f"[{webhook.name}] 服务端拒绝", kind="rejected", retryable=True
            )
        self.dependencies.logger.success(
            f"自定义Webhook推送成功: {webhook.name} - {title}"
        )

        # 企业微信群机器人的文本消息放不下图，失败截图要单独补发一条图片消息；
        # 模板里自己写了 {image_base64} 的说明用户已经处理过图，不再补发。
        if image_base64 and "{image_base64}" not in template and _is_wecom_robot(url):
            await self._push_wecom_image(
                url, image_base64, headers, webhook.name, proxy=proxy
            )

    async def _push_wecom_image(
        self,
        url: str,
        image_base64: str,
        headers: dict,
        name: str,
        *,
        proxy: str | Proxy | None,
    ) -> None:
        """给企业微信群机器人补发一条图片消息。

        正文那条已经送达，图片发不出去只记警告，不让整条通知算失败。日志里
        不带 URL，里面的 key 就是机器人的发送凭据。

        Args:
            url: 企业微信群机器人 Webhook 地址。
            image_base64: 图片的纯 Base64 数据。
            headers: 与正文那条相同的请求头。
            name: Webhook 名称，只用于日志。
        """

        try:
            raw = base64.b64decode(image_base64, validate=True)
        except ValueError:
            self.dependencies.logger.warning(
                f"企业微信图片补发跳过: {name} - 图片不是有效的 Base64"
            )
            return
        if len(raw) > WECOM_IMAGE_MAX_BYTES:
            self.dependencies.logger.warning(
                f"企业微信图片补发跳过: {name} - 图片 {len(raw)} 字节，超过 2MB 上限"
            )
            return
        if not raw.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")):
            self.dependencies.logger.warning(
                f"企业微信图片补发跳过: {name} - 只支持 JPG/PNG"
            )
            return

        data = {
            "msgtype": "image",
            "image": {
                "base64": image_base64,
                "md5": hashlib.md5(raw).hexdigest(),
            },
        }
        try:
            async with self.dependencies.http_factory(
                **_webhook_client_kwargs(url, proxy)
            ) as client:
                response = await client.post(url=url, json=data, headers=headers)
        except Exception as e:
            self.dependencies.logger.warning(
                f"企业微信图片补发失败: {name} - {type(e).__name__}"
            )
            return
        if not response.is_success:
            self.dependencies.logger.warning(
                f"企业微信图片补发失败: {name} - HTTP {response.status_code}"
            )
            return
        failure = webhook_body_failure(response.text, url)
        if failure is not None:
            self.dependencies.logger.warning(
                f"企业微信图片补发失败: {name} - 服务端拒绝 {failure}"
            )
            return
        self.dependencies.logger.success(f"企业微信图片补发成功: {name}")
