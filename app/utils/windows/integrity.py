"""Windows 强制完整性级别（Mandatory Integrity Level）读取。

MuMu 模拟器 6.8.8 的 MuMuManager.exe 用 CreateProcessAsUser 拉起
MuMuNxMain.exe 时，子进程的完整性级别取「父令牌」与「映像文件」中的较低者；
安装目录若被旧版安装器标成 Low，主进程就会以 Low 启动并立即终止，表现为
control launch 反复重试后返回 -503 mainnx connect failed。
这里只负责把标签读出来，怎么用由调用点决定。
"""

import ctypes
import sys
from pathlib import Path

SE_FILE_OBJECT = 1
LABEL_SECURITY_INFORMATION = 0x00000010
SYSTEM_MANDATORY_LABEL_ACE_TYPE = 0x11

INTEGRITY_UNTRUSTED = 0x0000
INTEGRITY_LOW = 0x1000
INTEGRITY_MEDIUM = 0x2000
INTEGRITY_HIGH = 0x3000
INTEGRITY_SYSTEM = 0x4000
INTEGRITY_PROTECTED = 0x5000

_LEVEL_NAMES = {
    INTEGRITY_UNTRUSTED: "Untrusted",
    INTEGRITY_LOW: "Low",
    INTEGRITY_MEDIUM: "Medium",
    INTEGRITY_HIGH: "High",
    INTEGRITY_SYSTEM: "System",
    INTEGRITY_PROTECTED: "Protected",
}


class _AceHeader(ctypes.Structure):
    _fields_ = [
        ("AceType", ctypes.c_ubyte),
        ("AceFlags", ctypes.c_ubyte),
        ("AceSize", ctypes.c_ushort),
    ]


class _MandatoryLabelAce(ctypes.Structure):
    _fields_ = [
        ("Header", _AceHeader),
        ("Mask", ctypes.c_uint32),
        ("SidStart", ctypes.c_uint32),
    ]


class _AclHeader(ctypes.Structure):
    _fields_ = [
        ("AclRevision", ctypes.c_ubyte),
        ("Sbz1", ctypes.c_ubyte),
        ("AclSize", ctypes.c_ushort),
        ("AceCount", ctypes.c_ushort),
        ("Sbz2", ctypes.c_ushort),
    ]


def mandatory_label_rid(path: Path | str) -> int | None:
    """返回路径上强制完整性标签的 RID，例如 0x1000 为 Low、0x2000 为 Medium。

    路径没有标签（SACL 为空，绝大多数普通文件都是这样）、不存在，或者读取
    失败时返回 None——调用方据此区分「没标签」和「标签是别的级别」。
    """

    if sys.platform != "win32":
        return None

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32.GetNamedSecurityInfoW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_int,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetNamedSecurityInfoW.restype = ctypes.c_uint32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    advapi32.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
    advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    advapi32.GetSidSubAuthority.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    advapi32.GetSidSubAuthority.restype = ctypes.POINTER(ctypes.c_uint32)

    sacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    if (
        advapi32.GetNamedSecurityInfoW(
            str(path),
            SE_FILE_OBJECT,
            LABEL_SECURITY_INFORMATION,
            None,
            None,
            None,
            ctypes.byref(sacl),
            ctypes.byref(descriptor),
        )
        != 0
    ):
        return None
    if not descriptor.value:
        return None

    try:
        if not sacl.value:
            return None
        acl = ctypes.cast(sacl, ctypes.POINTER(_AclHeader)).contents
        offset = ctypes.sizeof(_AclHeader)
        for _ in range(acl.AceCount):
            ace = _MandatoryLabelAce.from_address(sacl.value + offset)
            # SID 紧跟 ACE 头（4 字节）与 Mask（4 字节）之后
            if ace.Header.AceType == SYSTEM_MANDATORY_LABEL_ACE_TYPE:
                return _label_rid(advapi32, sacl.value + offset + 8)
            if ace.Header.AceSize == 0:
                return None
            offset += ace.Header.AceSize
        return None
    finally:
        kernel32.LocalFree(descriptor)


def _label_rid(advapi32, sid: int) -> int | None:
    count = advapi32.GetSidSubAuthorityCount(sid)
    if not count:
        return None
    sub_authority = advapi32.GetSidSubAuthority(sid, count.contents.value - 1)
    if not sub_authority:
        return None
    return int(sub_authority.contents.value)


def integrity_level_name(rid: int | None) -> str:
    """把 RID 翻成 icacls 习惯的叫法，读不到时返回 Unknown。"""

    return _LEVEL_NAMES.get(rid if rid is not None else -1, "Unknown")
