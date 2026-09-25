#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""
zstd 解压后端 。

Sophon 的清单与 chunk 都是 zstd 压缩帧，必须用 libzstd 解压。
Python 侧按可用性依次降级：

    1. ``zstandard`` 包（最快）
    2. ``ctypes`` 直接加载 libzstd（仓库内就有 ``libzstd.dll``，或系统库）
    3. 纯 Python 实现（慢，仅用于小数据/离线自测）

提供两个入口：
    ``decompress(data) -> bytes``           一次性解压
    ``DecompressStream(stream) -> iterator`` 流式解压（大 chunk 用）
"""

from __future__ import annotations

import ctypes
import glob
import os
import sys
import threading
from typing import Iterator, Optional

__all__ = [
    "ZstdBackend",
    "backend_name",
    "is_available",
    "decompress",
    "iter_decompress",
    "ZstdError",
]


class ZstdError(RuntimeError):
    """zstd 解压失败。"""


# --------------------------------------------------------------------------- #
# 后端探测
# --------------------------------------------------------------------------- #

try:  # pragma: no cover - 可选依赖
    import zstandard  # type: ignore
except ImportError:  # pragma: no cover
    zstandard = None  # type: ignore


def _find_libzstd() -> Optional[str]:
    """在仓库内与系统路径中查找可用的 libzstd。

    先在仓库根目录下做递归 glob（``**/libzstd*``），命中即返回该路径；
    否则按平台试探常见文件名（如 ``libzstd.dll`` / ``libzstd.so.1``），
    能用 ``ctypes.CDLL`` 成功加载即视为可用。

    Returns:
        可用的库路径；全部失败返回 ``None``。
    """
    candidates: list[str] = []

    # 1) 随包一起发布的 libzstd
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.extend(
        glob.glob(os.path.join(repo_root, "**", "libzstd*"), recursive=True)
    )
    # 2) 常见系统名
    if sys.platform == "win32":
        candidates.extend(["libzstd.dll", "zstd.dll"])
    elif sys.platform == "darwin":
        candidates.extend(["libzstd.dylib", "/usr/local/lib/libzstd.dylib"])
    else:
        candidates.extend(["libzstd.so.1", "libzstd.so"])

    for candidate in candidates:
        if os.sep in candidate or "/" in candidate:
            path = candidate
        else:
            path = candidate
        if os.path.isfile(path):
            return path
        try:
            ctypes.CDLL(candidate)
            return candidate
        except OSError:
            continue
    return None


class _CtypesZstd:
    """用 ctypes 调 libzstd 的 simple API 解压。"""

    def __init__(self, lib_path: Optional[str] = None) -> None:
        """用 ctypes 加载 libzstd。

        Args:
            lib_path: 库文件路径；为 ``None`` 时尝试默认搜索路径。

        Raises:
            ZstdError: 加载不到库（``ctypes.CDLL`` 失败或路径无效）时。
        """
        self.lib = ctypes.CDLL(lib_path) if lib_path else None
        if self.lib is None:
            raise ZstdError("未找到 libzstd")
        self.lib.ZSTD_decompress.restype = ctypes.c_size_t
        self.lib.ZSTD_decompress.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_size_t,
        ]
        self.lib.ZSTD_isError.restype = ctypes.c_uint
        self.lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
        self.lib.ZSTD_getErrorName.restype = ctypes.c_char_p
        self.lib.ZSTD_getErrorName.argtypes = [ctypes.c_size_t]

    def decompress(self, data: bytes) -> bytes:
        """用 libzstd simple API 解压一段数据。

        Args:
            data: 压缩后的字节。

        Returns:
            解压后的原始字节。

        Raises:
            ZstdError: 库返回错误（如非 ``dstSize_tooSmall`` 的解压失败、
                输出缓冲区始终不足）时。
        """
        # 先用一个启发式容量，失败再按返回值重试
        for capacity in (len(data) * 8 + 65536, len(data) * 32 + 65536):
            output = ctypes.create_string_buffer(capacity)
            written = self.lib.ZSTD_decompress(
                output, ctypes.c_size_t(capacity), data, ctypes.c_size_t(len(data))
            )
            if self.lib.ZSTD_isError(written):
                name = self.lib.ZSTD_getErrorName(written).decode("utf-8", "replace")
                if "dstSize_tooSmall" in name:
                    continue
                raise ZstdError(f"libzstd 解压失败: {name}")
            return output.raw[:written]
        raise ZstdError("libzstd 解压失败：输出缓冲区不足")


class _PurePythonZstd:
    """最小化的纯 Python zstd 解压（仅覆盖 Sophon 用到的帧格式）。

    警告：性能远低于原生库，只应在没有 zstandard / libzstd 时作为兜底，
    且适合处理清单这类小数据。
    """

    MAGIC = 0xFD2FB528

    def decompress(self, data: bytes) -> bytes:
        """纯 Python 兜底解压（仅支持未压缩 / 单块的极小帧）。

        Args:
            data: zstd 帧字节。

        Returns:
            解压后的原始字节。

        Raises:
            ZstdError: 帧头非法、或不含 Raw/RLE 块（遇到真正压缩的块、
                多块帧）时——此时应改用 zstandard / libzstd 后端。
        """
        if len(data) < 6 or int.from_bytes(data[:4], "little") != self.MAGIC:
            raise ZstdError("不是合法的 zstd 帧")
        # 只处理「帧头里写了未压缩大小」的情况（官方下发的帧基本都带）
        frame_header_descriptor = data[4]
        content_size_flag = frame_header_descriptor >> 6
        single_segment = bool(frame_header_descriptor & 0x20)
        did_field_size = [0, 2, 4, 8][content_size_flag]

        offset = 6 if single_segment else 5
        content_size = None
        if did_field_size:
            content_size = int.from_bytes(
                data[offset : offset + did_field_size], "little"
            )
            if did_field_size == 2:
                content_size -= 256
            offset += did_field_size

        # raw block 快速路径
        while offset < len(data):
            header = int.from_bytes(data[offset : offset + 3], "little")
            block_type = (header >> 1) & 0x03
            block_size = (header >> 3) & 0x1FFFFF
            offset += 3
            if block_type == 0:  # Raw_Block
                return data[offset : offset + block_size]
            if block_type == 1:  # RLE_Block
                return data[offset : offset + 1] * block_size
            raise ZstdError(
                "纯 Python 后端只支持 Raw/RLE 块；请安装 zstandard 或提供 libzstd"
            )
        raise ZstdError("zstd 帧中没有可用数据块")


class _BackendProxy:
    """按优先级选择后端并统一接口。

    Note:
        ``zstandard.ZstdDecompressor`` 实例内部持有可复用的解压上下文，
        **不是线程安全的**：chunk 下载是多线程并发解压，共享单例会出现
        ``Data corruption detected`` / ``Unknown frame descriptor`` 之类的
        交叉损坏（实测 2026-09-25）。因此 zstandard 后端改为每线程独享
        一个实例（见 :func:`_zstd_impl`），ctypes 与纯 Python 后端本身就是
        无状态调用，不需要隔离。
    """

    def __init__(self) -> None:
        """按优先级探测并选定 zstd 后端。

        依次尝试 zstandard 包 → ctypes 加载 libzstd → 纯 Python 兜底，
        并把选定结果记到 ``self.name``；zstandard 的实例按线程惰性创建，
        不放在 ``self._impl`` 里共享。
        """
        self.name = "none"
        self._impl: object = None

        if zstandard is not None:
            self.name = "zstandard"
            return

        lib_path = _find_libzstd()
        if lib_path:
            try:
                self._impl = _CtypesZstd(lib_path)
                self.name = f"ctypes:{os.path.basename(lib_path)}"
                return
            except (OSError, ZstdError):  # pragma: no cover
                pass

        self._impl = _PurePythonZstd()
        self.name = "pure-python"

    @property
    def available(self) -> bool:
        """后端是否成功初始化。

        Returns:
            ``True`` 表示存在可用后端，``False`` 表示全部探测失败。
        """
        return self._impl is not None or self.name == "zstandard"

    def decompress(self, data: bytes) -> bytes:
        """用当前选定后端解压一段数据。

        Args:
            data: 压缩后的字节。

        Returns:
            解压后的原始字节。

        Raises:
            ZstdError: 底层后端解压失败时（如 zstandard / libzstd 报错）。
        """
        if self.name == "zstandard":
            return _zstd_impl().decompress(data)
        return self._impl.decompress(data)  # type: ignore[union-attr]

    def iter_decompress(self, stream, chunk_size: int = 65536) -> Iterator[bytes]:
        """流式解压，分块产出。

        Args:
            stream: 提供 ``read()`` 的类文件对象（原始压缩流）。
            chunk_size: 每块最大字节数（仅 zstandard 后端生效）。

        Yields:
            解压后的数据块（``bytes``）。

        Note:
            zstandard 后端边读边解压、内存友好；其它后端会先把**整个流读
            进内存**再整体解压、最后切块返回，大文件需留意峰值内存。
        """
        if self.name == "zstandard":
            with _zstd_impl().stream_reader(stream) as reader:
                while True:
                    chunk = reader.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
            return
        # 其它后端：一次性读入后解压再切块
        data = stream.read()
        if isinstance(data, str):  # pragma: no cover
            data = data.encode("utf-8")
        output = self.decompress(data)
        for offset in range(0, len(output), chunk_size):
            yield output[offset : offset + chunk_size]


#: 线程各自的 zstandard 解压器（实例不可跨线程共享，见 :class:`_BackendProxy`）
_ZSTD_LOCAL = threading.local()


def _zstd_impl() -> "zstandard.ZstdDecompressor":
    """返回当前线程独享的 ``zstandard.ZstdDecompressor``。

    Returns:
        惰性创建、绑定在当前线程上的解压器实例。
    """
    impl = getattr(_ZSTD_LOCAL, "impl", None)
    if impl is None:
        impl = _ZSTD_LOCAL.impl = zstandard.ZstdDecompressor()
    return impl


_BACKEND: Optional[_BackendProxy] = None


def ZstdBackend() -> _BackendProxy:
    """返回（惰初始化的）全局后端。"""
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = _BackendProxy()
    return _BACKEND


def backend_name() -> str:
    """返回当前选定后端的名称。

    Returns:
        名称字符串，可能为 ``"zstandard"``、``"ctypes:<库名>"``、
        ``"pure-python"`` 或探测全部失败时的 ``"none"``。
    """
    return ZstdBackend().name


def is_available() -> bool:
    """是否有可用后端。

    Returns:
        ``True`` 表示 zstandard / libzstd / 纯 Python 任一后端可用。
    """
    return ZstdBackend().available


def decompress(data: bytes) -> bytes:
    """解压一段 zstd 数据（委托给当前后端）。

    Args:
        data: 压缩后的字节。

    Returns:
        解压后的原始字节。

    Raises:
        ZstdError: 后端解压失败时。
    """
    return ZstdBackend().decompress(data)


def iter_decompress(stream, chunk_size: int = 65536) -> Iterator[bytes]:
    """流式解压（委托给当前后端，逐块产出）。

    Args:
        stream: 提供 ``read()`` 的类文件对象（原始压缩流）。
        chunk_size: 每块最大字节数（仅 zstandard 后端生效）。

    Yields:
        解压后的数据块（``bytes``）。

    Note:
        非 zstandard 后端会把整个流读进内存再整体解压、然后切块返回。
    """
    yield from ZstdBackend().iter_decompress(stream, chunk_size)
