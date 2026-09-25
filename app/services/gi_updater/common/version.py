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
版本号值类型。

米哈游使用 4 段版本号（major.minor.patch.revision，例如 3.4.0.0 / 2.7.10.1）。
比较语义：
  * 允许短版本（"3.4" == "3.4.0.0"）
  * 逐段数值比较，不做字符串比较
  * 未解析/空串视为 None（表示「未安装」或「未知」）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

__all__ = ["GameVersion", "VERSION_SEGMENTS"]

#: 版本号段数，米哈游固定为 4 段
VERSION_SEGMENTS = 4

_VERSION_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?$")


@dataclass(frozen=True, order=False)
class GameVersion:
    """不可变、可比较的 4 段版本号。

    ：使用 ``field`` 关键字做惰性解析，并重载了
    ``==`` / ``>`` / ``<`` 等运算符。Python 侧用 ``functools.total_ordering``
    风格的显式富比较方法实现同样语义。
    """

    major: int = 0
    minor: int = 0
    patch: int = 0
    revision: int = 0

    # ------------------------------------------------------------------ 构造

    @classmethod
    def parse(cls, value: "str | int | GameVersion | None") -> Optional["GameVersion"]:
        """宽松解析版本号；无法解析或为空时返回 ``None`` 而非抛异常。

         / 隐式转换运算符。

        Args:
            value: 待解析的值，支持 str（如 ``"5.6.0.0"``）、int、``GameVersion``
                或 None。空串、``None``、以及无法匹配 ``_VERSION_RE`` 的输入一律返回 ``None``。

        Returns:
            解析出的 :class:`GameVersion`，或 ``None``（语义上表示「未安装」/「未知」）。
        """
        if value is None:
            return None
        if isinstance(value, GameVersion):
            return value
        if isinstance(value, int):
            # 极少见：某些 API 用纯数字表示版本
            return cls.from_segments([value])

        text = str(value).strip()
        if not text:
            return None

        match = _VERSION_RE.match(text)
        if match is None:
            return None

        segments = [int(part) for part in match.groups() if part is not None]
        return cls.from_segments(segments)

    @classmethod
    def from_segments(cls, segments: Iterable[int]) -> "GameVersion":
        """用整数序列构造版本号，超过 4 段截断、不足 4 段补 0。

        Args:
            segments: 版本号分段，如 ``[5, 6, 0]`` 或 ``(3, 4)``。

        Returns:
            补齐/截断到 4 段后的 :class:`GameVersion` 实例。
        """
        parts: List[int] = [int(part) for part in segments][:VERSION_SEGMENTS]
        while len(parts) < VERSION_SEGMENTS:
            parts.append(0)
        return cls(*parts)

    @classmethod
    def empty(cls) -> "GameVersion":
        """等价（全 0 版本）。"""
        return cls(0, 0, 0, 0)

    # ------------------------------------------------------------------ 输出

    @property
    def version_string(self) -> str:
        """（``major.minor.patch.revision``）。"""
        return f"{self.major}.{self.minor}.{self.patch}.{self.revision}"

    @property
    def sophon_tag(self) -> str:
        """Sophon 侧的 3 段版本串（``major.minor.patch``）。

        Note:
            分支 ``tag`` 与差分清单 ``stats`` 的基线键都是 3 段形态，拿 4 段的
            `version_string` 去对永远对不上：目标版本会被服务端判 ``-202``，
            差分会被当成不存在。
        """
        return f"{self.major}.{self.minor}.{self.patch}"

    def as_tuple(self) -> Tuple[int, int, int, int]:
        """返回 4 段版本号的整数元组 ``(major, minor, patch, revision)``。"""
        return (self.major, self.minor, self.patch, self.revision)

    def __str__(self) -> str:  # pragma: no cover - 平凡实现
        """等价于 ``version_string``。"""
        return self.version_string

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        """返回可供 ``eval``/调试阅读的 ``GameVersion(x.y.z.w)`` 形式。"""
        return f"GameVersion({self.version_string})"

    def is_empty(self) -> bool:
        """判断是否为全 0 的「空版本」。"""
        return self.as_tuple() == (0, 0, 0, 0)

    # ------------------------------------------------------------------ 比较

    def __eq__(self, other: object) -> bool:
        """相等比较；右操作数经 :func:`GameVersion.parse` 转换后逐段比较。

        Args:
            other: 另一版本，可为 ``GameVersion`` / str / int / None。

        Returns:
            两段版本是否相等；``other`` 为 None 或无法解析时返回 ``NotImplemented``，
            交由 Python 回退到默认对象比较（而非当作不等）。
        """
        other_version = (
            self.parse(other) if not isinstance(other, GameVersion) else other
        )
        if other_version is None:
            return NotImplemented
        return self.as_tuple() == other_version.as_tuple()

    def __hash__(self) -> int:
        """以 4 段元组为哈希键，使相等的版本必然同哈希。"""
        return hash(self.as_tuple())

    def __lt__(self, other: "GameVersion") -> bool:
        """小于比较；右操作数经 :func:`GameVersion.parse` 转换后逐段比较。

        Args:
            other: 另一版本，可为 ``GameVersion`` / str / int / None。
                None 或无法解析的值按 ``GameVersion.Empty`` 处理，故「未安装」小于任何具体版本。

        Returns:
            左操作数是否严格小于 ``other``。
        """
        return self.as_tuple() < _coerce(other).as_tuple()

    def __le__(self, other: "GameVersion") -> bool:
        """小于等于比较；右操作数经 :func:`GameVersion.parse` 转换后逐段比较。

        Args:
            other: 另一版本，可为 ``GameVersion`` / str / int / None。
                None 或无法解析的值按 ``GameVersion.Empty`` 处理。

        Returns:
            左操作数是否小于或等于 ``other``。
        """
        return self.as_tuple() <= _coerce(other).as_tuple()

    def __gt__(self, other: "GameVersion") -> bool:
        """大于比较；右操作数经 :func:`GameVersion.parse` 转换后逐段比较。

        Args:
            other: 另一版本，可为 ``GameVersion`` / str / int / None。
                None 或无法解析的值按 ``GameVersion.Empty`` 处理。

        Returns:
            左操作数是否严格大于 ``other``。
        """
        return self.as_tuple() > _coerce(other).as_tuple()

    def __ge__(self, other: "GameVersion") -> bool:
        """大于等于比较；右操作数经 :func:`GameVersion.parse` 转换后逐段比较。

        Args:
            other: 另一版本，可为 ``GameVersion`` / str / int / None。
                None 或无法解析的值按 ``GameVersion.Empty`` 处理。

        Returns:
            左操作数是否大于或等于 ``other``。
        """
        return self.as_tuple() >= _coerce(other).as_tuple()


def _coerce(other: object) -> GameVersion:
    """把比较运算的右操作数转成 GameVersion。

    None 或无法解析的值按 ``GameVersion.Empty`` 处理，使「未安装」排在任意
    具体版本之下（「未知」排在「已安装」之前）。

    Args:
        other: 比较右操作数，可为 ``GameVersion`` / str / int / None。

    Returns:
        与 ``other`` 等价的 :class:`GameVersion`（不可解析时退化为全 0 空版本）。
    """
    if isinstance(other, GameVersion):
        return other
    parsed = GameVersion.parse(other)
    if parsed is None:
        # 与 None 比较时，任何具体版本都视为「更大」（已安装 > 未安装）
        return GameVersion.empty()
    return parsed
