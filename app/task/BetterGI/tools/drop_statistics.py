#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""BetterGI「奖励识别」日志解析与掉落统计聚合。

BGI 侧对应开关为 ``RewardRecognitionEnabled``（UI：每轮领取后识别奖励名称与数量，
任务结束打印汇总）。开启后每轮领奖会打印一行可解析的掉落明细；**实测（2026-09-14 日志）
明细段被一对 ASCII 双引号包住，首领的来源名也带引号**：

    自动秘境：本轮奖励识别结果 "摩拉 x1000, 大英雄的经验 x5"
    "自动首领讨伐"：本轮奖励识别结果 "冒险家的经验 x2, 摩拉 x800"

本模块只做「把日志行解析成 {物品: 数量}」这一件事；日志文案属上游对外契约
（见 blackbox-boundary.md），上游改文案时解析不到即为空表，不误报。
"""

import re
from typing import Iterable

# 明细行：<来源>：本轮奖励识别结果 <物品> x<数量>, <物品> x<数量>…
# 日志文件里消息独占一行，但仍允许行首带时间戳/logger 前缀，故用 search 而非 match。
_REWARD_LINE = re.compile(
    r"(?P<source>[^：\n]{1,32})：本轮奖励识别结果[ \t　]*(?P<body>[^\n]*)$"
)
# 单个条目：物品名 + 空格 + x + 数量（物品名允许含空格，如「大英雄的经验」）
_ITEM = re.compile(r"(?P<name>[^,，\n]+?)\s*[xX×]\s*(?P<count>\d+)")
# 明细段两侧的包裹引号。只剥引号类字符：物品名本身可能以「开头（如「久雨莲」的种子），
# 把「」一并计入会破坏名字。不剥则首条物品名带引号（`"摩拉`），且同一物品处于首位/非首位
# 时会被拆成两个键、数量合不到一起。
_QUOTES = "\"'“”"

# 空结果提示（BGI 在没识别到奖励时打印，不产生条目）
_EMPTY_MARK = "本轮奖励识别结果为空"


def parse_drop_lines(lines: Iterable[str]) -> dict[str, int]:
    """把日志行里的掉落明细解析为 ``{物品名: 数量}``（跨轮、跨来源累加）。

    Args:
        lines: 日志行序列（可以带时间戳/logger 前缀）。

    Returns:
        按物品汇总的数量表；没有任何掉落行时返回空字典。
    """

    totals: dict[str, int] = {}
    for raw in lines:
        if not raw or _EMPTY_MARK in raw:
            continue
        matched = _REWARD_LINE.search(raw)
        if matched is None:
            continue
        for item in _ITEM.finditer(matched.group("body")):
            name = item.group("name").strip().strip(_QUOTES)
            if not name:
                continue
            totals[name] = totals.get(name, 0) + int(item.group("count"))
    return totals


def format_drop_statistics(statistics: dict[str, int] | None) -> str:
    """把掉落统计渲染成通知正文段落（「物品: 数量」逐行，数量降序）。"""

    if not statistics:
        return ""
    lines = ["【掉落统计】"]
    for name, count in sorted(
        statistics.items(), key=lambda kv: (-kv[1], kv[0])
    ):
        lines.append(f"{name}: {count}")
    return "\n".join(lines)
