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
from datetime import datetime
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx
from plyer import notification

from app.models.config import Webhook
from app.utils import LazyProxy, get_logger, ImageUtils
from app.utils.constants import UTC4

logger = get_logger("通知服务")

# 延迟加载 Config，避免 app.services 初始化期间触发 app.core 循环导入
Config = LazyProxy("app.core", "Config")

SMTP_TIMEOUT_SECONDS = 15

# Windows 通知最终写入 NOTIFYICONDATA 的定长字段：标题落在 szInfoTitle（64 个
# UTF-16 代码单元）、正文落在 szInfo（256 个）。plyer 直接把字符串塞进 ctypes 定长
# 数组，超长会抛 ValueError，且各留一位给结尾空字符，因此推送前先截断。
PLYER_TITLE_LIMIT = 63
PLYER_MESSAGE_LIMIT = 255


def clip_notify_text(text: str, limit: int) -> str:
    """
    按 Windows 通知字段上限截断文本，超出部分以省略号收尾

    ``ctypes.c_wchar`` 数组按 UTF-16 代码单元计数，而 ``len()`` 数的是码位：
    emoji 等非 BMP 字符占 1 个码位却要 2 个代码单元，按码位截断仍会溢出，因此
    这里按编码后的代码单元数裁剪。截断点落在代理对中间时，``errors="ignore"``
    会丢弃残缺的那一半。

    Args:
        text: 待截断的文本
        limit: 目标字段可用的 UTF-16 代码单元数（已扣除结尾空字符）

    Returns:
        str: 编码后不超过 ``limit`` 个 UTF-16 代码单元的文本
    """

    encoded = text.encode("utf-16-le")
    if len(encoded) // 2 <= limit:
        return text

    clipped = encoded[: (limit - 1) * 2].decode("utf-16-le", errors="ignore")

    return f"{clipped}…"


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


class Notification:
    async def push_plyer(self, title: str, message: str, ticker: str, t: int) -> None:
        """
        推送系统通知

        Parameters
        ----------
        title: str
            通知标题
        message: str
            通知内容
        ticker: str
            通知横幅
        t: int
            通知持续时间
        """

        if not Config.get("Notify", "IfPushPlyer"):
            return

        logger.info(f"推送系统通知: {title}")

        if notification.notify is not None:
            await asyncio.to_thread(
                notification.notify,
                title=clip_notify_text(title, PLYER_TITLE_LIMIT),
                message=clip_notify_text(message, PLYER_MESSAGE_LIMIT),
                app_name="AUTO-MAS",
                app_icon=(Path.cwd() / "res/icons/AUTO-MAS.ico").as_posix(),
                timeout=t,
                ticker=ticker,
                toast=True,
            )
        else:
            raise RuntimeError("plyer.notification 未正确导入，无法推送系统通知")

    async def send_mail(
        self, mode: Literal["文本", "网页"], title: str, content: str, to_address: str
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

    async def WebhookPush(self, title: str, content: str, webhook: Webhook) -> None:
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
        """
        if not webhook.get("Info", "Enabled"):
            return

        if webhook.get("Data", "Url") == "":
            raise ValueError("Webhook URL 不能为空")

        # 解析模板
        template = (
            webhook.get("Data", "Template")
            or '{"title": "{title}", "content": "{content}"}'
        )

        # 替换模板变量
        try:
            # 准备模板变量
            template_vars = {
                "title": title,
                "content": content,
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
                        return {k: replace_variables(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
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
        if response.status_code == 200:
            logger.success(
                f"自定义Webhook推送成功: {webhook.get('Info', 'Name')} - {title}"
            )
        else:
            raise Exception(
                f"[{webhook.get('Info', 'Name')}] HTTP {response.status_code}: {response.text}"
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
