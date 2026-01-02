#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 AUTO-MAS Team
import asyncio

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import re
import json
import smtplib
import httpx
from datetime import datetime
from plyer import notification
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Literal

from app.core import Config
from app.models.config import Webhook
from app.utils import get_logger, ImageUtils

logger = get_logger("通知服务")


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
            notification.notify(
                title=title,
                message=message,
                app_name="AUTO-MAS",
                app_icon=(Path.cwd() / "res/icons/AUTO-MAS.ico").as_posix(),
                timeout=t,
                ticker=ticker,
                toast=True,
            )
        else:
            logger.error("plyer.notification 未正确导入, 无法推送系统通知")

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

        smtpObj = smtplib.SMTP_SSL(Config.get("Notify", "SMTPServerAddress"), 465)
        smtpObj.login(
            Config.get("Notify", "FromAddress"),
            Config.get("Notify", "AuthorizationCode"),
        )
        smtpObj.sendmail(
            Config.get("Notify", "FromAddress"), to_address, message.as_string()
        )
        smtpObj.quit()
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
            }

            logger.debug(f"原始模板: {template}")
            logger.debug(f"模板变量: {template_vars}")

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
                logger.debug(f"成功解析JSON模板: {data}")

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
                    logger.debug(f"字符串模板解析为JSON成功: {data}")
                except json.JSONDecodeError:
                    # 最终作为纯文本发送
                    data = formatted_template
                    logger.debug(f"作为纯文本发送: {data}")

        except Exception as e:
            logger.warning(f"模板解析失败，使用默认格式: {e}")
            data = {"title": title, "content": content}

        # 准备请求头
        headers = {"Content-Type": "application/json"}
        headers.update(json.loads(webhook.get("Data", "Headers")))

        async with httpx.AsyncClient(proxy=Config.proxy, timeout=10) as client:
            if webhook.get("Data", "Method") == "POST":
                if isinstance(data, dict):
                    response = await client.post(
                        url=webhook.get("Data", "Url"), json=data, headers=headers
                    )
                elif isinstance(data, str):
                    response = await client.post(
                        url=webhook.get("Data", "Url"), content=data, headers=headers
                    )
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
                response = await client.get(
                    url=webhook.get("Data", "Url"), params=params, headers=headers
                )

        # 检查响应
        if response.status_code == 200:
            logger.success(
                f"自定义Webhook推送成功: {webhook.get('Info', 'Name')} - {title}"
            )
        else:
            raise Exception(f"HTTP {response.status_code}: {response.text}")

    async def _WebHookPush(self, title, content, webhook_url) -> None:
        """
        WebHook 推送通知 (即将弃用)

        :param title: 通知标题
        :param content: 通知内容
        :param webhook_url: WebHook地址
        """

        if not webhook_url:
            raise ValueError("WebHook 地址不能为空")

        content = f"{title}\n{content}"
        data = {"msgtype": "text", "text": {"content": content}}

        async with httpx.AsyncClient(proxy=Config.proxy) as client:
            response = await client.post(url=webhook_url, json=data)
            info = response.json()

        if info["errcode"] == 0:
            logger.success(f"WebHook 推送通知成功: {title}")
        else:
            raise Exception(f"WebHook 推送通知失败: {response.text}")

    async def CompanyWebHookBotPushImage(
        self, image_path: Path, webhook_url: str
    ) -> None:
        """
        使用企业微信群机器人推送图片通知（等待重新适配）

        :param image_path: 图片文件路径
        :param webhook_url: 企业微信群机器人的WebHook地址
        """

        if not webhook_url:
            raise ValueError("webhook URL 不能为空")

        # 压缩图片
        ImageUtils.compress_image_if_needed(image_path)

        # 检查图片是否存在
        if not image_path.exists():
            raise FileNotFoundError(f"文件未找到: {image_path}")

        # 获取图片base64和md5
        image_base64 = ImageUtils.get_base64_from_file(str(image_path))
        image_md5 = ImageUtils.calculate_md5_from_file(str(image_path))

        data = {
            "msgtype": "image",
            "image": {"base64": image_base64, "md5": image_md5},
        }

        async with httpx.AsyncClient(proxy=Config.proxy) as client:
            response = await client.post(url=webhook_url, json=data)
            info = response.json()

        if info.get("errcode") == 0:
            logger.success(f"企业微信群机器人推送图片成功: {image_path.name}")
        else:
            raise Exception(f"企业微信群机器人推送图片失败: {response.text}")

    async def send_koishi(
        self,
        message: str,
        token: str,
        target: str = "admin",
        msgtype: str = "text",
        base_url: str = "http://localhost:5140/AUTO_MAS",
    ) -> dict:
        """
        推送消息到 Koishi AUTO-MAS 插件

        Args:
            message (str): 消息内容。
            token (str): API 访问令牌。
            target (str): 发送目标，默认 "admin"。
            msgtype (str): 消息类型，可选 "text"、"html"、"picture"。
            base_url (str): API 端点地址。

        Returns:
            dict: API 响应结果。

        Raises:
            httpx.RequestError: 网络请求失败时抛出。
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        payload = {"user_id": target, "msgtype": msgtype, "message": message}

        async with httpx.AsyncClient(timeout=10) as client:
            try:
                response = await client.post(base_url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()

                if result.get("success"):
                    logger.success(f"Koishi 通知推送成功: {message[:50]}")
                else:
                    logger.error(f"Koishi 通知推送失败: {result.get('message')}")

                return result
            except httpx.RequestError as e:
                logger.error(f"Koishi 通知请求失败: {str(e)}")
                raise

    async def send_test_notification(self) -> None:
        """发送测试通知到所有已启用的通知渠道"""

        logger.info("发送测试通知到所有已启用的通知渠道")

        # 发送系统通知
        await self.push_plyer(
            "测试通知",
            "这是 AUTO-MAS 外部通知测试信息。如果你看到了这段内容, 说明 AUTO-MAS 的通知功能已经正确配置且可以正常工作！",
            "测试通知",
            3,
        )

        # 发送邮件通知
        if Config.get("Notify", "IfSendMail"):
            await self.send_mail(
                "文本",
                "AUTO-MAS测试通知",
                "这是 AUTO-MAS 外部通知测试信息。如果你看到了这段内容, 说明 AUTO-MAS 的通知功能已经正确配置且可以正常工作！",
                Config.get("Notify", "ToAddress"),
            )

        # 发送Server酱通知
        if Config.get("Notify", "IfServerChan"):
            await self.ServerChanPush(
                "AUTO-MAS测试通知",
                "这是 AUTO-MAS 外部通知测试信息。如果你看到了这段内容, 说明 AUTO-MAS 的通知功能已经正确配置且可以正常工作！",
                Config.get("Notify", "ServerChanKey"),
            )

        # 发送自定义Webhook通知
        for webhook in Config.Notify_CustomWebhooks.values():
            await self.WebhookPush(
                "AUTO-MAS测试通知",
                "这是 AUTO-MAS 外部通知测试信息。如果你看到了这段内容, 说明 AUTO-MAS 的通知功能已经正确配置且可以正常工作！",
                webhook,
            )

        # 发送Koishi通知
        if Config.get("Notify", "IfSendKoishi"):
            await self.send_koishi(
                "这是 AUTO-MAS 外部通知测试信息。如果你看到了这段内容, 说明 AUTO-MAS 的通知功能已经正确配置且可以正常工作！",
                Config.get("Notify", "KoishiToken"),
            )

        logger.success("测试通知发送完成")


if __name__ == "__main__":
    Notify = Notification()
    response = asyncio.run(
        Notify.send_koishi(
            "hello",
            "123456",
        )
    )
Notify = Notification()
