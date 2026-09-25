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

"""路径工具 —— 把「远端可控的相对路径」安全地落到本地目录里。

要落盘哪些文件、叫什么名字，全部来自服务端下发的清单字符串：Sophon 主清单里每个
asset 的本地路径、差分清单里的目标文件名与待删除文件名。任何一条写成绝对路径或
带 ``..``，就会写到游戏目录外面。收口只有一处：先按分量校验，再用
:func:`os.path.commonpath` 判是否仍在根内，越界即拒。
"""

from __future__ import annotations

import os
import re

__all__ = ["UnsafePathError", "split_rel_path", "safe_join"]

#: Windows 盘符前缀（``C:`` / ``c:``），也用来清洗 ``a/C:x`` 这类中间段
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class UnsafePathError(ValueError):
    """相对路径越界或形态非法 —— 调用方应当拒绝该条目，不要写入任何文件。"""


def split_rel_path(rel_path: str) -> list[str]:
    """把远端下发的相对路径清洗成安全的段列表。

    Args:
        rel_path: 原始相对路径；分隔符可以是 ``/`` 或 ``\\``，可以带前导斜杠。

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

    Args:
        root: 目标根目录（游戏安装目录、暂存目录等）。
        rel_path: 远端下发的相对路径。

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
