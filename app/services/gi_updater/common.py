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

"""通用件：领域异常、日志出口、路径防护、config.ini 读写与跨层回调类型。

**异常**：``UpdaterError`` 表示「这次没能按协议拿到东西」，``UpdateAborted`` 表示调用方
要求收工；其余异常按程序缺陷看待。

**日志**：引擎内部按 ``logger.info("已迁移 %d 个文件：%s", count, path)`` 这种惰性
格式写日志，而宿主的 loguru 用 ``{}`` 占位，两者不能直接混用；本模块是唯一做这条
转换的地方，调用方不需要改写法。级别只用到 ``debug`` / ``info`` / ``warning`` /
``error``，与 loguru 同名方法一一对应。

**路径**：要落盘哪些文件、叫什么名字，全部来自服务端下发的清单字符串——Sophon
主清单里每个 asset 的本地路径、差分清单里的目标文件名与待删除文件名。任何一条写成
绝对路径或带 ``..``，就会写到游戏目录外面。收口只有一处：先按分量校验，再用
:func:`os.path.commonpath` 判是否仍在根内，越界即拒。

**ini**：磁盘上有两份。Profile ini 在 ``<AppGameFolder>/<ProfileName>/config.ini``，
段 ``[launcher]``，关键键 ``game_install_path`` 指向真正的游戏目录；Version ini 在
``<game_install_path>/config.ini``，段 ``[General]``，关键键 ``game_version`` /
``channel`` / ``sub_channel`` / ``cps``。实现上保留原有的 BOM、换行风格与键顺序（不
做全量重写时），键比较**大小写不敏感**但写回时保留原有大小写，未知段/键原样保留
——文件里还有游戏与启动器自己写的配置。

**回调**：进度与中止都以函数形参传进来（``ProgressHook`` / ``AbortHook``），引擎不持有任何
展示层对象。
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, Dict, Iterator, List, Optional, Tuple

__all__ = [
    "IniFormatError",
    "UpdateAborted",
    "get_logger",
    "UnsafePathError",
    "split_rel_path",
    "safe_join",
    "IniFile",
    "IniSection",
    "IniValue",
    "AbortHook",
    "ProgressHook",
    "Throttle",
    "UpdaterError",
    "summarize_size",
]

#: 一行面向用户的进度文案
ProgressHook = Callable[[str], Awaitable[None]]

#: 中止判定；为真时在文件批次边界收工
AbortHook = Callable[[], bool]


class UpdaterError(RuntimeError):
    """问不出、取不到、或取回的内容与清单不符。

    只说明「这次没能按协议拿到东西」，不代表用户的客户端坏了；调用方据此按
    「无法判定」放行，而不是记一次任务失败。
    """


class IniFormatError(RuntimeError):
    """现有 ``config.ini`` 读不懂，拒绝改写。"""


class UpdateAborted(RuntimeError):
    """用户中止了本轮更新。

    由 ``should_abort`` 判定在下载与打补丁的边界抛出；已落盘的合法文件不回滚，
    ``config.ini`` 也不会被写，因此重新发起即可从断点继续。
    """


class PercentStyleLogger:
    """把 ``%`` 惰性格式化转发给 loguru 的薄壳。"""

    def __init__(self, name: str = "更新引擎") -> None:
        """绑定一个宿主 logger。"""
        from app.utils import get_logger as host_get_logger

        self._logger = host_get_logger(name)

    def _emit(self, level: str, message: Any, args: tuple[Any, ...]) -> None:
        """按 ``level`` 输出一条消息，参数缺失或格式不匹配时降级为拼接。

        Args:
            args: 位置参数；为空表示不做格式化。
        """
        if not args:
            text = message if isinstance(message, str) else str(message)
        else:
            try:
                text = str(message) % args
            except (TypeError, ValueError):
                # 模板与参数对不上是日志本身的问题，不能让它掀掉正在跑的流程
                text = " ".join([str(message), *[repr(a) for a in args]])
        getattr(self._logger, level)(text)

    def debug(self, message: Any, *args: Any) -> None:
        """输出 DEBUG 级日志。"""
        self._emit("debug", message, args)

    def info(self, message: Any, *args: Any) -> None:
        """输出 INFO 级日志。"""
        self._emit("info", message, args)

    def warning(self, message: Any, *args: Any) -> None:
        """输出 WARNING 级日志。"""
        self._emit("warning", message, args)

    def error(self, message: Any, *args: Any) -> None:
        """输出 ERROR 级日志。"""
        self._emit("error", message, args)


_CACHE: dict[str, PercentStyleLogger] = {}


def get_logger(name: str = "更新引擎") -> PercentStyleLogger:
    """取引擎用的 logger（按名字复用同一个实例）。

    Args:
        name: loguru 的模块名；装配层会按游戏传「<游戏名>更新」，缺省为中性名。

    Returns:
        :class:`PercentStyleLogger` 实例。
    """
    cached = _CACHE.get(name)
    if cached is None:
        cached = _CACHE[name] = PercentStyleLogger(name)
    return cached


#: Windows 盘符前缀（``C:`` / ``c:``），也用来清洗 ``a/C:x`` 这类中间段
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class UnsafePathError(ValueError):
    """相对路径越界或形态非法 —— 调用方应当拒绝该条目，不要写入任何文件。"""


def split_rel_path(rel_path: str) -> list[str]:
    """把远端下发的相对路径清洗成安全的段列表。
    Returns:
        逐个目录段（已去掉空段与 ``.`` 段），至少含一段。

    Raises:
        UnsafePathError: 输入为空、含 ``..`` 段、带盘符（``C:``）、是 UNC
            （``//server/share``）或清洗后不剩任何段。

    Note:
        前导 ``/`` 是**剥掉**而不是拒绝 —— 正常清单里确实会出现 ``/ExecuteTask``
        这类绝对形态的成员名，拒绝会让合法安装失败。真正的越界靠 ``..`` 段
        与后面的 commonpath 判定拦。
    """
    text = str(rel_path or "").strip()
    if not text:
        raise UnsafePathError("空路径")

    text = text.replace("\\", "/")
    # UNC：把 ``//server/share/x`` 拆成 ``['','server',...]``，第一段就是 ``//``
    if text.startswith("//"):
        raise UnsafePathError(f"拒绝 UNC 路径: {rel_path!r}")

    parts: list[str] = []
    for segment in text.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            raise UnsafePathError(f"拒绝越界（含 .. 段）: {rel_path!r}")
        if _DRIVE_RE.match(segment):
            raise UnsafePathError(f"拒绝带盘符的路径: {rel_path!r}")
        parts.append(segment)

    if not parts:
        raise UnsafePathError(f"清洗后不剩任何路径段: {rel_path!r}")
    return parts


def safe_join(root: str, rel_path: str) -> str:
    """把不可信的相对路径拼到可信根目录下，越界即抛。
    Returns:
        位于 ``root`` 内部的绝对路径。

    Raises:
        UnsafePathError: 路径形态非法，或拼接结果落在 ``root`` 之外。

    Note:
        最后一道防线是 :func:`os.path.commonpath` 而不是 ``startswith`` ——
        ``root`` 为 ``...\\Games`` 时，``...\\GamesEvil\\x.exe`` 会被
        字符串前缀判定放行，commonpath 不会。比较前统一过
        :func:`os.path.normcase`，因此在 Windows 上大小写不敏感。
    """
    parts = split_rel_path(rel_path)
    joined = os.path.join(root, *parts)
    root_abs = os.path.normcase(os.path.abspath(root))
    joined_abs = os.path.normcase(os.path.abspath(joined))
    try:
        common = os.path.commonpath([root_abs, joined_abs])
    except ValueError as exc:  # 不同盘符、绝对与相对混用等
        raise UnsafePathError(f"无法判定路径归属: {rel_path!r} ({exc})") from exc
    if common != root_abs:
        raise UnsafePathError(f"越出根目录 {root!r}: {rel_path!r}")
    return joined


_SECTION_RE = re.compile(r"^\s*\[\s*(?P<name>[^\]]*?)\s*\]\s*$")
_KV_RE = re.compile(r"^\s*(?P<key>[^=:\s][^=:]*?)\s*(?P<sep>[=:])\s*(?P<value>.*?)\s*$")

#: ``config.ini`` 里承载游戏版本信息的段名
VERSION_SECTION = "General"
#: 启动器 profile 段名
PROFILE_SECTION = "launcher"


class IniValue(str):
    """ini 值。继承 ``str`` 以便直接当字符串用，同时保留原始字面量。"""

    __slots__ = ()


class IniSection(Dict[str, IniValue]):
    """一个 ini 段。键查找大小写不敏感。"""

    def __init__(self, name: str = "") -> None:
        """初始化一个段，同时建立大小写映射与键出现顺序表。"""
        super().__init__()
        self.name = name
        self._key_case_map: Dict[str, str] = {}
        self.order: List[str] = []

    # -------------------------------------------------------------- dict 覆写

    def __setitem__(self, key: str, value: object) -> None:
        """写入键值，保留首次出现的键大小写与插入顺序。"""
        lower = str(key).lower()
        original = self._key_case_map.get(lower)
        if original is None:
            self._key_case_map[lower] = str(key)
            self.order.append(str(key))
        else:
            key = original
        super().__setitem__(str(key), IniValue(value))

    def __getitem__(self, key: str) -> IniValue:
        """读取键值；未命中时**静默创建空节点并返回**，不会抛异常。

        与 :meth:`get` 一样宽容：访问不存在的键会在段内留下一个空
        ``IniValue`` 并记入键顺序，因此本方法兼具「查询」与「副作用写入」。
        Returns:
            对应的 :class:`IniValue`；未命中时为新建的空值。
        """
        lower = str(key).lower()
        original = self._key_case_map.get(lower)
        if original is not None and original in self.keys():
            return super().__getitem__(original)
        # 未找到时返回空 IniValue 而不是抛异常，与 get() 的宽容读法一致
        empty = IniValue("")
        super().__setitem__(str(key), empty)
        self._key_case_map[lower] = str(key)
        self.order.append(str(key))
        return empty

    def __contains__(self, key: object) -> bool:
        """判断键是否存在（大小写不敏感，且对「尚未首次写入」的大小写别名也成立）。
        Returns:
            该键（忽略大小写）是否已存在于段中。
        """
        return super().__contains__(str(key)) or str(key).lower() in self._key_case_map

    def get(self, key: str, default: object = None):  # type: ignore[override]
        """宽松取值；键不存在时返回 ``default`` 且**不会**像 ``__getitem__`` 那样创建空节点。

        Args:
            default: 缺失时返回的值，默认 ``None``。

        Returns:
            对应的 :class:`IniValue`，或 ``default``。
        """
        if key in self:
            return self[key]
        return default

    def __missing__(
        self, key: str
    ) -> IniValue:  # pragma: no cover - 由 __getitem__ 兜底
        """dict 缺失键兜底；实际不会触发（``__getitem__`` 已自行处理）。
        Returns:
            占位用的空 :class:`IniValue`。
        """
        return IniValue("")


class IniFile:
    """轻量 ini 文档模型，支持「读 → 改 → 写回」且尽量保留原格式。"""

    def __init__(self) -> None:
        """初始化空文档，记录段顺序、大小写映射与首个段之前的前导内容（preamble）。"""
        self._sections: Dict[str, IniSection] = {}
        self._section_order: List[str] = []
        self._lower_map: Dict[str, str] = {}
        # 原文里位于第一个段之前的内容（注释等）
        self.preamble: List[str] = []
        self.encoding: str = "utf-8"
        self.newline: str = os.linesep

    # ------------------------------------------------------------------ 访问

    @property
    def sections(self) -> List[str]:
        """返回按出现顺序排列的段名列表（副本）。"""
        return list(self._section_order)

    def __contains__(self, section: object) -> bool:
        """判断段是否存在（大小写不敏感）。
        Returns:
            该段名（忽略大小写）是否已存在。
        """
        return str(section).lower() in self._lower_map

    def __getitem__(self, section: str) -> IniSection:
        """获取段；不存在时**新建空段并返回**（写入段顺序，不抛异常）。
        Returns:
            对应的 :class:`IniSection`；未命中时为新建的空段。
        """
        lower = str(section).lower()
        name = self._lower_map.get(lower)
        if name is not None:
            return self._sections[name]
        created = IniSection(str(section))
        self._sections[str(section)] = created
        self._lower_map[lower] = str(section)
        self._section_order.append(str(section))
        return created

    def get(self, section: str, default: object = None):
        """宽松取段；段不存在时返回 ``default`` 而不创建空段。

        Args:
            default: 缺失时返回的值，默认 ``None``。

        Returns:
            对应的 :class:`IniSection`，或 ``default``。
        """
        return self[section] if section in self else default

    def items(self) -> Iterator[Tuple[str, IniSection]]:
        """按段顺序产出 ``(段名, IniSection)`` 对。

        Yields:
            段名与对应段对象的元组。
        """
        for name in self._section_order:
            yield name, self._sections[name]

    # ------------------------------------------------------------------ 读写

    @classmethod
    def load(cls, path: str) -> "IniFile":
        """从磁盘加载 ini；文件不存在时返回空文档。

        保留原文件注释、键顺序与换行风格：自动探测 UTF-8 / UTF-8-BOM / UTF-16
        编码，并记录首个段之前的前导内容到 ``preamble``。
        Returns:
            解析出的 :class:`IniFile`；文件不存在时为不含任何段的空文档。
        """
        ini = cls()
        if not os.path.isfile(path):
            return ini

        with open(path, "rb") as handle:
            raw = handle.read()

        # 保留 BOM：官方写出的 ini 常带 UTF-8 BOM
        if raw.startswith(b"\xef\xbb\xbf"):
            ini.encoding = "utf-8-sig"
            text = raw.decode("utf-8-sig")
        else:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                ini.encoding = "utf-16"
                text = raw.decode("utf-16")

        if "\r\n" in text:
            ini.newline = "\r\n"
        elif "\n" in text:
            ini.newline = "\n"

        ini._parse(text)
        return ini

    def _parse(self, text: str) -> None:
        """把已解码的文本按行解析为段/键值，写入内部模型。

        段名匹配 ``_SECTION_RE``、键值匹配 ``_KV_RE``；首个段之前的非键值行
        视为前导内容存入 ``preamble``。
        """
        current: Optional[IniSection] = None
        for line in text.splitlines():
            section_match = _SECTION_RE.match(line)
            if section_match:
                name = section_match.group("name")
                current = self[name]
                continue

            kv_match = _KV_RE.match(line)
            if kv_match and current is not None:
                current[kv_match.group("key")] = IniValue(kv_match.group("value"))
            elif current is None:
                self.preamble.append(line)

    def dumps(self) -> str:
        """按原顺序序列化为字符串，保留 preamble、段序与键序（写回不破坏原格式）。"""
        lines: List[str] = list(self.preamble)
        for name in self._section_order:
            section = self._sections[name]
            lines.append(f"[{name}]")
            for key in section.order:
                lines.append(f"{key}={section[key]}")
            lines.append("")
        return self.newline.join(lines).rstrip(self.newline) + self.newline

    def save(self, path: str) -> None:
        """把改动写回磁盘——**只替换变化的那几行**，其余字节原样保留。

        目标文件已存在时走单行替换：定位 ``[段]`` 下的 ``键=值`` 行，整行换成模型里的
        新值并沿用该行原有的行尾；模型里有、文件里没有的键追加到该段末尾；文件里有而
        模型没动的段、键、注释行、空行一概不碰。文件不存在才整份写出。
        Raises:
            IniFormatError: 现有文件按加载时的编码解不开时——宁可停手，也不把一份读不
                懂的配置覆盖掉。

        Note:
            不整份重序列化，是因为模型只认段与键：注释、未知段、键的原始大小写与对齐
            都会在重写中丢掉，而这两个 ``config.ini`` 里还放着游戏与启动器自己的配置。
            同名重复键只替换第一次出现，后续出现原样留着。落盘一律原子改名，免得写一半
            时断电留下截断文件。
        """
        directory = os.path.dirname(os.path.abspath(path))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)

        from pathlib import Path as _Path

        from app.utils.io import atomic_write as _atomic_write

        existing = self._read_existing(path)
        payload = self.dumps() if existing is None else self._splice(existing)
        _atomic_write(_Path(path), payload.encode(self.encoding))

    def _read_existing(self, path: str) -> Optional[str]:
        """按加载时的编码读出磁盘上的现有内容。
        Returns:
            解码后的文本；文件不存在时返回 ``None``，表示需要整份写出。

        Raises:
            IniFormatError: 解码失败时。
        """
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "rb") as handle:
                return handle.read().decode(self.encoding)
        except (UnicodeDecodeError, ValueError) as error:
            raise IniFormatError(
                f"{path} 解不开为 {self.encoding} 文本，拒绝改写以免损坏配置"
            ) from error

    def _section_spans(self, lines: List[str]) -> Dict[str, Tuple[int, int]]:
        """算出每个段在原文里的行区间。
        Returns:
            ``段名（折叠大小写）-> (起始行, 结束行左开)``，段头行本身含在区间内。
        """
        spans: Dict[str, List[int]] = {}
        current: Optional[str] = None
        for index, line in enumerate(lines):
            match = _SECTION_RE.match(line)
            if match:
                current = match.group("name").casefold()
                spans.setdefault(current, [index, index + 1])
            elif current is not None:
                spans[current][1] = index + 1
        return {name: (span[0], span[1]) for name, span in spans.items()}

    def _splice(self, text: str) -> str:
        """把模型里被改过的键替换进原文，其余行一字不动。
        Returns:
            改好的完整文本。
        """
        lines = text.splitlines(keepends=True)
        spans = self._section_spans(lines)
        ending = self.newline
        rewritten: set = set()
        appends: Dict[str, List[str]] = {}

        for name, section in self.items():
            span = spans.get(name.casefold())
            if span is None:
                appends[name] = [
                    f"{key}={section[key]}{ending}" for key in section.order
                ]
                continue
            for key in section.order:
                value = section[key]
                tail = None
                for index in range(span[0], span[1]):
                    if index in rewritten:
                        continue
                    line = lines[index]
                    match = _KV_RE.match(line)
                    if not match or match.group("key").casefold() != key.casefold():
                        continue
                    tail = line[len(line.rstrip("\r\n")) :] or ending
                    lines[index] = f"{key}={value}{tail}"
                    rewritten.add(index)
                    break
                if tail is None:
                    appends.setdefault(name, []).append(f"{key}={value}{ending}")

        if not appends:
            return "".join(lines)
        return self._insert_appends(lines, spans, appends, ending)

    @staticmethod
    def _insert_appends(
        lines: List[str],
        spans: Dict[str, Tuple[int, int]],
        appends: Dict[str, List[str]],
        ending: str,
    ) -> str:
        """把原文里没有的键插到所属段末尾；段本身也不存在时整段追加到文件末尾。
        Returns:
            插入完成的文本。
        """
        insert_at: List[Tuple[int, str]] = []
        at_eof: List[str] = []
        for name, extra in appends.items():
            block = "".join(extra)
            span = spans.get(name.casefold())
            if span is None:
                at_eof.append(f"[{name}]{ending}{block}")
            else:
                insert_at.append((span[1], block))

        out = list(lines)
        # 从后往前插，前面的插入才不会把后面的行号顶掉
        for index, block in sorted(insert_at, reverse=True):
            out.insert(index, block)
        text = "".join(out)
        if at_eof:
            if text and not text.endswith(ending):
                text += ending
            text += "".join(at_eof)
        return text


def summarize_size(size: float) -> str:
    """把字节数格式化成人类可读的体积（1024 进制）。

    按 B/KiB/MiB/GiB/TiB 递进，绝对值达到 1024 才升一档（故 ``1024`` 显示为
    ``"1.00 KiB"``）；``B`` 档取整，其余档留 2 位小数，如 ``"1.50 MiB"``。
    """
    size = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(size) < 1024.0 or unit == "TiB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TiB"  # pragma: no cover


class Throttle:
    """按时间间隔放行重复事件。

    进度回调在异步引擎里每条都要 await，密集起来足以刷爆调度台；这里只回答
    「距上次放行够了没有」，够与不够之后说什么由调用方定。
    """

    def __init__(self, interval: float) -> None:
        """记录间隔；第一次 :meth:`ready` 必定放行。"""
        self._interval = interval
        self._last = 0.0

    def ready(self) -> bool:
        """现在该不该放行一次。

        Returns:
            距上次放行已超过间隔时为真，并同时刷新时刻。
        """
        now = time.monotonic()
        if now - self._last < self._interval:
            return False
        self._last = now
        return True
