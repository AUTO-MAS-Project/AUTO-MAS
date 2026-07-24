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


import base64
import binascii
import re
from dataclasses import dataclass

import win32crypt


DPAPI_APPLICATION_ENTROPY = b"top.auto-mas.frontend/configuration/dpapi/v1"
"""AUTO-MAS 配置密文使用的稳定应用绑定 entropy。

DPAPI 的 optional entropy 不是秘密；这里用它隔离同一 Windows 用户下由
其他应用创建的 DPAPI blob。显式传入 ``entropy=None`` 仅用于读取或构造
历史 AUTO-MAS 密文。
"""

DPAPI_CONFIG_PREFIX = "DPAPI:v1:"
"""AUTO-MAS 当前配置密文封装版本。"""

DPAPI_LEGACY_CONFIG_PREFIX = "DPAPI:"
"""Config v2 实验版本曾使用的无版本前缀。"""

_DPAPI_BLOB_HEADER = bytes.fromhex(
    "01000000d08c9ddf0115d1118c7a00c04fc297eb"
)


class DPAPIProtectionError(RuntimeError):
    """DPAPI 保护或解保护失败，错误文本不携带明文或密文。"""


@dataclass(frozen=True, slots=True, repr=False)
class DPAPIDecryptionResult:
    """一次 DPAPI 解密结果及其存储迁移状态。"""

    plaintext: str
    needs_migration: bool

    def __repr__(self) -> str:
        """避免结果对象被诊断日志打印时泄漏明文。"""
        return (
            "DPAPIDecryptionResult("
            f"plaintext=***, needs_migration={self.needs_migration!r})"
        )


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
    note: str,
    description: str | None = None,
    entropy: bytes | None = DPAPI_APPLICATION_ENTROPY,
) -> str:
    """
    使用 Windows DPAPI 加密数据。

    默认使用 AUTO-MAS 应用绑定 entropy。只有兼容测试或显式历史数据工具
    才应传入 ``entropy=None``。

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

    try:
        protected = win32crypt.CryptProtectData(
            note.encode("utf-8"), description, entropy, None, None, 0
        )
    except Exception:
        raise DPAPIProtectionError(
            "DPAPI configuration value encryption failed"
        ) from None

    encrypted = protected[1] if isinstance(protected, tuple) else protected
    if not isinstance(encrypted, bytes):
        raise DPAPIProtectionError(
            "DPAPI configuration value encryption returned invalid data"
        )
    return base64.b64encode(encrypted).decode("ascii")


def _decode_dpapi_blob(note: str) -> bytes:
    """严格解码一个 Base64 DPAPI blob，不在异常中携带输入。"""
    if not isinstance(note, str):
        raise DPAPIProtectionError(
            "DPAPI encrypted configuration value must be a string"
        )
    try:
        return base64.b64decode(note, validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError):
        raise DPAPIProtectionError(
            "DPAPI encrypted configuration value is not valid Base64"
        ) from None


def is_probable_dpapi_ciphertext(note: str) -> bool:
    """判断字符串是否带有标准 Windows DPAPI blob 头。

    历史 AUTO-MAS 配置没有外层格式标签。该检查用于区分需要首次加密的
    明文与已经损坏、因而必须 fail-closed 的 DPAPI 密文。
    """
    if not isinstance(note, str):
        return False
    if note.startswith(DPAPI_LEGACY_CONFIG_PREFIX):
        return True
    try:
        encrypted = base64.b64decode(note, validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError):
        return False
    return encrypted.startswith(_DPAPI_BLOB_HEADER)


def _dpapi_decrypt_exact(encrypted: bytes, entropy: bytes | None) -> str:
    """使用指定 entropy 解密；不实施兼容回退。"""
    try:
        unprotected = win32crypt.CryptUnprotectData(
            encrypted, entropy, None, None, 0
        )
        decrypted = unprotected[1] if isinstance(unprotected, tuple) else unprotected
        if not isinstance(decrypted, bytes):
            raise TypeError
        return decrypted.decode("utf-8")
    except Exception:
        raise DPAPIProtectionError(
            "DPAPI encrypted configuration value cannot be decrypted"
        ) from None


def dpapi_decrypt_with_status(
    note: str,
    entropy: bytes | None = DPAPI_APPLICATION_ENTROPY,
) -> DPAPIDecryptionResult:
    """解密 DPAPI 密文并返回是否需要从历史 entropy 迁移。

    默认先使用应用绑定 entropy。仅当该尝试失败时，才回退到历史
    ``entropy=None``；成功回退会以 ``needs_migration=True`` 明确报告给
    持久化层。传入自定义 entropy（包括显式 ``None``）时不进行回退。
    """
    if note == "":
        return DPAPIDecryptionResult("", needs_migration=False)

    encrypted = _decode_dpapi_blob(note)
    try:
        plaintext = _dpapi_decrypt_exact(encrypted, entropy)
    except DPAPIProtectionError:
        if entropy != DPAPI_APPLICATION_ENTROPY:
            raise
        plaintext = _dpapi_decrypt_exact(encrypted, None)
        return DPAPIDecryptionResult(plaintext, needs_migration=True)

    return DPAPIDecryptionResult(plaintext, needs_migration=False)


def dpapi_decrypt(
    note: str,
    entropy: bytes | None = DPAPI_APPLICATION_ENTROPY,
) -> str:
    """
    使用 Windows DPAPI 解密数据。

    默认兼容读取历史 ``entropy=None`` 密文。需要审计迁移状态的持久化
    调用方应使用 :func:`dpapi_decrypt_with_status`。

    :param note: 数据密文
    :type note: str
    :param entropy: 随机熵
    :type entropy: bytes
    :return: 解密后的明文
    :rtype: str
    """

    return dpapi_decrypt_with_status(note, entropy).plaintext


def encrypt_config_value(note: str) -> str:
    """使用当前版本封装和应用 entropy 加密一个配置字符串。"""
    if note == "":
        return ""
    return DPAPI_CONFIG_PREFIX + dpapi_encrypt(note)


def decrypt_config_value_with_status(note: str) -> DPAPIDecryptionResult:
    """解密当前或历史 AUTO-MAS 配置密文并报告格式迁移需求。

    支持三种输入：

    - ``DPAPI:v1:<blob>``：当前格式，只接受应用 entropy；
    - ``DPAPI:<blob>``：历史 Config v2 格式；
    - ``<blob>``：历史 ``ConfigBase`` 裸 DPAPI 格式。

    两种无版本历史格式无论底层使用 application entropy 还是
    ``entropy=None``，读取成功后都需要重写为当前格式。
    """
    if note == "":
        return DPAPIDecryptionResult("", needs_migration=False)

    if note.startswith(DPAPI_CONFIG_PREFIX):
        encoded = note[len(DPAPI_CONFIG_PREFIX) :]
        encrypted = _decode_dpapi_blob(encoded)
        plaintext = _dpapi_decrypt_exact(
            encrypted,
            DPAPI_APPLICATION_ENTROPY,
        )
        return DPAPIDecryptionResult(plaintext, needs_migration=False)

    if note.startswith(DPAPI_LEGACY_CONFIG_PREFIX):
        encoded = note[len(DPAPI_LEGACY_CONFIG_PREFIX) :]
    else:
        encoded = note

    plaintext = dpapi_decrypt_with_status(encoded).plaintext
    return DPAPIDecryptionResult(plaintext, needs_migration=True)


def decrypt_config_value(note: str) -> str:
    """解密版本化或历史 AUTO-MAS 配置密文。"""
    return decrypt_config_value_with_status(note).plaintext
