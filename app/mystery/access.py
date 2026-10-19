"""神秘入口的设备与当前后端源码指纹。"""

import hashlib
import sys
import uuid
from pathlib import Path
from threading import Lock
from typing import Literal

if sys.platform == "win32":
    import pythoncom
    import win32com.client

_context: tuple[str, str] | None = None
_context_lock = Lock()


class MysteryContextError(Exception):
    def __init__(self, code: Literal["DEVICE_UNAVAILABLE", "BACKEND_UNAVAILABLE"]):
        super().__init__(code)
        self.code = code


def _query_windows_uuid() -> str:
    # COM 引用在这个函数返回时释放，先于外层 CoUninitialize。
    service = win32com.client.GetObject(r"winmgmts:\\.\root\cimv2")
    for row in service.ExecQuery("SELECT UUID FROM Win32_ComputerSystemProduct"):
        return str(row.UUID).strip()
    raise ValueError("SMBIOS UUID unavailable")


def get_device_hash() -> str:
    """读取有效的 SMBIOS UUID，不使用安装标识或共用默认值。"""
    if sys.platform != "win32":
        raise MysteryContextError("DEVICE_UNAVAILABLE")
    try:
        pythoncom.CoInitialize()
        try:
            device_uuid = uuid.UUID(_query_windows_uuid())
        finally:
            pythoncom.CoUninitialize()
        if device_uuid.int in (0, (1 << 128) - 1):
            raise ValueError("SMBIOS UUID unavailable")
        source = f"auto-mas:mystery:device:v1|smbios|{device_uuid}"
        return hashlib.sha256(source.encode("utf-8")).hexdigest()
    except Exception as error:
        raise MysteryContextError("DEVICE_UNAVAILABLE") from error


def get_backend_hash(root: Path) -> str:
    """按相对路径排序哈希源码；目录位置、换行和运行产物不影响结果。"""
    paths = [root / "main.py", *(root / "app").rglob("*.py")]
    digest = hashlib.sha256(b"auto-mas:mystery:backend:v1\n")
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        if "__pycache__" in path.parts:
            continue
        relative_path = path.relative_to(root).as_posix()
        content = path.read_bytes().replace(b"\r\n", b"\n")
        file_hash = hashlib.sha256(content).hexdigest()
        digest.update(f"{relative_path}\0{file_hash}\n".encode("utf-8"))
    return digest.hexdigest()


def get_access_context() -> tuple[str, str]:
    """每个后端进程只采集一次；并发请求共用同一结果。"""
    global _context
    with _context_lock:
        if _context is None:
            device_hash = get_device_hash()
            try:
                backend_hash = get_backend_hash(Path(__file__).resolve().parents[2])
            except OSError as error:
                raise MysteryContextError("BACKEND_UNAVAILABLE") from error
            _context = device_hash, backend_hash
        return _context
