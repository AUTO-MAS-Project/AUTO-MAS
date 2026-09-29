#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""MAA 运行日志的统计与落盘。

MAA 日志的格式（理智、公招、关卡掉落行）与统计产物都是 MAA 领域知识，
从 app/core/config.py 迁入本模块，由 MAA 专项自己维护。
"""

import json
import re
from collections import defaultdict
from pathlib import Path

from app.utils import get_logger

logger = get_logger("MAA 日志统计")


def _parse_drop_count(text: str) -> int:
    """把 MAA 掉落行中的数量换算成整数。

    MAA 对较大数量输出 ``1.5k``（≥1 万）与 ``1.2M``（≥100 万）缩写（不区分
    大小写），其余为 ``864`` 或 ``9,999`` 形态。

    Args:
        text: 掉落行中的数量原文。

    Returns:
        换算后的整数数量。
    """

    text = text.replace(",", "")
    multiplier = 1
    if text[-1:] in ("k", "K"):
        multiplier, text = 1000, text[:-1]
    elif text[-1:] in ("m", "M"):
        multiplier, text = 1_000_000, text[:-1]
    return round(float(text) * multiplier)


def _parse_drop_statistics(logs: list[str]) -> dict[str, dict[str, int]]:
    """按理智任务边界解析 MAA 日志中的关卡掉落统计。

    Args:
        logs: MAA 日志行列表。

    Returns:
        按关卡汇总的掉落统计。
    """

    target_task_names = {
        "Fight",
        "理智作战",
        "活动关优先",
        "库存保持",
        "养成计划",
    }
    annihilation_markers = ("剿灭", "剿滅", "Annihilation", "殲滅", "섬멸")
    fight_start_markers = (
        "开始任务: Fight",
        "开始任务: 理智作战",
        "Start Task Chain: Fight",
    )
    # 库存保持/养成计划在同一个任务项里按 plan 拼接多条独立 Fight 链，MAA 为
    # 区分日志给每条链的完成行追加 " #N" 序号后缀（语言无关）；裸任务名只出现在
    # 识别链的括号后缀里，剥掉序号后缀再与目标名比对，否则这些链会被整体漏掉。
    multi_chain_suffix = re.compile(r"\s+#\d+$")

    def is_task_boundary(line: str) -> bool:
        return "完成任务:" in line or "Completed Task Chain:" in line

    def get_completed_task_name(line: str) -> str | None:
        match = re.search(r"完成任务:\s*([^\r\n]+)", line)
        if match is not None:
            name = multi_chain_suffix.sub("", match.group(1).strip())
            return name or None

        match = re.search(r"Completed Task Chain:\s*([^,\r\n]+)", line)
        if match is None:
            return None
        return match.group(1).strip() or None

    task_ranges: list[tuple[int, int]] = []
    for end_index, line in enumerate(logs):
        task_name = get_completed_task_name(line)
        if task_name not in target_task_names:
            continue

        previous_boundary = max(
            (
                index
                for index, item in enumerate(logs[:end_index])
                if is_task_boundary(item)
            ),
            default=-1,
        )
        start_candidates = [
            index
            for index, item in enumerate(logs[:end_index])
            if index > previous_boundary
            and any(marker in item for marker in fight_start_markers)
        ]
        start_index = max(start_candidates, default=previous_boundary + 1)

        if task_name == "Fight" and any(
            marker in item
            for item in logs[start_index : end_index + 1]
            for marker in annihilation_markers
        ):
            continue

        task_ranges.append((start_index, end_index))

    all_stage_drops: dict[str, dict[str, int]] = {}
    for start_index, end_index in task_ranges:
        current_stage = None
        last_drop_stats: dict[str, int] = {}

        for line in logs[start_index : end_index + 1]:
            drop_match = re.search(r"([\u4e00-\u9fffA-Za-z0-9\-]+) 掉落统计:", line)
            if drop_match:
                current_stage = drop_match.group(1)
                last_drop_stats = {}
                continue

            if not current_stage:
                continue

            item_match: list[tuple[str, str]] = re.findall(
                r"^(?!\[)(\S+?)\s*:\s*([\d,]+(?:\.\d+)?[kKmM]?)(?:\s*\(\+[\d,]+(?:\.\d+)?[kKmM]?\))?",
                line,
                re.M,
            )
            for item, total in item_match:
                total = _parse_drop_count(total)

                if item not in [
                    "当前次数",
                    "理智",
                    "最快截图耗时",
                    "专精等级",
                    "剩余时间",
                ]:
                    last_drop_stats[item] = total

        if current_stage and last_drop_stats:
            stage_drops = all_stage_drops.setdefault(current_stage, {})
            for item, count in last_drop_stats.items():
                stage_drops[item] = stage_drops.get(item, 0) + count

    return all_stage_drops


async def save_maa_log(log_path: Path, logs: list, maa_result: str) -> bool:
    """
    保存MAA日志并生成对应统计数据

    Args:
        log_path (Path): 日志文件保存路径
        logs (list): 日志列表
        maa_result (str): MAA任务结果
    Returns:
        bool: 是否存在高资
    """

    logger.info(f"开始处理 MAA 日志, 日志长度: {len(logs)}, 日志标记: {maa_result}")

    data = {
        "recruit_statistics": defaultdict(int),
        "drop_statistics": defaultdict(dict),
        "sanity": 0,
        "sanity_full_at": "",
        "maa_result": maa_result,
    }

    if_six_star = False

    # 提取理智相关信息
    for log_line in logs:
        # 提取当前理智值：理智: 5/180
        sanity_match = re.search(r"理智:\s*(\d+)/\d+", log_line)
        if sanity_match:
            data["sanity"] = int(sanity_match.group(1))

        # 提取理智回满时间：理智将在 2025-09-26 18:57 回满。(17h 29m 后)
        sanity_full_match = re.search(
            r"(理智将在\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s*回满。\(\d+h\s+\d+m\s+后\))",
            log_line,
        )
        if sanity_full_match:
            data["sanity_full_at"] = sanity_full_match.group(1)

    # 公招统计（仅统计招募到的）
    confirmed_recruit = False
    current_star_level = None
    i = 0
    while i < len(logs):
        if "公招识别结果:" in logs[i]:
            current_star_level = None  # 每次识别公招时清空之前的星级
            i += 1
            while i < len(logs) and "Tags" not in logs[i]:  # 读取所有公招标签
                i += 1

            if i < len(logs) and "Tags" in logs[i]:  # 识别星级
                star_match = re.search(r"(\d+)\s*★ Tags", logs[i])
                if star_match:
                    current_star_level = f"{star_match.group(1)}★"
                    if current_star_level == "6★":
                        if_six_star = True

        if "已确认招募" in logs[i]:  # 只有确认招募后才统计
            confirmed_recruit = True

        if confirmed_recruit and current_star_level:
            data["recruit_statistics"][current_star_level] += 1
            confirmed_recruit = False  # 重置, 等待下一次公招
            current_star_level = None  # 清空已处理的星级

        i += 1

    # 掉落统计收集所有由理智任务产生的有效 Fight 任务链，包括活动关优先
    # 和库存保持任务。
    data["drop_statistics"] = _parse_drop_statistics(logs)

    # 保存日志
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("".join(logs), encoding="utf-8")
    # 保存统计数据
    log_path.with_suffix(".json").write_text(
        json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
    )

    logger.success(f"MAA 日志统计完成, 日志路径: {log_path}")

    return if_six_star
