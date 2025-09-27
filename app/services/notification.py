#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361

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
import smtplib
import requests
import json
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Dict, List, Optional

from plyer import notification

from app.core import Config
from app.utils import get_logger, ImageUtils

logger = get_logger("通知服务")


class Notification:

    def __init__(self):
        super().__init__()
        self.webhook_templates = self._init_webhook_templates()

    def _init_webhook_templates(self) -> Dict[str, Dict]:
        """初始化 Webhook 模板"""
        return {
            "企业微信": {
                "name": "企业微信群机器人",
                "description": "企业微信群机器人 Webhook 推送",
                "headers": {"Content-Type": "application/json"},
                "body_template": {
                    "msgtype": "text",
                    "text": {"content": "{title}\n{content}"}
                },
                "image_template": {
                    "msgtype": "image",
                    "image": {"base64": "{image_base64}", "md5": "{image_md5}"}
                },
                "url_example": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
            },
            "钉钉": {
                "name": "钉钉群机器人",
                "description": "钉钉群机器人 Webhook 推送",
                "headers": {"Content-Type": "application/json"},
                "body_template": {
                    "msgtype": "text",
                    "text": {"content": "{title}\n{content}"}
                },
                "url_example": "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
            },
            "飞书": {
                "name": "飞书群机器人",
                "description": "飞书群机器人 Webhook 推送",
                "headers": {"Content-Type": "application/json"},
                "body_template": {
                    "msg_type": "text",
                    "content": {"text": "{title}\n{content}"}
                },
                "url_example": "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_HOOK_ID"
            },
            "Bark": {
                "name": "Bark 推送",
                "description": "Bark iOS 推送服务",
                "headers": {"Content-Type": "application/json"},
                "body_template": {
                    "title": "{title}",
                    "body": "{content}",
                    "sound": "default",
                    "group": "AUTO-MAS"
                },
                "url_example": "https://api.day.app/YOUR_KEY/"
            },
            "Bark_GET": {
                "name": "Bark 推送 (GET方式)",
                "description": "Bark iOS 推送服务 - GET 请求方式",
                "headers": {},
                "body_template": {},
                "method": "GET",
                "url_template": "https://api.day.app/YOUR_KEY/{title}/{content}?sound=default&group=AUTO-MAS",
                "url_example": "https://api.day.app/YOUR_KEY/"
            },
            "Server酱": {
                "name": "Server酱推送",
                "description": "Server酱微信推送服务",
                "headers": {"Content-Type": "application/json"},
                "body_template": {
                    "title": "{title}",
                    "desp": "{content}"
                },
                "url_example": "https://sctapi.ftqq.com/YOUR_SEND_KEY.send"
            },
            "PushPlus": {
                "name": "PushPlus推送",
                "description": "PushPlus 微信推送服务",
                "headers": {"Content-Type": "application/json"},
                "body_template": {
                    "token": "YOUR_TOKEN",
                    "title": "{title}",
                    "content": "{content}",
                    "template": "html"
                },
                "url_example": "http://www.pushplus.plus/send"
            },
            "QQ机器人": {
                "name": "QQ机器人",
                "description": "QQ 机器人推送",
                "headers": {"Content-Type": "application/json"},
                "body_template": {
                    "message": "{title}\n{content}"
                },
                "url_example": "http://your-qq-bot-server/send"
            },
            "Telegram": {
                "name": "Telegram Bot",
                "description": "Telegram 机器人推送",
                "headers": {"Content-Type": "application/json"},
                "body_template": {
                    "chat_id": "YOUR_CHAT_ID",
                    "text": "<b>{title}</b>\n{content}",
                    "parse_mode": "HTML"
                },
                "url_example": "https://api.telegram.org/botYOUR_BOT_TOKEN/sendMessage"
            },
            "Discord": {
                "name": "Discord Webhook",
                "description": "Discord 频道 Webhook 推送",
                "headers": {"Content-Type": "application/json"},
                "body_template": {
                    "content": "**{title}**\n{content}",
                    "username": "AUTO-MAS"
                },
                "url_example": "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"
            },
            "Slack": {
                "name": "Slack Webhook",
                "description": "Slack 频道 Webhook 推送",
                "headers": {"Content-Type": "application/json"},
                "body_template": {
                    "text": "*{title}*\n{content}",
                    "username": "AUTO-MAS"
                },
                "url_example": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
            },
            "Gotify": {
                "name": "Gotify 推送",
                "description": "Gotify 自托管推送服务",
                "headers": {"Content-Type": "application/json"},
                "body_template": {
                    "title": "{title}",
                    "message": "{content}",
                    "priority": 5
                },
                "url_example": "https://your-gotify-server/message?token=YOUR_TOKEN"
            },
            "Ntfy": {
                "name": "Ntfy 推送",
                "description": "Ntfy 推送服务",
                "headers": {"Content-Type": "text/plain"},
                "body_template": "{title}\n{content}",
                "url_example": "https://ntfy.sh/YOUR_TOPIC"
            },
            "自定义": {
                "name": "自定义格式",
                "description": "完全自定义的 Webhook 格式",
                "headers": {"Content-Type": "application/json"},
                "body_template": {
                    "title": "{title}",
                    "content": "{content}",
                    "timestamp": "{timestamp}"
                },
                "url_example": "https://your-custom-webhook-url"
            }
        }

    def get_webhook_templates(self) -> Dict[str, Dict]:
        """获取所有可用的 Webhook 模板"""
        return self.webhook_templates

    async def push_plyer(self, title, message, ticker, t) -> bool:
        """
        推送系统通知

        :param title: 通知标题
        :param message: 通知内容
        :param ticker: 通知横幅
        :param t: 通知持续时间
        :return: bool
        """

        if Config.get("Notify", "IfPushPlyer"):

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

        return True

    async def send_mail(self, mode, title, content, to_address) -> None:
        """
        推送邮件通知

        :param mode: 邮件内容模式, 支持 "文本" 和 "网页"
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
                "邮件通知的SMTP服务器地址、授权码、发件人地址或收件人地址未正确配置"
            )

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

    async def ServerChanPush(self, title, content, send_key) -> None:
        """
        使用Server酱推送通知

        :param title: 通知标题
        :param content: 通知内容
        :param send_key: Server酱的SendKey
        """

        if not send_key:
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

        response = requests.post(
            url, json=params, headers=headers, timeout=10, proxies=Config.get_proxies()
        )
        result = response.json()

        if result.get("code") == 0:
            logger.success(f"Server酱推送通知成功: {title}")
        else:
            raise Exception(f"ServerChan 推送通知失败: {response.text}")

    async def WebHookPush(self, title, content, webhook_url) -> None:
        """
        WebHook 推送通知

        :param title: 通知标题
        :param content: 通知内容
        :param webhook_url: WebHook地址
        """

        if not webhook_url:
            raise ValueError("WebHook 地址不能为空")

        content = f"{title}\n{content}"
        data = {"msgtype": "text", "text": {"content": content}}

        response = requests.post(
            url=webhook_url, json=data, timeout=10, proxies=Config.get_proxies()
        )
        info = response.json()

        if info["errcode"] == 0:
            logger.success(f"WebHook 推送通知成功: {title}")
        else:
            raise Exception(f"WebHook 推送通知失败: {response.text}")

    async def CompanyWebHookBotPushImage(
        self, image_path: Path, webhook_url: str
    ) -> None:
        """
        使用企业微信群机器人推送图片通知

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

        response = requests.post(
            url=webhook_url, json=data, timeout=10, proxies=Config.get_proxies()
        )
        info = response.json()

        if info.get("errcode") == 0:
            logger.success(f"企业微信群机器人推送图片成功: {image_path.name}")
        else:
            raise Exception(f"企业微信群机器人推送图片失败: {response.text}")

    async def CustomWebhookPush(self, title: str, content: str, webhook_config: Dict) -> None:
        """
        自定义 Webhook 推送通知

        :param title: 通知标题
        :param content: 通知内容
        :param webhook_config: Webhook配置信息
        """
        if not webhook_config.get("url"):
            raise ValueError("Webhook URL 不能为空")

        if not webhook_config.get("enabled", True):
            logger.info(f"Webhook {webhook_config.get('name', 'Unknown')} 已禁用，跳过推送")
            return

        template_type = webhook_config.get("template", "自定义")
        template = self.webhook_templates.get(template_type, self.webhook_templates["自定义"])

        # 获取请求方法
        method = template.get("method", "POST").upper()
        
        # 设置请求头
        headers = webhook_config.get("headers", template.get("headers", {}))

        # 添加时间戳
        import time
        timestamp = str(int(time.time()))
        
        try:
            if method == "GET" and template.get("url_template"):
                # 使用 URL 模板的 GET 请求（如 Bark GET 方式）
                url_template = template["url_template"]
                # URL 编码标题和内容
                import urllib.parse
                encoded_title = urllib.parse.quote(title)
                encoded_content = urllib.parse.quote(content)
                
                # 替换 URL 模板中的变量
                final_url = webhook_config["url"]
                if not final_url.endswith('/'):
                    final_url += '/'
                final_url += f"{encoded_title}/{encoded_content}"
                
                # 添加查询参数
                if "?" in url_template:
                    query_part = url_template.split("?", 1)[1]
                    query_part = query_part.replace("{title}", encoded_title).replace("{content}", encoded_content)
                    final_url += f"?{query_part}"
                
                response = requests.get(
                    url=final_url,
                    headers=headers,
                    timeout=10,
                    proxies=Config.get_proxies()
                )
            else:
                # POST 请求
                # 使用自定义模板或默认模板
                if webhook_config.get("body_template"):
                    try:
                        body_template = json.loads(webhook_config["body_template"])
                    except json.JSONDecodeError:
                        body_template = template.get("body_template", {})
                else:
                    body_template = template.get("body_template", {})

                # 处理不同的数据类型
                if isinstance(body_template, dict):
                    # JSON 格式
                    body_str = json.dumps(body_template)
                    body_str = body_str.replace("{title}", title).replace("{content}", content).replace("{timestamp}", timestamp)
                    data = json.loads(body_str)
                    
                    response = requests.post(
                        url=webhook_config["url"],
                        json=data,
                        headers=headers,
                        timeout=10,
                        proxies=Config.get_proxies()
                    )
                else:
                    # 纯文本格式（如 Ntfy）
                    body_str = str(body_template)
                    body_str = body_str.replace("{title}", title).replace("{content}", content).replace("{timestamp}", timestamp)
                    
                    response = requests.post(
                        url=webhook_config["url"],
                        data=body_str,
                        headers=headers,
                        timeout=10,
                        proxies=Config.get_proxies()
                    )
            
            # 检查响应
            if response.status_code in [200, 201, 204]:
                # 尝试解析JSON响应
                try:
                    result = response.json()
                    # 企业微信/钉钉等返回格式检查
                    if "errcode" in result:
                        if result["errcode"] == 0:
                            logger.success(f"自定义Webhook推送成功: {webhook_config.get('name', 'Unknown')} - {title}")
                        else:
                            raise Exception(f"Webhook推送失败: {result}")
                    elif "code" in result and result["code"] != 200:
                        raise Exception(f"Webhook推送失败: {result}")
                    else:
                        logger.success(f"自定义Webhook推送成功: {webhook_config.get('name', 'Unknown')} - {title}")
                except json.JSONDecodeError:
                    # 非JSON响应，但状态码成功认为推送成功
                    logger.success(f"自定义Webhook推送成功: {webhook_config.get('name', 'Unknown')} - {title}")
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")

        except Exception as e:
            logger.error(f"自定义Webhook推送失败 {webhook_config.get('name', 'Unknown')}: {str(e)}")
            raise

    async def CustomWebhookPushImage(self, image_path: Path, webhook_config: Dict) -> None:
        """
        自定义 Webhook 推送图片通知

        :param image_path: 图片文件路径
        :param webhook_config: Webhook配置信息
        """
        if not webhook_config.get("url"):
            raise ValueError("Webhook URL 不能为空")

        if not webhook_config.get("enabled", True):
            logger.info(f"Webhook {webhook_config.get('name', 'Unknown')} 已禁用，跳过推送")
            return

        template_type = webhook_config.get("template", "自定义")
        template = self.webhook_templates.get(template_type, self.webhook_templates["自定义"])

        # 只有支持图片的模板才处理图片推送
        if "image_template" not in template:
            logger.warning(f"Webhook模板 {template_type} 不支持图片推送")
            return

        # 压缩图片
        ImageUtils.compress_image_if_needed(image_path)

        # 检查图片是否存在
        if not image_path.exists():
            raise FileNotFoundError(f"文件未找到: {image_path}")

        # 获取图片base64和md5
        image_base64 = ImageUtils.get_base64_from_file(str(image_path))
        image_md5 = ImageUtils.calculate_md5_from_file(str(image_path))

        # 替换模板中的变量
        body_template = template["image_template"]
        body_str = json.dumps(body_template)
        body_str = body_str.replace("{image_base64}", image_base64).replace("{image_md5}", image_md5)
        data = json.loads(body_str)

        # 设置请求头
        headers = webhook_config.get("headers", template["headers"])

        try:
            response = requests.post(
                url=webhook_config["url"],
                json=data,
                headers=headers,
                timeout=10,
                proxies=Config.get_proxies()
            )

            if response.status_code == 200:
                try:
                    result = response.json()
                    if "errcode" in result:
                        if result["errcode"] == 0:
                            logger.success(f"自定义Webhook图片推送成功: {webhook_config.get('name', 'Unknown')} - {image_path.name}")
                        else:
                            raise Exception(f"Webhook图片推送失败: {result}")
                    else:
                        logger.success(f"自定义Webhook图片推送成功: {webhook_config.get('name', 'Unknown')} - {image_path.name}")
                except json.JSONDecodeError:
                    logger.success(f"自定义Webhook图片推送成功: {webhook_config.get('name', 'Unknown')} - {image_path.name}")
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")

        except Exception as e:
            logger.error(f"自定义Webhook图片推送失败 {webhook_config.get('name', 'Unknown')}: {str(e)}")
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

        # 发送WebHook通知
        if Config.get("Notify", "IfCompanyWebHookBot"):
            await self.WebHookPush(
                "AUTO-MAS测试通知",
                "这是 AUTO-MAS 外部通知测试信息。如果你看到了这段内容, 说明 AUTO-MAS 的通知功能已经正确配置且可以正常工作！",
                Config.get("Notify", "CompanyWebHookBotUrl"),
            )
            await self.CompanyWebHookBotPushImage(
                Path.cwd() / "res/images/notification/test_notify.png",
                Config.get("Notify", "CompanyWebHookBotUrl"),
            )

        # 发送自定义Webhook通知
        custom_webhooks = Config.get("Notify", "CustomWebhooks", [])
        for webhook in custom_webhooks:
            if webhook.get("enabled", True):
                try:
                    await self.CustomWebhookPush(
                        "AUTO-MAS测试通知",
                        "这是 AUTO-MAS 外部通知测试信息。如果你看到了这段内容, 说明 AUTO-MAS 的通知功能已经正确配置且可以正常工作！",
                        webhook
                    )
                    # 如果支持图片推送，也测试图片
                    if webhook.get("template") in ["企业微信"]:
                        await self.CustomWebhookPushImage(
                            Path.cwd() / "res/images/notification/test_notify.png",
                            webhook
                        )
                except Exception as e:
                    logger.error(f"自定义Webhook测试失败 {webhook.get('name', 'Unknown')}: {str(e)}")

        logger.success("测试通知发送完成")

    async def send_notification_to_all_channels(self, title: str, content: str, user_config: Optional[Dict] = None, image_path: Optional[Path] = None) -> None:
        """
        发送通知到所有已启用的通知渠道

        :param title: 通知标题
        :param content: 通知内容
        :param user_config: 用户特定配置（可选）
        :param image_path: 图片路径（可选）
        """
        
        # 使用用户配置或全局配置
        notify_config = user_config.get("Notify", {}) if user_config else {}
        
        # 发送系统通知
        if Config.get("Notify", "IfPushPlyer"):
            try:
                await self.push_plyer(title, content, title, 5)
            except Exception as e:
                logger.error(f"系统通知发送失败: {str(e)}")

        # 发送邮件通知
        if notify_config.get("IfSendMail") or (not user_config and Config.get("Notify", "IfSendMail")):
            try:
                to_address = notify_config.get("ToAddress") or Config.get("Notify", "ToAddress")
                if to_address:
                    await self.send_mail("文本", title, content, to_address)
            except Exception as e:
                logger.error(f"邮件通知发送失败: {str(e)}")

        # 发送Server酱通知
        if notify_config.get("IfServerChan") or (not user_config and Config.get("Notify", "IfServerChan")):
            try:
                server_chan_key = notify_config.get("ServerChanKey") or Config.get("Notify", "ServerChanKey")
                if server_chan_key:
                    await self.ServerChanPush(title, content, server_chan_key)
            except Exception as e:
                logger.error(f"Server酱通知发送失败: {str(e)}")

        # 发送企业微信Webhook通知
        if notify_config.get("IfCompanyWebHookBot") or (not user_config and Config.get("Notify", "IfCompanyWebHookBot")):
            try:
                webhook_url = notify_config.get("CompanyWebHookBotUrl") or Config.get("Notify", "CompanyWebHookBotUrl")
                if webhook_url:
                    await self.WebHookPush(title, content, webhook_url)
                    if image_path and image_path.exists():
                        await self.CompanyWebHookBotPushImage(image_path, webhook_url)
            except Exception as e:
                logger.error(f"企业微信Webhook通知发送失败: {str(e)}")

        # 发送自定义Webhook通知
        custom_webhooks = notify_config.get("CustomWebhooks", [])
        if not custom_webhooks and not user_config:
            custom_webhooks = Config.get("Notify", "CustomWebhooks", [])
        
        for webhook in custom_webhooks:
            if webhook.get("enabled", True):
                try:
                    await self.CustomWebhookPush(title, content, webhook)
                    # 如果支持图片推送且有图片
                    if image_path and image_path.exists() and webhook.get("template") in ["企业微信"]:
                        await self.CustomWebhookPushImage(image_path, webhook)
                except Exception as e:
                    logger.error(f"自定义Webhook通知发送失败 {webhook.get('name', 'Unknown')}: {str(e)}")


Notify = Notification()
