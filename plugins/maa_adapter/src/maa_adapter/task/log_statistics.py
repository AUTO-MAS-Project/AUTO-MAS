"""MAA 运行日志统计（纯内存解析，不落盘）。"""

from __future__ import annotations

import re
from collections import defaultdict

from auto_mas_core.utils import get_logger

logger = get_logger("MAA 日志统计")


def _parse_drop_count(text: str) -> int:
    text = text.replace(",", "")
    multiplier = 1
    if text[-1:] in ("k", "K"):
        multiplier, text = 1000, text[:-1]
    elif text[-1:] in ("m", "M"):
        multiplier, text = 1_000_000, text[:-1]
    return round(float(text) * multiplier)


def _parse_drop_statistics(logs: list[str]) -> dict[str, dict[str, int]]:
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


def parse_maa_log(logs: list[str], maa_result: str) -> tuple[dict, bool]:
    """解析 MAA 日志正文，返回 (统计 dict, 是否公招六星)。"""

    logger.info(f"开始处理 MAA 日志, 日志长度: {len(logs)}, 日志标记: {maa_result}")

    data: dict = {
        "recruit_statistics": defaultdict(int),
        "drop_statistics": defaultdict(dict),
        "sanity": 0,
        "sanity_full_at": "",
        "maa_result": maa_result,
    }
    if_six_star = False

    for log_line in logs:
        sanity_match = re.search(r"理智:\s*(\d+)/\d+", log_line)
        if sanity_match:
            data["sanity"] = int(sanity_match.group(1))
        sanity_full_match = re.search(
            r"(理智将在\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s*回满。\(\d+h\s+\d+m\s+后\))",
            log_line,
        )
        if sanity_full_match:
            data["sanity_full_at"] = sanity_full_match.group(1)

    confirmed_recruit = False
    current_star_level = None
    i = 0
    while i < len(logs):
        if "公招识别结果:" in logs[i]:
            current_star_level = None
            i += 1
            while i < len(logs) and "Tags" not in logs[i]:
                i += 1
            if i < len(logs) and "Tags" in logs[i]:
                star_match = re.search(r"(\d+)\s*★ Tags", logs[i])
                if star_match:
                    current_star_level = f"{star_match.group(1)}★"
                    if current_star_level == "6★":
                        if_six_star = True
        if "已确认招募" in logs[i]:
            confirmed_recruit = True
        if confirmed_recruit and current_star_level:
            data["recruit_statistics"][current_star_level] += 1
            confirmed_recruit = False
            current_star_level = None
        i += 1

    data["drop_statistics"] = _parse_drop_statistics(logs)
    data["recruit_statistics"] = dict(data["recruit_statistics"])
    data["drop_statistics"] = {
        k: dict(v) for k, v in data["drop_statistics"].items()
    }
    return data, if_six_star
