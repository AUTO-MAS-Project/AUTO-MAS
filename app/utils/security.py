#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

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
import base64
import win32crypt


def sanitize_log_message(message: str) -> str:
    """
    从日志消息中移除敏感信息

    :param message: 原始日志消息
    :type message: str
    :return: 过滤后的日志消息
    :rtype: str
    """
    # 定义需要过滤的敏感参数模式
    sensitive_patterns = [
        (r"(cdk=)[^&\s]+", r"\1***"),  # cdk参数
        (r"(password=)[^&\s]+", r"\1***"),  # password参数
        (r"(token=)[^&\s]+", r"\1***"),  # token参数
        (r"(api_key=)[^&\s]+", r"\1***"),  # api_key参数
        (r"(secret=)[^&\s]+", r"\1***"),  # secret参数
    ]

    sanitized_message = message
    for pattern, replacement in sensitive_patterns:
        sanitized_message = re.sub(
            pattern, replacement, sanitized_message, flags=re.IGNORECASE
        )

    return sanitized_message


def dpapi_encrypt(
    note: str, description: None | str = None, entropy: None | bytes = None
) -> str:
    """
    使用Windows DPAPI加密数据

    :param note: 数据明文
    :type note: str
    :param description: 描述信息
    :type description: str
    :param entropy: 随机熵
    :type entropy: bytes
    :return: 加密后的数据
    :rtype: str
    """

    if note == "":
        return ""

    encrypted = win32crypt.CryptProtectData(
        note.encode("utf-8"), description, entropy, None, None, 0
    )
    return base64.b64encode(encrypted).decode("utf-8")


def dpapi_decrypt(note: str, entropy: None | bytes = None) -> str:
    """
    使用Windows DPAPI解密数据

    :param note: 数据密文
    :type note: str
    :param entropy: 随机熵
    :type entropy: bytes
    :return: 解密后的明文
    :rtype: str
    """

    if note == "":
        return ""

    decrypted = win32crypt.CryptUnprotectData(
        base64.b64decode(note), entropy, None, None, 0
    )
    return decrypted[1].decode("utf-8")
