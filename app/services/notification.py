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
v4.4
作者：DLmaster_361
"""

import re
import smtplib
import time
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Union

import requests
from PySide6.QtCore import QObject, Signal

from plyer import notification

from app.core import Config, logger
from app.utils.security import Crypto
from app.utils.ImageUtils import ImageUtils


class Notification(QObject):

    push_info_bar = Signal(str, str, str, int)

    def __init__(self, parent=None):
        super().__init__(parent)

    def push_plyer(self, title, message, ticker, t) -> bool:
        """
        推送系统通知

        :param title: 通知标题
        :param message: 通知内容
        :param ticker: 通知横幅
        :param t: 通知持续时间
        :return: bool
        """

        if Config.get(Config.notify_IfPushPlyer):

            logger.info(f"推送系统通知：{title}", module="通知服务")

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

    def send_mail(self, mode, title, content, to_address) -> None:
        """
        推送邮件通知

        :param mode: 邮件内容模式，支持 "文本" 和 "网页"
        :param title: 邮件标题
        :param content: 邮件内容
        :param to_address: 收件人地址
        """

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
                    to_address,
                )
            )
        ):
            logger.error(
                "请正确设置邮件通知的SMTP服务器地址、授权码、发件人地址和收件人地址",
                module="通知服务",
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
                (Header("AUTO_MAA用户", "utf-8").encode(), to_address)
            )  # 收件人显示的名字
            message["Subject"] = Header(title, "utf-8")

            if mode == "网页":
                message.attach(MIMEText(content, "html", "utf-8"))

            smtpObj = smtplib.SMTP_SSL(Config.get(Config.notify_SMTPServerAddress), 465)
            smtpObj.login(
                Config.get(Config.notify_FromAddress),
                Crypto.win_decryptor(Config.get(Config.notify_AuthorizationCode)),
            )
            smtpObj.sendmail(
                Config.get(Config.notify_FromAddress), to_address, message.as_string()
            )
            smtpObj.quit()
            logger.success(f"邮件发送成功：{title}", module="通知服务")
        except Exception as e:
            logger.exception(f"发送邮件时出错：{e}", module="通知服务")
            self.push_info_bar.emit("error", "发送邮件时出错", f"{e}", -1)

    def ServerChanPush(
        self, title, content, send_key, tag, channel
    ) -> Union[bool, str]:
        """
        使用Server酱推送通知

        :param title: 通知标题
        :param content: 通知内容
        :param send_key: Server酱的SendKey
        :param tag: 通知标签
        :param channel: 通知频道
        :return: bool or str
        """

        if not send_key:
            logger.error("请正确设置Server酱的SendKey", module="通知服务")
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

            tags = "|".join(_.strip() for _ in tag.split("|"))
            channels = "|".join(_.strip() for _ in channel.split("|"))

            options = {}
            if is_valid(tags):
                options["tags"] = tags
            else:
                logger.warning("Server酱 Tag 配置不正确，将被忽略", module="通知服务")
                self.push_info_bar.emit(
                    "warning",
                    "Server酱通知推送异常",
                    "请正确设置 ServerChan 的 Tag",
                    -1,
                )

            if is_valid(channels):
                options["channel"] = channels
            else:
                logger.warning(
                    "Server酱 Channel 配置不正确，将被忽略", module="通知服务"
                )
                self.push_info_bar.emit(
                    "warning",
                    "Server酱通知推送异常",
                    "请正确设置 ServerChan 的 Channel",
                    -1,
                )

            # 请求发送
            params = {"title": title, "desp": content, **options}
            headers = {"Content-Type": "application/json;charset=utf-8"}

            response = requests.post(
                url,
                json=params,
                headers=headers,
                timeout=10,
                proxies={
                    "http": Config.get(Config.update_ProxyAddress),
                    "https": Config.get(Config.update_ProxyAddress),
                },
            )
            result = response.json()

            if result.get("code") == 0:
                logger.success(f"Server酱推送通知成功：{title}", module="通知服务")
                return True
            else:
                error_code = result.get("code", "-1")
                logger.exception(
                    f"Server酱通知推送失败：响应码：{error_code}", module="通知服务"
                )
                self.push_info_bar.emit(
                    "error", "Server酱通知推送失败", f"响应码：{error_code}", -1
                )
                return f"Server酱通知推送失败：{error_code}"

        except Exception as e:
            logger.exception(f"Server酱通知推送异常：{e}", module="通知服务")
            self.push_info_bar.emit(
                "error",
                "Server酱通知推送异常",
                "请检查相关设置和网络连接。如全部配置正确，请稍后再试。",
                -1,
            )
            return f"Server酱通知推送异常：{str(e)}"

    def CompanyWebHookBotPush(self, title, content, webhook_url) -> Union[bool, str]:
        """
        使用企业微信群机器人推送通知

        :param title: 通知标题
        :param content: 通知内容
        :param webhook_url: 企业微信群机器人的WebHook地址
        :return: bool or str
        """

        if webhook_url == "":
            logger.error("请正确设置企业微信群机器人的WebHook地址", module="通知服务")
            self.push_info_bar.emit(
                "error",
                "企业微信群机器人通知推送异常",
                "请正确设置企业微信群机器人的WebHook地址",
                -1,
            )
            return None

        content = f"{title}\n{content}"
        data = {"msgtype": "text", "text": {"content": content}}

        for _ in range(3):
            try:
                response = requests.post(
                    url=webhook_url,
                    json=data,
                    timeout=10,
                    proxies={
                        "http": Config.get(Config.update_ProxyAddress),
                        "https": Config.get(Config.update_ProxyAddress),
                    },
                )
                info = response.json()
                break
            except Exception as e:
                err = e
                time.sleep(0.1)
        else:
            logger.error(f"推送企业微信群机器人时出错：{err}", module="通知服务")
            self.push_info_bar.emit(
                "error",
                "企业微信群机器人通知推送失败",
                f"使用企业微信群机器人推送通知时出错：{err}",
                -1,
            )
            return None

        if info["errcode"] == 0:
            logger.success(f"企业微信群机器人推送通知成功：{title}", module="通知服务")
            return True
        else:
            logger.error(f"企业微信群机器人推送通知失败：{info}", module="通知服务")
            self.push_info_bar.emit(
                "error",
                "企业微信群机器人通知推送失败",
                f"使用企业微信群机器人推送通知时出错：{err}",
                -1,
            )
            return f"使用企业微信群机器人推送通知时出错：{err}"

    def CompanyWebHookBotPushImage(self, image_path: Path, webhook_url: str) -> bool:
        """
        使用企业微信群机器人推送图片通知

        :param image_path: 图片文件路径
        :param webhook_url: 企业微信群机器人的WebHook地址
        :return: bool
        """

        try:
            # 压缩图片
            ImageUtils.compress_image_if_needed(image_path)

            # 检查图片是否存在
            if not image_path.exists():
                logger.error(
                    "图片推送异常 | 图片不存在或者压缩失败，请检查图片路径是否正确",
                    module="通知服务",
                )
                self.push_info_bar.emit(
                    "error",
                    "企业微信群机器人通知推送异常",
                    "图片不存在或者压缩失败，请检查图片路径是否正确",
                    -1,
                )
                return False

            if not webhook_url:
                logger.error(
                    "请正确设置企业微信群机器人的WebHook地址", module="通知服务"
                )
                self.push_info_bar.emit(
                    "error",
                    "企业微信群机器人通知推送异常",
                    "请正确设置企业微信群机器人的WebHook地址",
                    -1,
                )
                return False

            # 获取图片base64和md5
            try:
                image_base64 = ImageUtils.get_base64_from_file(str(image_path))
                image_md5 = ImageUtils.calculate_md5_from_file(str(image_path))
            except Exception as e:
                logger.exception(f"图片编码或MD5计算失败：{e}", module="通知服务")
                self.push_info_bar.emit(
                    "error",
                    "企业微信群机器人通知推送异常",
                    f"图片编码或MD5计算失败：{e}",
                    -1,
                )
                return False

            data = {
                "msgtype": "image",
                "image": {"base64": image_base64, "md5": image_md5},
            }

            for _ in range(3):
                try:
                    response = requests.post(
                        url=webhook_url,
                        json=data,
                        timeout=10,
                        proxies={
                            "http": Config.get(Config.update_ProxyAddress),
                            "https": Config.get(Config.update_ProxyAddress),
                        },
                    )
                    info = response.json()
                    break
                except requests.RequestException as e:
                    err = e
                    logger.exception(
                        f"推送企业微信群机器人图片第{_+1}次失败：{e}", module="通知服务"
                    )
                    time.sleep(0.1)
            else:
                logger.error("推送企业微信群机器人图片时出错", module="通知服务")
                self.push_info_bar.emit(
                    "error",
                    "企业微信群机器人图片推送失败",
                    f"使用企业微信群机器人推送图片时出错：{err}",
                    -1,
                )
                return False

            if info.get("errcode") == 0:
                logger.success(
                    f"企业微信群机器人推送图片成功：{image_path.name}",
                    module="通知服务",
                )
                return True
            else:
                logger.error(f"企业微信群机器人推送图片失败：{info}", module="通知服务")
                self.push_info_bar.emit(
                    "error",
                    "企业微信群机器人图片推送失败",
                    f"使用企业微信群机器人推送图片时出错：{info}",
                    -1,
                )
                return False

        except Exception as e:
            logger.error(f"推送企业微信群机器人图片时发生未知异常：{e}")
            self.push_info_bar.emit(
                "error",
                "企业微信群机器人图片推送失败",
                f"发生未知异常：{e}",
                -1,
            )
            return False

    def send_test_notification(self):
        """发送测试通知到所有已启用的通知渠道"""

        logger.info("发送测试通知到所有已启用的通知渠道", module="通知服务")

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
                Config.get(Config.notify_ToAddress),
            )

        # 发送Server酱通知
        if Config.get(Config.notify_IfServerChan):
            self.ServerChanPush(
                "AUTO_MAA测试通知",
                "这是 AUTO_MAA 外部通知测试信息。如果你看到了这段内容，说明 AUTO_MAA 的通知功能已经正确配置且可以正常工作！",
                Config.get(Config.notify_ServerChanKey),
                Config.get(Config.notify_ServerChanTag),
                Config.get(Config.notify_ServerChanChannel),
            )

        # 发送企业微信机器人通知
        if Config.get(Config.notify_IfCompanyWebHookBot):
            self.CompanyWebHookBotPush(
                "AUTO_MAA测试通知",
                "这是 AUTO_MAA 外部通知测试信息。如果你看到了这段内容，说明 AUTO_MAA 的通知功能已经正确配置且可以正常工作！",
                Config.get(Config.notify_CompanyWebHookBotUrl),
            )
            Notify.CompanyWebHookBotPushImage(
                Config.app_path / "resources/images/notification/test_notify.png",
                Config.get(Config.notify_CompanyWebHookBotUrl),
            )

        logger.info("测试通知发送完成", module="通知服务")

        return True


Notify = Notification()
