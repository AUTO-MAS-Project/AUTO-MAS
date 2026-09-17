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


import asyncio
import ipaddress
import json
import re
import smtplib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from email.header import Header
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Literal
from urllib.parse import urlparse

import httpx

from app.models.config import Webhook
from app.models.schema import WSSystemNoticeData
from app.utils import LazyProxy, get_logger
from app.utils.constants import UTC4

logger = get_logger("通知服务")

# 延迟加载 Config 与 WS 发布器，避免 app.services 初始化期间触发 app.core 循环导入
Config = LazyProxy("app.core", "Config")
Publisher = LazyProxy("app.core.ws", "Publisher")
protocol = LazyProxy("app.core.ws", "protocol")

SMTP_TIMEOUT_SECONDS = 15
DEFAULT_WEBHOOK_TEMPLATE = '{"title": "{title}", "content": "{content}"}'
# OneBot 图片段里的占位写法，前端预设与这里必须一致。
WEBHOOK_IMAGE_PLACEHOLDER = "base64://{image_base64}"


@dataclass(frozen=True)
class MailInlineImage:
    """随网页邮件一起发送的内嵌图片，正文用 ``<img src="cid:{cid}">`` 引用。

    走 ``multipart/related`` + Content-ID，而不是把 base64 直接写进 ``<img src>``：
    data URI 在 QQ 邮箱、Gmail、Outlook 里都会被拦掉，六星喜报以前就是这么
    失效的（c8d3c41e6 改成了外链）。
    """

    cid: str
    data: bytes
    subtype: str = "png"


def webhook_body_failure(text: str, url: str = "") -> str | None:
    """从 HTTP 2xx 的响应体里识别机器人平台的业务失败。

    钉钉、企业微信自定义机器人被关键词/签名校验拦下、飞书 token 无效、OneBot
    动作失败时都回 200，只在 JSON 里写 ``errcode`` / ``code`` / ``status``；
    只看状态码会把这些记成「推送成功」，用户以为通知没发。识别出失败时返回
    平台给的原因，正常或看不懂的响应返回 None。
    """

    if not text:
        return None
    try:
        body = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(body, dict):
        return None

    def _reason(*keys: str) -> str:
        for key in keys:
            value = body.get(key)
            if value:
                return str(value)
        return text[:200]

    # 钉钉 / 企业微信：成功一律 errcode 0。
    errcode = body.get("errcode")
    if isinstance(errcode, int) and not isinstance(errcode, bool) and errcode != 0:
        return f"errcode={errcode} {_reason('errmsg', 'msg')}"
    # OneBot v11：status 为 failed 才算失败，retcode 只是补充。
    if str(body.get("status", "")).lower() == "failed":
        return f"retcode={body.get('retcode')} {_reason('msg', 'message', 'wording')}"
    # 飞书：只在飞书域名下解读 code，别的服务常拿 code=200 当成功。
    host = (urlparse(url).hostname or "").lower()
    if host.endswith(("feishu.cn", "larksuite.com")):
        code = body.get("code")
        if isinstance(code, int) and not isinstance(code, bool) and code != 0:
            return f"code={code} {_reason('msg', 'message')}"
    return None


def _webhook_client_kwargs(url: str) -> dict:
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
    return {"timeout": 10, "proxy": Config.proxy}


def _is_webhook_image_placeholder(obj: object) -> bool:
    """是不是 OneBot 预设里那段 ``base64://{image_base64}`` 图片。"""

    return (
        isinstance(obj, dict)
        and obj.get("type") == "image"
        and isinstance(obj.get("data"), dict)
        and obj["data"].get("file") == WEBHOOK_IMAGE_PLACEHOLDER
    )


