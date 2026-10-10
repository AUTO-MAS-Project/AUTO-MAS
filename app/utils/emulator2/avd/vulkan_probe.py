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

"""独立脚本：列出这台电脑上 Vulkan 能用的显卡，结果按一行 JSON 打到标准输出。

由 :mod:`.precheck` 用 ``python <本文件路径>`` 在子进程里跑，不在后端进程里加载：``vulkan-1.dll``
会把显卡驱动的 ICD 一并装进来，驱动出问题时只崩这个子进程。只用标准库（ctypes），不导入 ``app``。
不改系统、不装东西：只调 Vulkan 加载器的 ``vkCreateInstance`` / ``vkEnumeratePhysicalDevices`` /
``vkGetPhysicalDeviceProperties``。

输出：``{"loaded": bool, "result": int, "devices": [{"name", "type", "apiVersion", "vendorId"}],
"error": str}``。``type`` 是 ``VkPhysicalDeviceType``：0 其他、1 集成显卡、2 独立显卡、3 虚拟显卡、
4 CPU（软件实现，如 SwiftShader / lavapipe）。
"""

from __future__ import annotations

import ctypes
import json
import sys
from ctypes import POINTER, Structure, byref, c_char_p, c_int32, c_uint32, c_void_p

_STRUCTURE_TYPE_APPLICATION_INFO = 0
_STRUCTURE_TYPE_INSTANCE_CREATE_INFO = 1
#: VK_API_VERSION_1_1
_API_VERSION = (1 << 22) | (1 << 12)
#: ``VkPhysicalDeviceProperties`` 实际约 824 字节（含 limits），这里给足；只读开头几个字段。
_PROPERTIES_BUFFER = 4096
_DEVICE_NAME_OFFSET = 20
_DEVICE_NAME_SIZE = 256


class _ApplicationInfo(Structure):
    _fields_ = [
        ("sType", c_int32),
        ("pNext", c_void_p),
        ("pApplicationName", c_char_p),
        ("applicationVersion", c_uint32),
        ("pEngineName", c_char_p),
        ("engineVersion", c_uint32),
        ("apiVersion", c_uint32),
    ]


class _InstanceCreateInfo(Structure):
    _fields_ = [
        ("sType", c_int32),
        ("pNext", c_void_p),
        ("flags", c_uint32),
        ("pApplicationInfo", POINTER(_ApplicationInfo)),
        ("enabledLayerCount", c_uint32),
        ("ppEnabledLayerNames", c_void_p),
        ("enabledExtensionCount", c_uint32),
        ("ppEnabledExtensionNames", c_void_p),
    ]


def _version(raw: int) -> str:
    return f"{(raw >> 22) & 0x7F}.{(raw >> 12) & 0x3FF}.{raw & 0xFFF}"


def probe() -> dict:
    try:
        vulkan = ctypes.WinDLL("vulkan-1.dll") if sys.platform == "win32" else None
    except OSError as e:
        return {"loaded": False, "result": 0, "devices": [], "error": str(e)}
    if vulkan is None:
        return {"loaded": False, "result": 0, "devices": [], "error": "not Windows"}

    create = vulkan.vkCreateInstance
    create.argtypes = [POINTER(_InstanceCreateInfo), c_void_p, POINTER(c_void_p)]
    create.restype = c_int32
    enumerate_devices = vulkan.vkEnumeratePhysicalDevices
    enumerate_devices.argtypes = [c_void_p, POINTER(c_uint32), POINTER(c_void_p)]
    enumerate_devices.restype = c_int32
    get_properties = vulkan.vkGetPhysicalDeviceProperties
    get_properties.argtypes = [c_void_p, c_void_p]
    get_properties.restype = None
    destroy = vulkan.vkDestroyInstance
    destroy.argtypes = [c_void_p, c_void_p]
    destroy.restype = None

    app = _ApplicationInfo(
        _STRUCTURE_TYPE_APPLICATION_INFO,
        None,
        b"AUTO-MAS",
        1,
        b"AUTO-MAS",
        1,
        _API_VERSION,
    )
    info = _InstanceCreateInfo(
        _STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        None,
        0,
        ctypes.pointer(app),
        0,
        None,
        0,
        None,
    )
    instance = c_void_p()
    result = create(byref(info), None, byref(instance))
    if result != 0:
        return {
            "loaded": True,
            "result": result,
            "devices": [],
            "error": "vkCreateInstance",
        }
    devices = []
    try:
        count = c_uint32(0)
        result = enumerate_devices(instance, byref(count), None)
        if result == 0 and count.value:
            handles = (c_void_p * count.value)()
            result = enumerate_devices(instance, byref(count), handles)
            for handle in handles[: count.value]:
                buffer = ctypes.create_string_buffer(_PROPERTIES_BUFFER)
                get_properties(handle, buffer)
                raw = buffer.raw
                name = raw[
                    _DEVICE_NAME_OFFSET : _DEVICE_NAME_OFFSET + _DEVICE_NAME_SIZE
                ]
                devices.append(
                    {
                        "name": name.split(b"\0", 1)[0].decode("utf-8", "replace"),
                        "type": int.from_bytes(raw[16:20], "little", signed=True),
                        "apiVersion": _version(int.from_bytes(raw[0:4], "little")),
                        "vendorId": int.from_bytes(raw[8:12], "little"),
                    }
                )
    finally:
        destroy(instance, None)
    return {"loaded": True, "result": result, "devices": devices, "error": ""}


if __name__ == "__main__":
    print(json.dumps(probe(), ensure_ascii=False), flush=True)
