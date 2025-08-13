#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import re
import smtplib
import requests
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

from plyer import notification

from app.core import Config
from app.utils import get_logger, ImageUtils

logger = get_logger("通知服务")


class Notification:

    def __init__(self):
        super().__init__()

    def push_plyer(self, title, message, ticker, t) -> bool:
        """
        推送系统通知

        :param title: 通知标题
        :param message: 通知内容
        :param ticker: 通知横幅
        :param t: 通知持续时间
        :return: bool
        """

        if Config.get("Notify", "IfPushPlyer"):

            logger.info(f"推送系统通知：{title}")

            if notification.notify is not None:
                notification.notify(
                    title=title,
                    message=message,
                    app_name="AUTO_MAA",
                    app_icon=(Path.cwd() / "res/icons/AUTO_MAA.ico").as_posix(),
                    timeout=t,
                    ticker=ticker,
                    toast=True,
                )
            else:
                logger.error("plyer.notification 未正确导入，无法推送系统通知")

        return True

    def send_mail(self, mode, title, content, to_address) -> None:
        """
        推送邮件通知

        :param mode: 邮件内容模式，支持 "文本" 和 "网页"
        :param title: 邮件标题
        :param content: 邮件内容
        :param to_address: 收件人地址
        """

        if (
            Config.get("Notify", "SMTPServerAddress") == ""
            or Config.get("Notify", "AuthorizationCode") == ""
            or not bool(
                re.match(
                    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                    Config.get("Notify", "FromAddress"),
                )
            )
            or not bool(
                re.match(
                    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                    to_address,
                )
            )
        ):
            logger.error(
                "请正确设置邮件通知的SMTP服务器地址、授权码、发件人地址和收件人地址"
            )
            raise ValueError(
                "The SMTP server address, authorization code, sender address, or recipient address is not set correctly."
            )

        # 定义邮件正文
        if mode == "文本":
            message = MIMEText(content, "plain", "utf-8")
        elif mode == "网页":
            message = MIMEMultipart("alternative")
        message["From"] = formataddr(
            (
                Header("AUTO_MAA通知服务", "utf-8").encode(),
                Config.get("Notify", "FromAddress"),
            )
        )  # 发件人显示的名字
        message["To"] = formataddr(
            (Header("AUTO_MAA用户", "utf-8").encode(), to_address)
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
        logger.success(f"邮件发送成功：{title}")

    def ServerChanPush(self, title, content, send_key) -> None:
        """
        使用Server酱推送通知

        :param title: 通知标题
        :param content: 通知内容
        :param send_key: Server酱的SendKey
        """

        if not send_key:
            raise ValueError("The ServerChan SendKey can not be empty.")

        # 构造 URL
        if send_key.startswith("sctp"):
            match = re.match(r"^sctp(\d+)t", send_key)
            if match:
                url = f"https://{match.group(1)}.push.ft07.com/send/{send_key}.send"
            else:
                raise ValueError("SendKey format is incorrect (sctp<int>).")
        else:
            url = f"https://sctapi.ftqq.com/{send_key}.send"

        # 请求发送
        params = {"title": title, "desp": content}
        headers = {"Content-Type": "application/json;charset=utf-8"}

        response = requests.post(
            url, json=params, headers=headers, timeout=10, proxies=Config.get_proxies()
        )
        result = response.json()

        if result.get("code") == 0:
            logger.success(f"Server酱推送通知成功：{title}")
        else:
            raise Exception(f"ServerChan failed to send notification: {response.text}")

    def WebHookPush(self, title, content, webhook_url) -> None:
        """
        WebHook 推送通知

        :param title: 通知标题
        :param content: 通知内容
        :param webhook_url: WebHook地址
        """

        if not webhook_url:
            raise ValueError("The webhook URL can not be empty.")

        content = f"{title}\n{content}"
        data = {"msgtype": "text", "text": {"content": content}}

        response = requests.post(
            url=webhook_url, json=data, timeout=10, proxies=Config.get_proxies()
        )
        info = response.json()

        if info["errcode"] == 0:
            logger.success(f"WebHook 推送通知成功：{title}")
        else:
            raise Exception(f"WebHook failed to send notification: {response.text}")

    def CompanyWebHookBotPushImage(self, image_path: Path, webhook_url: str) -> None:
        """
        使用企业微信群机器人推送图片通知

        :param image_path: 图片文件路径
        :param webhook_url: 企业微信群机器人的WebHook地址
        """

        if not webhook_url:
            raise ValueError("The webhook URL can not be empty.")

        # 压缩图片
        ImageUtils.compress_image_if_needed(image_path)

        # 检查图片是否存在
        if not image_path.exists():
            raise FileNotFoundError(f"File not found: {image_path}")

        # 获取图片base64和md5
        image_base64 = ImageUtils.get_base64_from_file(str(image_path))
        image_md5 = ImageUtils.calculate_md5_from_file(str(image_path))

        data = {
            "msgtype": "image",
            "image": {"base64": image_base64, "md5": image_md5},
        }

        response = requests.post(
            url=webhook_url, json=data, timeout=10, proxies=Config.get_proxies()
        )
        info = response.json()

        if info.get("errcode") == 0:
            logger.success(f"企业微信群机器人推送图片成功：{image_path.name}")
        else:
            raise Exception(
                f"Company WebHook Bot failed to send image: {response.text}"
            )

    def send_test_notification(self) -> None:
        """发送测试通知到所有已启用的通知渠道"""

        logger.info("发送测试通知到所有已启用的通知渠道")

        # 发送系统通知
        self.push_plyer(
            "测试通知",
            "这是 AUTO_MAA 外部通知测试信息。如果你看到了这段内容，说明 AUTO_MAA 的通知功能已经正确配置且可以正常工作！",
            "测试通知",
            3,
        )

        # 发送邮件通知
        if Config.get("Notify", "IfSendMail"):
            self.send_mail(
                "文本",
                "AUTO_MAA测试通知",
                "这是 AUTO_MAA 外部通知测试信息。如果你看到了这段内容，说明 AUTO_MAA 的通知功能已经正确配置且可以正常工作！",
                Config.get("Notify", "ToAddress"),
            )

        # 发送Server酱通知
        if Config.get("Notify", "IfServerChan"):
            self.ServerChanPush(
                "AUTO_MAA测试通知",
                "这是 AUTO_MAA 外部通知测试信息。如果你看到了这段内容，说明 AUTO_MAA 的通知功能已经正确配置且可以正常工作！",
                Config.get("Notify", "ServerChanKey"),
            )

        # 发送WebHook通知
        if Config.get("Notify", "IfCompanyWebHookBot"):
            self.WebHookPush(
                "AUTO_MAA测试通知",
                "这是 AUTO_MAA 外部通知测试信息。如果你看到了这段内容，说明 AUTO_MAA 的通知功能已经正确配置且可以正常工作！",
                Config.get("Notify", "CompanyWebHookBotUrl"),
            )
            Notify.CompanyWebHookBotPushImage(
                Path.cwd() / "res/images/notification/test_notify.png",
                Config.get("Notify", "CompanyWebHookBotUrl"),
            )

        logger.success("测试通知发送完成")


Notify = Notification()
