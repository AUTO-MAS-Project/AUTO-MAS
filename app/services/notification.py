#   <AUTO_MAA:A MAA Multi Account Management and Automation Tool>
#   Copyright © <2024> <DLmaster361>

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

#   DLmaster_361@163.com

"""
AUTO_MAA
AUTO_MAA通知服务
v4.2
作者：DLmaster_361
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal
import requests
from loguru import logger
from plyer import notification
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr

from serverchan_sdk import sc_send

from app.core import Config
from app.services.security import Crypto


class Notification(QWidget):

    push_info_bar = Signal(str, str, str, int)

    def __init__(self, parent=None):
        super().__init__(parent)

    def push_plyer(self, title, message, ticker, t):
        """推送系统通知"""

        if Config.global_config.get(Config.global_config.notify_IfPushPlyer):

            notification.notify(
                title=title,
                message=message,
                app_name="AUTO_MAA",
                app_icon=str(Config.app_path / "resources/icons/AUTO_MAA.ico"),
                timeout=t,
                ticker=ticker,
                toast=True,
            )

        return True

    def send_mail(self, mode, title, content) -> None:
        """推送邮件通知"""

        if Config.global_config.get(Config.global_config.notify_IfSendMail):

            if (
                Config.global_config.get(Config.global_config.notify_SMTPServerAddress)
                == ""
                or Config.global_config.get(
                    Config.global_config.notify_AuthorizationCode
                )
                == ""
                or not bool(
                    re.match(
                        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                        Config.global_config.get(
                            Config.global_config.notify_FromAddress
                        ),
                    )
                )
                or not bool(
                    re.match(
                        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                        Config.global_config.get(Config.global_config.notify_ToAddress),
                    )
                )
            ):
                logger.error(
                    "请正确设置邮件通知的SMTP服务器地址、授权码、发件人地址和收件人地址"
                )
                self.push_info_bar.emit(
                    "error",
                    "邮件通知推送异常",
                    "请正确设置邮件通知的SMTP服务器地址、授权码、发件人地址和收件人地址",
                    -1,
                )
                return None

            try:
                # 定义邮件正文
                if mode == "文本":
                    message = MIMEText(content, "plain", "utf-8")
                elif mode == "网页":
                    message = MIMEMultipart("alternative")
                message["From"] = formataddr(
                    (
                        Header("AUTO_MAA通知服务", "utf-8").encode(),
                        Config.global_config.get(
                            Config.global_config.notify_FromAddress
                        ),
                    )
                )  # 发件人显示的名字
                message["To"] = formataddr(
                    (
                        Header("AUTO_MAA用户", "utf-8").encode(),
                        Config.global_config.get(Config.global_config.notify_ToAddress),
                    )
                )  # 收件人显示的名字
                message["Subject"] = Header(title, "utf-8")

                if mode == "网页":
                    message.attach(MIMEText(content, "html", "utf-8"))

                smtpObj = smtplib.SMTP_SSL(
                    Config.global_config.get(
                        Config.global_config.notify_SMTPServerAddress
                    ),
                    465,
                )
                smtpObj.login(
                    Config.global_config.get(Config.global_config.notify_FromAddress),
                    Crypto.win_decryptor(
                        Config.global_config.get(
                            Config.global_config.notify_AuthorizationCode
                        )
                    ),
                )
                smtpObj.sendmail(
                    Config.global_config.get(Config.global_config.notify_FromAddress),
                    Config.global_config.get(Config.global_config.notify_ToAddress),
                    message.as_string(),
                )
                smtpObj.quit()
                logger.success("邮件发送成功")
            except Exception as e:
                logger.error(f"发送邮件时出错：\n{e}")
                self.push_info_bar.emit("error", "发送邮件时出错", f"{e}", -1)

    def ServerChanPush(self, title, content):
        """使用Server酱推送通知"""

        if Config.global_config.get(Config.global_config.notify_IfServerChan):
            send_key = Config.global_config.get(
                Config.global_config.notify_ServerChanKey
            )
            option = {}
            is_valid = lambda s: s == "" or (
                s == "|".join(s.split("|")) and (s.count("|") == 0 or all(s.split("|")))
            )
            """
            is_valid => True, 如果启用的话需要正确设置Tag和Channel。
            允许空的Tag和Channel即不启用，但不允许例如a||b，|a|b，a|b|，||||
            """
            send_tag = Config.global_config.get(
                Config.global_config.notify_ServerChanTag
            )
            send_channel = Config.global_config.get(
                Config.global_config.notify_ServerChanChannel
            )

            if is_valid(send_tag):
                option["tags"] = send_tag
            else:
                option["tags"] = ""
                logger.warning("请正确设置Auto_MAA中ServerChan的Tag。")
                self.push_info_bar.emit(
                    "warning",
                    "Server酱通知推送异常",
                    "请正确设置Auto_MAA中ServerChan的Tag。",
                    -1,
                )

            if is_valid(send_channel):
                option["channel"] = send_channel
            else:
                option["channel"] = ""
                logger.warning("请正确设置Auto_MAA中ServerChan的Channel。")
                self.push_info_bar.emit(
                    "warning",
                    "Server酱通知推送异常",
                    "请正确设置Auto_MAA中ServerChan的Channel。",
                    -1,
                )

            response = sc_send(send_key, title, content, option)
            if response["code"] == 0:
                logger.info("Server酱推送通知成功")
                return True
            else:
                logger.info("Server酱推送通知失败")
                logger.error(response)
                self.push_info_bar.emit(
                    "error",
                    "Server酱通知推送失败",
                    f'使用Server酱推送通知时出错：\n{response["data"]['error']}',
                    -1,
                )
                return f'使用Server酱推送通知时出错：\n{response["data"]['error']}'

    def CompanyWebHookBotPush(self, title, content):
        """使用企业微信群机器人推送通知"""
        if Config.global_config.get(Config.global_config.notify_IfCompanyWebHookBot):
            content = f"{title}\n{content}"
            data = {"msgtype": "text", "text": {"content": content}}
            response = requests.post(
                url=Config.global_config.get(
                    Config.global_config.notify_CompanyWebHookBotUrl
                ),
                json=data,
            )
            if response.json()["errcode"] == 0:
                logger.info("企业微信群机器人推送通知成功")
                return True
            else:
                logger.info("企业微信群机器人推送通知失败")
                logger.error(response.json())
                self.push_info_bar.emit(
                    "error",
                    "企业微信群机器人通知推送失败",
                    f'使用企业微信群机器人推送通知时出错：\n{response.json()["errmsg"]}',
                    -1,
                )
                return (
                    f'使用企业微信群机器人推送通知时出错：\n{response.json()["errmsg"]}'
                )


Notify = Notification()
