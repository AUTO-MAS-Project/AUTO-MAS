#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""星铁普通模式（Vulkan）要的客体驱动补丁，逻辑照搬 aemu-lab ``tools/guest/khrfix.py``。

API 34 镜像的 ``/vendor/lib64/libvulkan_enc.so`` 里，``vkUpdateDescriptorSetWithTemplateKHR`` 的两个
入口直接调原始编码器，原始编码器把无类型的 ``pData`` 当 1 个字节发出去，宿主收不到描述符；星铁
（Unity 的 Vulkan 模式）拿没写过的描述符画图，NVIDIA 显卡出错。核心入口走
``ResourceTracker::on_vkUpdateDescriptorSetWithTemplate``，会把模板数据线性化后发出去；两者签名相同，
所以把两个 KHR 入口各改成一条 5 字节的 ``jmp`` 跳到核心入口。

改好的库只在用户电脑上从镜像自带的那份生成（**不分发**）：原库哈希对不上就不改。
"""

from __future__ import annotations

import hashlib
import struct

from .constants import (
    VULKAN_ENC_CORE_ENTRY,
    VULKAN_ENC_FIX_SHA256,
    VULKAN_ENC_ORIG_SHA256,
    VULKAN_ENC_PATCHES,
    VULKAN_ENC_TEXT_DELTA,
)

#: 镜像版本不对时给用户看的话。
UNSUPPORTED_IMAGE_MESSAGE = "这个镜像版本不支持星铁普通模式"


class VulkanFixError(RuntimeError):
    """补丁打不了（库不是预期的那个版本）。消息直接给用户看。"""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_vulkan_encoder(original: bytes) -> bytes:
    """返回改好的库。原库哈希、函数开头字节、改完的哈希任一对不上就抛 :class:`VulkanFixError`。"""
    digest = sha256(original)
    if digest != VULKAN_ENC_ORIG_SHA256:
        raise VulkanFixError(
            f"{UNSUPPORTED_IMAGE_MESSAGE}（客体驱动库哈希 {digest[:12]}…，不是预期版本）"
        )
    data = bytearray(original)
    for address, prologue_hex, name in VULKAN_ENC_PATCHES:
        offset = address - VULKAN_ENC_TEXT_DELTA
        prologue = bytes.fromhex(prologue_hex)
        if bytes(data[offset : offset + len(prologue)]) != prologue:
            raise VulkanFixError(f"{UNSUPPORTED_IMAGE_MESSAGE}（{name} 开头字节不符）")
        relative = VULKAN_ENC_CORE_ENTRY - (address + 5)
        data[offset : offset + 5] = b"\xe9" + struct.pack("<i", relative)
    patched = bytes(data)
    if sha256(patched) != VULKAN_ENC_FIX_SHA256:
        raise VulkanFixError(f"{UNSUPPORTED_IMAGE_MESSAGE}（改完的库哈希不符）")
    return patched


__all__ = [
    "UNSUPPORTED_IMAGE_MESSAGE",
    "VulkanFixError",
    "patch_vulkan_encoder",
    "sha256",
]
