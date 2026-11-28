"""限时开放与 Electron 共用配置时的 Windows 文件替换。"""

import ctypes
import os
from ctypes import wintypes
from pathlib import Path
from tempfile import NamedTemporaryFile

import pywintypes
import win32con
import win32file

_FILE_RENAME_INFO_EX = 22
_FILE_RENAME_REPLACE_IF_EXISTS = 1
_FILE_RENAME_POSIX_SEMANTICS = 2


class _FileRenameInfo(ctypes.Structure):
    _fields_ = [
        ("flags", wintypes.DWORD),
        ("root_directory", wintypes.HANDLE),
        ("file_name_length", wintypes.DWORD),
        ("file_name", wintypes.WCHAR * 1),
    ]


_SetFileInformationByHandle = ctypes.WinDLL(
    "kernel32", use_last_error=True
).SetFileInformationByHandle
_SetFileInformationByHandle.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
)
_SetFileInformationByHandle.restype = wintypes.BOOL


def _replace_open_file(staged: Path, target: Path) -> None:
    """使用 FileRenameInfoEx 替换仍持有保护句柄的文件。"""
    name = str(target).encode("utf-16-le")
    size = max(
        ctypes.sizeof(_FileRenameInfo), _FileRenameInfo.file_name.offset + len(name) + 2
    )
    buffer = ctypes.create_string_buffer(size)
    info = _FileRenameInfo.from_buffer(buffer)
    info.flags = _FILE_RENAME_REPLACE_IF_EXISTS | _FILE_RENAME_POSIX_SEMANTICS
    info.file_name_length = len(name)
    ctypes.memmove(
        ctypes.addressof(info) + _FileRenameInfo.file_name.offset, name, len(name)
    )

    handle = win32file.CreateFile(
        str(staged),
        win32con.DELETE,
        win32con.FILE_SHARE_READ
        | win32con.FILE_SHARE_WRITE
        | win32con.FILE_SHARE_DELETE,
        None,
        win32con.OPEN_EXISTING,
        0,
        None,
    )
    try:
        if not _SetFileInformationByHandle(
            int(handle), _FILE_RENAME_INFO_EX, buffer, size
        ):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        handle.Close()


def replace_if_unchanged(*, path: Path, original: bytes | None, updated: bytes) -> None:
    """仅在磁盘仍为读取时的版本时替换，遇到并发写入则让给客户端。"""
    staged: Path | None = None
    try:
        with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            staged = Path(temporary.name)
            temporary.write(updated)
            temporary.flush()
            os.fsync(temporary.fileno())

        if original is None:
            # Windows rename 不覆盖目标，避免覆盖刚由客户端创建的配置。
            staged.rename(path)
            return

        guard = win32file.CreateFile(
            str(path),
            win32con.GENERIC_READ,
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_DELETE,
            None,
            win32con.OPEN_EXISTING,
            0,
            None,
        )
        try:
            _, current = win32file.ReadFile(guard, len(original) + 1)
            if current == original:
                _replace_open_file(staged, path)
        finally:
            guard.Close()
    except pywintypes.error as error:
        raise ctypes.WinError(error.winerror) from error
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
