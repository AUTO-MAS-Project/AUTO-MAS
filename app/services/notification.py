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

"""
AUTO_MAA
AUTO_MAA通知服务
v4.3
作者：DLmaster_361
"""

import re
import smtplib
import time
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import requests
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget
from loguru import logger
from plyer import notification

from app.core import Config
from app.services.security import Crypto


class Notification(QWidget):

    push_info_bar = Signal(str, str, str, int)

    def __init__(self, parent=None):
        super().__init__(parent)

    def push_plyer(self, title, message, ticker, t):
        """推送系统通知"""

        if Config.get(Config.notify_IfPushPlyer):

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

        if Config.get(Config.notify_IfSendMail):

            if (
                Config.get(Config.notify_SMTPServerAddress) == ""
                or Config.get(Config.notify_AuthorizationCode) == ""
                or not bool(
                    re.match(
                        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                        Config.get(Config.notify_FromAddress),
                    )
                )
                or not bool(
                    re.match(
                        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                        Config.get(Config.notify_ToAddress),
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
                        Config.get(Config.notify_FromAddress),
                    )
                )  # 发件人显示的名字
                message["To"] = formataddr(
                    (
                        Header("AUTO_MAA用户", "utf-8").encode(),
                        Config.get(Config.notify_ToAddress),
                    )
                )  # 收件人显示的名字
                message["Subject"] = Header(title, "utf-8")

                if mode == "网页":
                    message.attach(MIMEText(content, "html", "utf-8"))

                smtpObj = smtplib.SMTP_SSL(
                    Config.get(Config.notify_SMTPServerAddress),
                    465,
                )
                smtpObj.login(
                    Config.get(Config.notify_FromAddress),
                    Crypto.win_decryptor(Config.get(Config.notify_AuthorizationCode)),
                )
                smtpObj.sendmail(
                    Config.get(Config.notify_FromAddress),
                    Config.get(Config.notify_ToAddress),
                    message.as_string(),
                )
                smtpObj.quit()
                logger.success("邮件发送成功")
            except Exception as e:
                logger.error(f"发送邮件时出错：\n{e}")
                self.push_info_bar.emit("error", "发送邮件时出错", f"{e}", -1)

    def ServerChanPush(self, title, content):
        """使用Server酱推送通知（支持 tag 和 channel，避免使用SDK）"""
        if Config.get(Config.notify_IfServerChan):
            send_key = Config.get(Config.notify_ServerChanKey)

            if not send_key:
                logger.error("请正确设置Server酱的SendKey")
                self.push_info_bar.emit(
                    "error", "Server酱通知推送异常", "请正确设置Server酱的SendKey", -1
                )
                return None

            try:
                # 构造 URL
                if send_key.startswith("sctp"):
                    match = re.match(r"^sctp(\d+)t", send_key)
                    if match:
                        url = f"https://{match.group(1)}.push.ft07.com/send/{send_key}.send"
                    else:
                        raise ValueError("SendKey 格式错误（sctp）")
                else:
                    url = f"https://sctapi.ftqq.com/{send_key}.send"

                # 构建 tags 和 channel
                def is_valid(s):
                    return s == "" or (
                        s == "|".join(s.split("|"))
                        and (s.count("|") == 0 or all(s.split("|")))
                    )

                tags = "|".join(
                    _.strip()
                    for _ in Config.get(Config.notify_ServerChanTag).split("|")
                )
                channels = "|".join(
                    _.strip()
                    for _ in Config.get(Config.notify_ServerChanChannel).split("|")
                )

                options = {}
                if is_valid(tags):
                    options["tags"] = tags
                else:
                    logger.warning("Server酱 Tag 配置不正确，将被忽略")
                    self.push_info_bar.emit(
                        "warning",
                        "Server酱通知推送异常",
                        "请正确设置 ServerChan 的 Tag",
                        -1,
                    )

                if is_valid(channels):
                    options["channel"] = channels
                else:
                    logger.warning("Server酱 Channel 配置不正确，将被忽略")
                    self.push_info_bar.emit(
                        "warning",
                        "Server酱通知推送异常",
                        "请正确设置 ServerChan 的 Channel",
                        -1,
                    )

                # 请求发送
                params = {"title": title, "desp": content, **options}
                headers = {"Content-Type": "application/json;charset=utf-8"}

                response = requests.post(url, json=params, headers=headers, timeout=10)
                result = response.json()

                if result.get("code") == 0:
                    logger.info("Server酱推送通知成功")
                    return True
                else:
                    error_code = result.get("code", "-1")
                    logger.error(f"Server酱通知推送失败：响应码：{error_code}")
                    self.push_info_bar.emit(
                        "error", "Server酱通知推送失败", f"响应码：{error_code}", -1
                    )
                    return f"Server酱通知推送失败：{error_code}"

            except Exception as e:
                logger.exception("Server酱通知推送异常")
                self.push_info_bar.emit(
                    "error", "Server酱通知推送异常", f"请检查相关设置，如还有问题可联系开发者", -1
                )
                return f"Server酱通知推送异常：{str(e)}"

    def CompanyWebHookBotPush(self, title, content):
        """使用企业微信群机器人推送通知"""
        if Config.get(Config.notify_IfCompanyWebHookBot):

            if Config.get(Config.notify_CompanyWebHookBotUrl) == "":
                logger.error("请正确设置企业微信群机器人的WebHook地址")
                self.push_info_bar.emit(
                    "error",
                    "企业微信群机器人通知推送异常",
                    "请正确设置企业微信群机器人的WebHook地址",
                    -1,
                )
                return None

            content = f"{title}\n{content}"
            data = {"msgtype": "text", "text": {"content": content}}
            # 从远程服务器获取最新主题图像
            for _ in range(3):
                try:
                    response = requests.post(
                        url=Config.get(Config.notify_CompanyWebHookBotUrl),
                        json=data,
                        timeout=10,
                    )
                    info = response.json()
                    break
                except Exception as e:
                    err = e
                    time.sleep(0.1)
            else:
                logger.error(f"推送企业微信群机器人时出错：{err}")
                self.push_info_bar.emit(
                    "error",
                    "企业微信群机器人通知推送失败",
                    f'使用企业微信群机器人推送通知时出错：{info["errmsg"]}',
                    -1,
                )
                return None

            if info["errcode"] == 0:
                logger.info("企业微信群机器人推送通知成功")
                return True
            else:
                logger.error(f"企业微信群机器人推送通知失败：{info}")
                self.push_info_bar.emit(
                    "error",
                    "企业微信群机器人通知推送失败",
                    f'使用企业微信群机器人推送通知时出错：{info["errmsg"]}',
                    -1,
                )
                return f'使用企业微信群机器人推送通知时出错：{info["errmsg"]}'

    def send_test_notification(self):
        """发送测试通知到所有已启用的通知渠道"""
        # 发送系统通知
        self.push_plyer(
            "测试通知",
            "这是 AUTO_MAA 外部通知测试信息。如果你看到了这段内容，说明 AUTO_MAA 的通知功能已经正确配置且可以正常工作！",
            "测试通知",
            3,
        )

        # 发送邮件通知
        if Config.get(Config.notify_IfSendMail):
            self.send_mail(
                "文本",
                "AUTO_MAA测试通知",
                "这是 AUTO_MAA 外部通知测试信息。如果你看到了这段内容，说明 AUTO_MAA 的通知功能已经正确配置且可以正常工作！",
            )

        # 发送Server酱通知
        if Config.get(Config.notify_IfServerChan):
            self.ServerChanPush(
                "AUTO_MAA测试通知",
                "这是 AUTO_MAA 外部通知测试信息。如果你看到了这段内容，说明 AUTO_MAA 的通知功能已经正确配置且可以正常工作！",
            )

        # 发送企业微信机器人通知
        if Config.get(Config.notify_IfCompanyWebHookBot):
            self.CompanyWebHookBotPush(
                "AUTO_MAA测试通知",
                "这是 AUTO_MAA 外部通知测试信息。如果你看到了这段内容，说明 AUTO_MAA 的通知功能已经正确配置且可以正常工作！",
            )

        return True


class UserNotification:
    """用户单独通知服务"""

    def __init__(self, user_config):
        self.config = user_config

    def send_notification(self, title: str, content: str) -> bool:
        """发送用户通知"""
        logger.info(f"单独通知-准备发送用户通知，标题: {title}")

        if not self.config.get(self.config.Notify_Enable):
            logger.warning("单独通知-用户通知功能未启用，跳过发送")
            return False

        success = False

        # 邮件通知
        if self._check_smtp_config():
            try:
                self._send_email(title, content)
                success = True
            except Exception as e:
                logger.error(f"单独通知-发送邮件通知失败: {str(e)}")

        # Server酱通知
        if (
            self.config.get(self.config.Notify_IfServerChan)
            and self._check_serverchan_config()
        ):
            try:
                self._send_serverchan(title, content)
                success = True
            except Exception as e:
                logger.error(f"单独通知-发送 Server酱 通知失败: {str(e)}")

        # 企业微信群机器人
        if (
            self.config.get(self.config.Notify_IfCompanyWebHookBot)
            and self._check_webhook_config()
        ):
            try:
                self._send_webhook(title, content)
                success = True
            except Exception as e:
                logger.error(f"单独通知-发送企业微信机器人通知失败: {str(e)}")

        if success:
            logger.info("单独通知-用户通知发送完成")
        else:
            logger.warning("单独通知-所有通知方式均发送失败")

        return success

    def _check_smtp_config(self) -> bool:
        """检查SMTP配置是否完整"""
        return all([
            self.config.get(self.config.Notify_IfSMTP),
            self.config.get(self.config.Notify_SMTPServerAddress),
            self.config.get(self.config.Notify_AuthorizationCode),
            self.config.get(self.config.Notify_FromAddress),
            self.config.get(self.config.Notify_ToAddress)
        ])

    def _check_serverchan_config(self) -> bool:
        """检查ServerChan配置是否完整"""
        return bool(self.config.get(self.config.Notify_ServerChanKey))

    def _check_webhook_config(self) -> bool:
        """检查企业微信机器人配置是否完整"""
        return bool(self.config.get(self.config.Notify_CompanyWebHookBotUrl))

    def _send_email(self, title: str, content: str):
        """发送邮件通知"""
        logger.debug("单独通知-开始发送邮件通知")
        import smtplib
        from email.mime.text import MIMEText
        from email.header import Header

        msg = MIMEText(content, 'plain', 'utf-8')
        msg['Subject'] = Header(title, 'utf-8')
        msg['From'] = self.config.get(self.config.Notify_FromAddress)
        msg['To'] = self.config.get(self.config.Notify_ToAddress)

        server = smtplib.SMTP_SSL(self.config.get(self.config.Notify_SMTPServerAddress))
        server.login(
            self.config.get(self.config.Notify_FromAddress),
            self.config.get(self.config.Notify_AuthorizationCode)
        )
        server.send_message(msg)
        server.quit()
        logger.success("单独通知-邮件通知发送成功")

    def _send_serverchan(self, title: str, content: str):
        """发送 ServerChan 通知，支持 SCT、SC3、自定义域名等"""
        logger.debug("单独通知-开始发送 ServerChan 通知")
        import requests
        import re

        key = self.config.get(self.config.Notify_ServerChanKey)
        tag = self.config.get(self.config.Notify_ServerChanTag)
        channel = self.config.get(self.config.Notify_ServerChanChannel)

        if not key:
            raise Exception("ServerChan SendKey 未设置")

        # 1. 构造 URL（支持 sctpN 和 sct 开头的）
        if key.startswith("sctp"):
            match = re.match(r"^sctp(\d+)t", key)
            if match:
                url = f"https://{match.group(1)}.push.ft07.com/send/{key}.send"
            else:
                raise ValueError("SendKey 格式错误，sctp 开头但不符合规范")
        else:
            url = f"https://sctapi.ftqq.com/{key}.send"

        logger.debug(f"单独通知-Server酱推送URL: {url}")

        # 2. 校验 tag 和 channel 格式
        def is_valid(s):
            return s == "" or (
                s == "|".join(s.split("|")) and (s.count("|") == 0 or all(s.split("|")))
            )

        tags = "|".join([_.strip() for _ in tag.split("|")]) if tag else ""
        channels = "|".join([_.strip() for _ in channel.split("|")]) if channel else ""

        options = {}
        if is_valid(tags):
            options["tags"] = tags
        else:
            logger.warning("单独通知-ServerChan Tag 格式不正确，已忽略")

        if is_valid(channels):
            options["channel"] = channels
        else:
            logger.warning("单独通知-ServerChan Channel 格式不正确，已忽略")

        # 3. 构造 payload
        payload = {"title": title, "desp": content, **options}

        headers = {"Content-Type": "application/json;charset=utf-8"}
        logger.info(f"单独通知-发送 Server酱通知: {payload}")

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            result = response.json()

            if result.get("code") == 0:
                logger.success("Server酱通知推送成功")
            else:
                raise Exception(
                    f"推送失败，响应码：{result.get('code')}, 信息：{result}"
                )
        except Exception as e:
            raise Exception(f"Server酱推送失败: {e}")

    def _send_webhook(self, title: str, content: str):
        """发送企业微信机器人通知"""
        logger.debug("单独通知-开始发送企业微信机器人通知")
        import requests

        url = self.config.get(self.config.Notify_CompanyWebHookBotUrl)
        data = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"### {title}\n{content}"
            }
        }

        response = requests.post(url, json=data)
        if response.status_code != 200:
            raise Exception(f"企业微信机器人API返回错误: {response.text}")
        logger.success("单独通知-企业微信机器人通知发送成功")


Notify = Notification()
