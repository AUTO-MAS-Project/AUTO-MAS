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


import re

from app.utils.platform.secret import (
    dpapi_decrypt,
    dpapi_encrypt,
    looks_like_dpapi_blob,
)

__all__ = [
    "sanitize_log_message",
    "format_exception_reason",
    "dpapi_encrypt",
    "dpapi_decrypt",
    "looks_like_dpapi_blob",
]


# 推送地址里的密钥。httpx 按 INFO 记下每个请求的完整 URL，这些 URL 会进 app.log 与
# Runtime 抓下来的后端输出，再随问题包、日志压缩包被发出去。上面那组按参数名匹配的规则
# 管不到它们：企业微信群机器人的 ``key=``、Server 酱 SendKey 与飞书、Discord 等 Webhook
# 的令牌都在路径里。前端问题包导出（frontend/electron/services/issueReportCore.ts）有同一组规则，
# 给已经落盘的旧日志打码，两边一起改。
# 值只认 URL 里的字符，碰到逗号、中文、引号就停，别把后面的正文一起打掉。
_URL_VALUE = r"[A-Za-z0-9_.~%+/=-]+"
_URL_SEGMENT = r"[A-Za-z0-9_.~%+=-]+"
_URL_SECRET_PATTERNS = [
    # 企业微信群机器人 ?key=、钉钉加签 &sign=、Server 酱 ?sendkey=、PushDeer ?pushkey=、
    # WxPusher ?appToken=、Power Automate &sig=；JSON 里的 & 会转义成 &
    (
        re.compile(
            rf"((?:[?&]|\\u0026)(?:key|sendkey|sign|sig|pushkey|apptoken)=){_URL_VALUE}",
            re.IGNORECASE,
        ),
        r"\1***",
    ),
    # Server 酱：(sc|sctapi).ftqq.com/<SendKey>.send、<uid>.push.ft07.com/send/<SendKey>.send
    (
        re.compile(
            rf"((?:(?:sc|sctapi)\.ftqq\.com|\.push\.ft07\.com/send)/){_URL_SEGMENT}(\.send)",
            re.IGNORECASE,
        ),
        r"\1***\2",
    ),
    # 路径最后一段就是令牌的：飞书 / Lark（新旧两版）、Discord（可带 API 版本号）、
    # Telegram（令牌带冒号）、Bark、PushPlus、Qmsg、WxPusher 的 SPT、IFTTT
    *[
        (re.compile(prefix + rest, re.IGNORECASE), r"\1***")
        for prefix, rest in [
            (
                r"(open\.(?:feishu\.cn|larksuite\.com)/open-apis/bot/(?:v2/)?hook/)",
                _URL_SEGMENT,
            ),
            (
                rf"(discord(?:app)?\.com/api/(?:v\d+/)?webhooks/{_URL_SEGMENT}/)",
                _URL_SEGMENT,
            ),
            (r"(api\.telegram\.org/bot)", r"[A-Za-z0-9_:-]+"),
            (r"(api\.day\.app/)", _URL_SEGMENT),
            (r"(pushplus\.plus/send/)", _URL_SEGMENT),
            (r"(qmsg\.zendee\.cn/(?:j?send|j?group)/)", _URL_SEGMENT),
            (r"(wxpusher\.zjiecode\.com/api/send/message/)", _URL_SEGMENT),
            (r"(maker\.ifttt\.com/trigger/[^/\s]+/(?:json/)?with/key/)", _URL_SEGMENT),
        ]
    ],
    # Slack：hooks.slack.com/services/<T>/<B>/<secret>
    (
        re.compile(r"(hooks\.slack\.com/services/)[A-Za-z0-9_/-]+", re.IGNORECASE),
        r"\1***",
    ),
]


def sanitize_log_message(message: str) -> str:
    """
    从日志消息中移除敏感信息

    :param message: 原始日志消息
    :type message: str
    :return: 过滤后的日志消息
    :rtype: str
    """
    # 定义需要过滤的敏感参数模式，兼容 URL、表单和 JSON 日志格式。
    sensitive_key = (
        r"(?:cdk|password|passwd|pwd|token|access[_-]?token|"
        r"refresh[_-]?token|authorization|cookies?[_-]?str|cookie|"
        r"secret|api[_-]?key|username|phone|cellphone|useridentity)"
    )
    sensitive_patterns = [
        # JSON 字符串值，例如 "password": "..."
        (rf"([\"']{sensitive_key}[\"']\s*:\s*[\"'])(.*?)([\"'])", r"\1***\3"),
        # JSON 数字、布尔或未加引号值，例如 "uid": ...（仅匹配敏感 key）
        (rf"([\"']{sensitive_key}[\"']\s*:\s*)(?![\"'])([^,}}\]]+)", r"\1***"),
        # URL、表单和普通日志中的 key=value
        (rf"(\b{sensitive_key}\b\s*=\s*)([^&\s,}}\]]+)", r"\1***"),
        # 请求头或字典中的 key: value
        (rf"(\b{sensitive_key}\b\s*:\s*)([^\r\n,}}\]]+)", r"\1***"),
    ]

    sanitized_message = message
    for pattern, replacement in sensitive_patterns:
        sanitized_message = re.sub(
            pattern, replacement, sanitized_message, flags=re.IGNORECASE
        )
    return _mask_url_secrets(sanitized_message)


def _mask_url_secrets(message: str) -> str:
    """只套推送地址那组规则（与前端 issueReportCore.ts 的 maskUrlSecrets 逐条对应）。"""

    for url_pattern, replacement in _URL_SECRET_PATTERNS:
        message = url_pattern.sub(replacement, message)
    return message


def format_exception_reason(
    error: BaseException,
    *,
    stage: str,
    include_message: bool = True,
) -> str:
    """生成不为空且不包含 URL 查询参数的异常原因。"""

    exception_name = type(error).__name__
    message = sanitize_log_message(str(error).strip()) if include_message else ""
    message = re.sub(
        r"(https?://[^\s?#]+)[?#][^\s]*",
        r"\1",
        message,
        flags=re.IGNORECASE,
    )
    if not message:
        if "timeout" in exception_name.lower():
            message = "请求超时"
        elif include_message:
            message = "未提供异常详情"
        else:
            message = "程序内部异常"
    return f"{stage}（{exception_name}）：{message}"