class Notification:
    async def push_plyer(self, title: str, message: str, ticker: str, t: int) -> None:
        """
        推送系统通知

        改由前端转交 Electron 主进程以系统原生通知弹出（Windows 为 Toast，
        可进通知中心），不再走会占用托盘图标的托盘气泡。

        Parameters
        ----------
        title: str
            通知标题
        message: str
            通知内容
        ticker: str
            兼容保留，已无效果（旧托盘气泡的横幅文本）
        t: int
            兼容保留，已无效果（横幅时长由系统通知设置决定）
        """

        if not Config.get("Notify", "IfPushPlyer"):
            return

        logger.info(f"推送系统通知: {title}")

        await Publisher.send(
            id=protocol.ID_MAIN,
            type=protocol.SYSTEM_NOTICE,
            data=WSSystemNoticeData(title=title, message=message),
        )

    async def send_mail(
        self,
        mode: Literal["文本", "网页"],
        title: str,
        content: str,
        to_address: str,
        *,
        images: Sequence[MailInlineImage] = (),
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
        images: Sequence[MailInlineImage], optional
            网页模式下随信内嵌的图片；文本模式忽略
        """

        if Config.get("Notify", "SMTPServerAddress") == "":
            raise ValueError("邮件通知的SMTP服务器地址不能为空")
        if Config.get("Notify", "AuthorizationCode") == "":
            raise ValueError("邮件通知的授权码不能为空")
        if not bool(
            re.match(
                r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                Config.get("Notify", "FromAddress"),
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

        # 定义邮件正文
        if mode == "文本":
            message = MIMEText(content, "plain", "utf-8")
        elif mode == "网页" and images:
            message = MIMEMultipart("related")
        elif mode == "网页":
            message = MIMEMultipart("alternative")
        message["From"] = formataddr(
            (
                Header("AUTO-MAS通知服务", "utf-8").encode(),
                Config.get("Notify", "FromAddress"),
            )
        )  # 发件人显示的名字
        message["To"] = formataddr(
            (Header("AUTO-MAS用户", "utf-8").encode(), to_address)
        )  # 收件人显示的名字
        message["Subject"] = str(Header(title, "utf-8"))

        if mode == "网页":
            message.attach(MIMEText(content, "html", "utf-8"))
            for image in images:
                part = MIMEImage(image.data, _subtype=image.subtype)
                part.add_header("Content-ID", f"<{image.cid}>")
                part.add_header(
                    "Content-Disposition",
                    "inline",
                    filename=f"{image.cid}.{image.subtype}",
                )
                message.attach(part)

        smtp_server = Config.get("Notify", "SMTPServerAddress")
        from_address = Config.get("Notify", "FromAddress")
        authorization_code = Config.get("Notify", "AuthorizationCode")

        def send() -> None:
            with smtplib.SMTP_SSL(
                smtp_server,
                465,
                timeout=SMTP_TIMEOUT_SECONDS,
            ) as smtp_obj:
                smtp_obj.login(from_address, authorization_code)
                smtp_obj.sendmail(from_address, to_address, message.as_string())

        await asyncio.to_thread(send)
        logger.success(f"邮件发送成功: {title}")

    async def ServerChanPush(self, title: str, content: str, send_key: str) -> None:
        """
        使用Server酱推送通知

        Parameters
        ----------
        title: str
            通知标题
        content: str
            通知内容
        send_key: str
            Server酱的SendKey
        """

        if send_key == "":
            raise ValueError("ServerChan SendKey 不能为空")

        # 构造 URL
        if send_key.startswith("sctp"):
            match = re.match(r"^sctp(\d+)t", send_key)
            if match:
                url = f"https://{match.group(1)}.push.ft07.com/send/{send_key}.send"
            else:
                raise ValueError("SendKey 格式不正确 (sctp<int>)")
        else:
            url = f"https://sctapi.ftqq.com/{send_key}.send"

        # 请求发送
        params = {"title": title, "desp": content}
        headers = {"Content-Type": "application/json;charset=utf-8"}

        async with httpx.AsyncClient(proxy=Config.proxy) as client:
            response = await client.post(url, json=params, headers=headers)
            result = response.json()

        if result.get("code") == 0:
            logger.success(f"Server酱推送通知成功: {title}")
        else:
            raise Exception(f"ServerChan 推送通知失败: {response.text}")

    async def send_cmcc_newmsg(self, title: str, content: str, api_key: str) -> None:
        """通过中国移动新消息（5G 消息）提交通知。"""

        from app.services.cmcc_newmsg import send_cmcc_newmsg

        await send_cmcc_newmsg(
            api_key=api_key,
            content=content,
            proxy=Config.proxy,
        )
        logger.success(f"中国移动5G短信通知已提交: {title}")

    async def send_openclaw_weixin(self, title: str, content: str) -> None:
        """通过微信 Claw 通道推送通知。

        登录凭据和会话上下文由扫码登录管理器维护，通知层不读取或暴露协议
        细节；长文本拆分、业务错误和上下文失效也由管理器统一处理。

        Args:
            title: 通知标题。
            content: 已渲染的通知正文。

        Raises:
            ValueError: 尚未绑定微信账号时抛出。
            RuntimeError: 网关返回 HTTP 或业务错误时抛出。
        """
        from app.services.openclaw_weixin import openclaw_weixin_manager

        await openclaw_weixin_manager.send(title=title, content=content)

    async def send_openclaw_qq(self, title: str, content: str) -> None:
        """通过 QQ 官方机器人通道推送通知。

        登录凭据由扫码登录管理器维护，通知层不读取或暴露协议细节；长文本
        拆分、业务错误和访问令牌刷新也由管理器统一处理。

        Args:
            title: 通知标题。
            content: 已渲染的通知正文。

        Raises:
            ValueError: 尚未绑定 QQ 官方机器人时抛出。
            RuntimeError: 官方接口返回 HTTP 或业务错误时抛出。
        """
        from app.services.openclaw_qq import openclaw_qq_manager

        await openclaw_qq_manager.send(title=title, content=content)

    async def WebhookPush(
        self,
        title: str,
        content: str,
        webhook: Webhook,
        *,
        image_base64: str = "",
    ) -> None:
        """
        Webhook 推送通知

        Parameters
        ----------
        title: str
            通知标题
        content: str
            通知内容
        webhook: Webhook
            Webhook配置对象
        image_base64: str, optional
            可选图片的纯 Base64 数据，供 OneBot 等协议使用
        """
        if not webhook.get("Info", "Enabled"):
            return

        if webhook.get("Data", "Url") == "":
            raise ValueError("Webhook URL 不能为空")

        # 解析模板
        template = webhook.get("Data", "Template") or DEFAULT_WEBHOOK_TEMPLATE

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

            logger.debug("开始解析 Webhook 消息模板")

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
                logger.debug("Webhook JSON 模板解析成功")

            except json.JSONDecodeError:
                # 如果不是有效的JSON，作为字符串模板处理
                logger.debug("模板不是有效JSON，作为字符串模板处理")
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
                    logger.debug("Webhook 字符串模板已解析为 JSON")
                except json.JSONDecodeError:
                    # 最终作为纯文本发送
                    data = formatted_template
                    logger.debug("Webhook 模板将作为纯文本发送")

        except Exception as e:
            logger.warning(f"模板解析失败，使用默认格式: {e}")
            data = {"title": title, "content": content}

        # 准备请求头
        headers = {"Content-Type": "application/json"}
        headers.update(json.loads(webhook.get("Data", "Headers")))

        url = webhook.get("Data", "Url")

        async with httpx.AsyncClient(**_webhook_client_kwargs(url)) as client:
            if webhook.get("Data", "Method") == "POST":
                if isinstance(data, dict):
                    response = await client.post(url=url, json=data, headers=headers)
                elif isinstance(data, str):
                    response = await client.post(url=url, content=data, headers=headers)
            elif webhook.get("Data", "Method") == "GET":
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
            raise Exception(
                f"[{webhook.get('Info', 'Name')}] HTTP {response.status_code}: {response.text}"
            )
        failure = webhook_body_failure(response.text, url)
        if failure is not None:
            raise Exception(f"[{webhook.get('Info', 'Name')}] 服务端拒绝: {failure}")
        logger.success(
            f"自定义Webhook推送成功: {webhook.get('Info', 'Name')} - {title}"
        )

    async def send_koishi(
        self,
        message: str,
        msgtype: str = "text",
        client_name: str = "Koishi",
    ) -> bool:
        """
        通过 WebSocket 推送消息到 Koishi AUTO-MAS 插件

        Args:
            message (str): 消息内容。
            msgtype (str): 消息类型，可选 "text"、"html"、"picture"，默认 "text"。
            client_name (str): WebSocket 客户端名称，默认 "Koishi"。

        Returns:
            bool: 发送是否成功。
        """
        from app.utils.websocket import ws_client_manager

        # 获取 WebSocket 客户端
        client = ws_client_manager.get_client(client_name)
        if not client:
            logger.error(
                f"Koishi 通知推送失败: 未找到名为 [{client_name}] 的 WebSocket 客户端"
            )
            return False

        if not client.is_connected:
            logger.error(
                f"Koishi 通知推送失败: WebSocket 客户端 [{client_name}] 未连接"
            )
            return False

        # 构造通知消息
        notify_message = {
            "id": "Client",
            "type": "notify",
            "data": {
                "msgtype": msgtype,
                "message": message,
            },
        }

        # 发送消息
        success = await client.send(notify_message)
        if success:
            logger.success(f"Koishi 通知推送成功: {message[:50]}")
        else:
            logger.error("Koishi 通知推送失败: 发送消息失败")

        return success


Notify = Notification()
