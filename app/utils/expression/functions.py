"""内置函数实现

每个函数接收 (text, args) 并返回处理后的字符串。
函数注册在 FUNCTIONS 字典中，供 evaluator 调用。

函数清单：cut / get / sub / cutby / subby / replace / trim / upper / lower
"""

from __future__ import annotations

from typing import Callable, Union

# 函数参数类型
Arg = Union[str, int]


def _find_nth(text: str, marker: str, nth: int, start: int = 0) -> int:
    """按出现序号查找 marker 的位置（非重叠计数）

    nth 正数表示第 nth 次出现（1 起），负数表示倒数第 |nth| 次出现（-1 为最后一次），
    0 视为 1。未找到时返回 -1。
    """

    if nth == 0:
        nth = 1
    if nth > 0:
        pos = start - 1
        for _ in range(nth):
            pos = text.find(marker, pos + 1)
            if pos == -1:
                return -1
        return pos
    positions: list[int] = []
    pos = text.find(marker, start)
    while pos != -1:
        positions.append(pos)
        pos = text.find(marker, pos + 1)
    return positions[nth] if len(positions) >= -nth else -1


def fn_cut(text: str, args: list[Arg]) -> str:
    """cut(num) — 切除指定数量的字符

    - num > 0：切除开头 num 个字符
    - num < 0：切除结尾 |num| 个字符
    """
    if len(args) < 1:
        raise ValueError("cut 需要一个参数: cut(num)")
    num = int(args[0])
    if num == 0:
        return text
    if num > 0:
        return text[num:]
    return text[:num]


def fn_get(text: str, args: list[Arg]) -> str:
    """get(num) — 保留指定数量的字符

    - num > 0：保留开头 num 个字符
    - num < 0：保留结尾 |num| 个字符
    """
    if len(args) < 1:
        raise ValueError("get 需要一个参数: get(num)")
    num = int(args[0])
    if num == 0:
        return ""
    if num > 0:
        return text[:num]
    return text[num:]


def fn_sub(text: str, args: list[Arg]) -> str:
    """sub(start, end) — 提取两个位置之间的子文本

    位置从 1 开始计数，负数表示从末尾倒数。
    """
    if len(args) < 2:
        raise ValueError("sub 需要两个参数: sub(start, end)")
    start = int(args[0])
    end = int(args[1])
    length = len(text)

    # 将 1-based 位置转为 0-based 索引
    if start > 0:
        start_idx = start - 1
    elif start < 0:
        start_idx = length + start
    else:
        return ""

    if end > 0:
        end_idx = end
    elif end < 0:
        end_idx = length + end + 1
    else:
        return ""

    return text[start_idx:end_idx]


def fn_cutby(text: str, args: list[Arg]) -> str:
    """cutby("定位文本", direction, keep, nth) — 按文本定位截断

    - direction: 0=向前切割（去头），1=向后切割（去尾）。默认 0
    - keep: 0=保留定位文本，1=删除定位文本。默认 0
    - nth: 定位文本的出现序号，正数=第 nth 次（1 起），负数=倒数第 |nth| 次
      （-1 为最后一次）。默认 1。用于同名分隔符（如多个 `]`）需要定位
      最后一个的场景。
    """
    if len(args) < 1:
        raise ValueError(
            'cutby 至少需要一个参数: cutby("文本", direction, keep, nth)'
        )
    marker = str(args[0])
    direction = int(args[1]) if len(args) > 1 else 0
    keep = int(args[2]) if len(args) > 2 else 0
    nth = int(args[3]) if len(args) > 3 else 1

    pos = _find_nth(text, marker, nth)
    if pos == -1:
        return text

    if direction == 0:
        # 向前切割：去掉定位文本之前的内容
        if keep == 0:
            return text[pos:]
        return text[pos + len(marker):]
    else:
        # 向后切割：去掉定位文本之后的内容
        if keep == 0:
            return text[: pos + len(marker)]
        return text[:pos]


def fn_subby(text: str, args: list[Arg]) -> str:
    """subby("首位文本", "末位文本", keepFirst, keepLast, nthFirst, nthLast) — 提取两段文本之间的内容

    - keepFirst: 0=保留首位文本，1=删除首位文本。默认 0
    - keepLast: 0=保留末位文本，1=删除末位文本。默认 0
    - nthFirst: 首位文本的出现序号（正数第 n 次 / 负数倒数）。默认 1
    - nthLast: 末位文本在首位之后的出现序号（正数第 n 次 / 负数倒数，-1 为
      首位之后最后一个）。默认 1
    """
    if len(args) < 2:
        raise ValueError(
            'subby 需要至少两个参数: subby("首位文本", "末位文本", keepFirst, keepLast, nthFirst, nthLast)'
        )
    first = str(args[0])
    second = str(args[1])
    keep_first = int(args[2]) if len(args) > 2 else 0
    keep_last = int(args[3]) if len(args) > 3 else 0
    nth_first = int(args[4]) if len(args) > 4 else 1
    nth_last = int(args[5]) if len(args) > 5 else 1

    first_pos = _find_nth(text, first, nth_first)
    if first_pos == -1:
        return text
    second_pos = _find_nth(text, second, nth_last, first_pos + len(first))
    if second_pos == -1:
        return text

    if keep_first == 0:
        start = first_pos
    else:
        start = first_pos + len(first)

    if keep_last == 0:
        end = second_pos + len(second)
    else:
        end = second_pos

    return text[start:end]


def fn_replace(text: str, args: list[Arg]) -> str:
    """replace("old", "new") — 将 old 替换为 new"""
    if len(args) < 2:
        raise ValueError('replace 需要两个参数: replace("old", "new")')
    return text.replace(str(args[0]), str(args[1]))


def fn_trim(text: str, args: list[Arg]) -> str:
    """trim() — 去除首尾空白字符"""
    return text.strip()


def fn_upper(text: str, args: list[Arg]) -> str:
    """upper() — 转大写"""
    return text.upper()


def fn_lower(text: str, args: list[Arg]) -> str:
    """lower() — 转小写"""
    return text.lower()


# ==================== 函数注册表 ====================

FUNCTIONS: dict[str, Callable[[str, list[Arg]], str]] = {
    "cut": fn_cut,
    "get": fn_get,
    "sub": fn_sub,
    "cutby": fn_cutby,
    "subby": fn_subby,
    "replace": fn_replace,
    "trim": fn_trim,
    "upper": fn_upper,
    "lower": fn_lower,
}


def apply_function(name: str, args: list[Arg], text: str) -> str:
    """调用内置函数

    Args:
        name: 函数名
        args: 参数列表
        text: 输入文本

    Returns:
        处理后的文本

    Raises:
        ValueError: 函数不存在或参数不合法
    """
    func = FUNCTIONS.get(name)
    if func is None:
        raise ValueError(f"未知函数: {name}")
    return func(text, args)
