#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 AUTO-MAS Team

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


from pathlib import Path


from .constants import ENCODINGS, CREATION_FLAGS


def decode_bytes(data: bytes) -> str:
    """
    尝试用多种编码解码 bytes, 全部失败则使用 latin1 保底

    Args:
        data(bytes): 要解码的字节串

    Returns:
        str: 解码后的字符串
    """
    if not data:
        return ""

    for encoding in ENCODINGS:
        try:
            return data.decode(encoding, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        return data.decode("latin1", errors="replace")
