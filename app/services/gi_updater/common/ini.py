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
游戏/启动器 ``config.ini`` 读写。

磁盘上有两份 ini：

* **Profile ini**（``<AppGameFolder>/<ProfileName>/config.ini``）
  段 ``[launcher]``，关键键 ``game_install_path`` 指向真正的游戏目录。
* **Version ini**（``<game_install_path>/config.ini``）
  段 ``[General]``，关键键 ``game_version`` / ``channel`` / ``sub_channel`` /
  ``cps`` / ``plugin_<id>_version`` / ``plugin_sdk_version`` / ``uapc``。

实现要点：
  * 保留原有的 BOM、换行风格与键顺序（不做全量重写时）
  * 键比较 **大小写不敏感**，但写回时保留原有大小写
  * 未知段/键原样保留（文件里还有游戏与启动器自己写的配置）
"""

from __future__ import annotations

import os
import re
from typing import Dict, Iterator, List, Optional, Tuple

__all__ = ["IniFile", "IniSection", "IniValue", "load_ini", "save_ini"]

_SECTION_RE = re.compile(r"^\s*\[\s*(?P<name>[^\]]*?)\s*\]\s*$")
_KV_RE = re.compile(r"^\s*(?P<key>[^=:\s][^=:]*?)\s*(?P<sep>[=:])\s*(?P<value>.*?)\s*$")

#: ``config.ini`` 里承载游戏版本信息的段名
VERSION_SECTION = "General"
#: 启动器 profile 段名
PROFILE_SECTION = "launcher"


class IniValue(str):
    """ini 值。继承 ``str`` 以便直接当字符串用，同时保留原始字面量。"""

    __slots__ = ()

    def as_int(self, default: int = 0) -> int:
        """按 ``int`` 解析本值；空值或解析失败（``TypeError``/``ValueError``）时返回 ``default``。

        Args:
            default: 无法转成整数时回退的值，默认 ``0``。

        Returns:
            解析出的整数，或 ``default``。
        """
        try:
            return int(str(self).strip())
        except (TypeError, ValueError):
            return default

    def as_bool(self, default: bool = False) -> bool:
        """按布尔解析本值：``true/1/yes/on`` 为真，``false/0/no/off`` 为假。

        Args:
            default: 不属于上述任一集合时回退的值，默认 ``False``。

        Returns:
            解析出的布尔，或 ``default``。
        """
        text = str(self).strip().lower()
        if text in ("true", "1", "yes", "on"):
            return True
        if text in ("false", "0", "no", "off"):
            return False
        return default


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
        """写入键值，保留首次出现的键大小写与插入顺序。

        Args:
            key: 键名（查找大小写不敏感，但写回沿用首次写入时的大小写）。
            value: 任意值，会被包装成 :class:`IniValue`。
        """
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

        与 的宽容读取一致：访问不存在的键会在段内留下一个空
        ``IniValue`` 并记入键顺序，因此本方法兼具「查询」与「副作用写入」。

        Args:
            key: 键名（大小写不敏感）。

        Returns:
            对应的 :class:`IniValue`；未命中时为新建的空值。
        """
        lower = str(key).lower()
        original = self._key_case_map.get(lower)
        if original is not None and original in self.keys():
            return super().__getitem__(original)
        # 未找到时返回空 IniValue 而不是抛异常 —— 与 的宽容行为一致
        empty = IniValue("")
        super().__setitem__(str(key), empty)
        self._key_case_map[lower] = str(key)
        self.order.append(str(key))
        return empty

    def __contains__(self, key: object) -> bool:
        """判断键是否存在（大小写不敏感，且对「尚未首次写入」的大小写别名也成立）。

        Args:
            key: 待查键名。

        Returns:
            该键（忽略大小写）是否已存在于段中。
        """
        return super().__contains__(str(key)) or str(key).lower() in self._key_case_map

    def get(self, key: str, default: object = None):  # type: ignore[override]
        """宽松取值；键不存在时返回 ``default`` 且**不会**像 ``__getitem__`` 那样创建空节点。

        Args:
            key: 键名（大小写不敏感）。
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

        Args:
            key: 缺失的键名。

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

        Args:
            section: 段名。

        Returns:
            该段名（忽略大小写）是否已存在。
        """
        return str(section).lower() in self._lower_map

    def __getitem__(self, section: str) -> IniSection:
        """获取段；不存在时**新建空段并返回**（写入段顺序，不抛异常）。

        Args:
            section: 段名。

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
            section: 段名（大小写不敏感）。
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

        Args:
            path: ini 文件路径。

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

        Args:
            text: 已解码的 ini 纯文本。
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
        """将文档写回磁盘；必要时自动创建父目录。

        写回沿用加载时探测到的编码（``encoding``）与换行符（``newline``）。

        Args:
            path: 目标文件路径。
        """
        directory = os.path.dirname(os.path.abspath(path))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding=self.encoding, newline="") as handle:
            handle.write(self.dumps())


def load_ini(path: str) -> IniFile:
    """便捷封装，等价于 :meth:`IniFile.load`。

    Args:
        path: ini 文件路径。

    Returns:
        解析出的 :class:`IniFile`。
    """
    return IniFile.load(path)


def save_ini(ini: IniFile, path: str) -> None:
    """便捷封装，等价于 :meth:`IniFile.save`。

    Args:
        ini: 待写回的 :class:`IniFile` 文档。
        path: 目标文件路径。
    """
    ini.save(path)
