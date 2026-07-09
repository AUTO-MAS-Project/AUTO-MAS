#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""鹰角游戏 config.ini AES-256-CBC 加解密

鹰角 PC 游戏 (明日方舟 PC / 终末地) 的 config.ini 以固定 key/IV 的
AES-256-CBC + PKCS7 加密存储。本模块提供对称加解密, 供
HypergryphPcProvider 读取/回写本地版本号使用。

依赖: pycryptodome (项目已声明依赖, 见 pyproject.toml)。
"""

from __future__ import annotations

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

# 固定密钥与初始向量 (32 字节 key / 16 字节 IV, 来自鹰角启动器)
AES_KEY = bytes(
    [
        0xC0, 0xF3, 0x0E, 0x1C, 0xE7, 0x63, 0xBB, 0xC2,
        0x1C, 0xC3, 0x55, 0xA3, 0x43, 0x03, 0xAC, 0x50,
        0x39, 0x94, 0x44, 0xBF, 0xF6, 0x8C, 0x4A, 0x22,
        0xAF, 0x39, 0x8C, 0x0A, 0x16, 0x6E, 0xE1, 0x43,
    ]
)
AES_IV = bytes(
    [
        0x33, 0x46, 0x78, 0x61, 0x19, 0x27, 0x50, 0x64,
        0x95, 0x01, 0x93, 0x72, 0x64, 0x60, 0x84, 0x00,
    ]
)

# AES 块大小 (字节), PKCS7 填充以块大小对齐
_BLOCK_SIZE = AES.block_size


def decrypt_config_to_str(raw: bytes) -> str:
    """解密 config.ini 原始字节为明文文本

    Args:
        raw: config.ini 的原始加密字节

    Returns:
        解密后的明文 (utf-8), 形如 INI 文本

    Raises:
        ValueError: 数据长度非块整数倍, 或 PKCS7 去填充失败 (密钥/数据错误)
    """
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv=AES_IV)
    decrypted = cipher.decrypt(raw)
    plain = unpad(decrypted, _BLOCK_SIZE)
    return plain.decode("utf-8")


def encrypt_str_to_config(text: str) -> bytes:
    """将明文文本加密为 config.ini 字节

    Args:
        text: 明文文本 (utf-8)

    Returns:
        AES-256-CBC + PKCS7 加密后的字节
    """
    data = text.encode("utf-8")
    padded = pad(data, _BLOCK_SIZE)
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv=AES_IV)
    return cipher.encrypt(padded)
