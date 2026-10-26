"""MaaEnd 用户可见日志中的统计解析。"""

import re
from html import unescape
from typing import Optional


def parse_maaend_failed_tasks(logs: list[str]) -> list[str]:
    """
    解析MaaEnd失败任务名称

    Args:
        logs (list[str]): 日志列表

    Returns:
        list[str]: 失败任务名称列表
    """

    failed_tasks: list[str] = []
    ignored_tasks = {"停止任务", "⛔ 结束进程", "__MXU_KILLPROC__", "StopTask"}

    for log_line in logs:
        match = re.search(r"任务失败:\s*(.+)", log_line)
        if match is None:
            continue

        task_name = match.group(1).strip()
        if (
            task_name
            and task_name not in ignored_tasks
            and task_name not in failed_tasks
        ):
            failed_tasks.append(task_name)

    return failed_tasks


def parse_maaend_matrix_statistics(
    logs: list[str],
) -> tuple[Optional[dict[str, str]], bool]:
    """
    解析MaaEnd基质刷取统计

    Args:
        logs (list[str]): 日志列表

    Returns:
        tuple[Optional[dict[str, str]], bool]: 基质统计数据与是否识别到基质流程
    """

    matrix_statistics: dict[str, str] = {}
    pending_statistics: dict[str, str] = {}
    current_matrix_skill = ""
    has_matrix_flow = False
    locked_count = 0

    for log_line in logs:
        text = unescape(re.sub(r"<[^>]*>", "", log_line)).strip()
        if re.search(r"任务(?:开始|完成|失败)[:：]", text):
            pending_statistics = {}
            current_matrix_skill = ""
            continue

        skill_match = re.search(r"OCR到技能[:：]\s*(.+)", text)
        if skill_match:
            current_matrix_skill = skill_match.group(1).strip()
            continue

        weapon_match = re.search(r"匹配到武器[:：]\s*(.+)", text)
        rule_match = re.search(r"扩展规则命中并锁定[:：]\s*(.+)", text)
        if current_matrix_skill and (weapon_match or rule_match):
            if weapon_match:
                pending_statistics[current_matrix_skill] = weapon_match.group(1).strip()
            elif rule_match:
                pending_statistics[current_matrix_skill] = (
                    f"扩展规则：{rule_match.group(1).strip()}"
                )
            current_matrix_skill = ""
            continue

        if "未匹配到目标技能组合" in text or "扩展规则命中（不操作）" in text:
            current_matrix_skill = ""
            continue

        completed_match = re.search(
            r"筛选完成[！!]\s*(?:共[历遍]+物品[:：]\s*\d+[，,]\s*)?"
            r"确认锁定物品[:：]\s*(\d+)",
            text,
        )
        if completed_match is None:
            continue

        has_matrix_flow = True
        current_locked_count = int(completed_match.group(1))
        locked_count += current_locked_count
        if current_locked_count > 0:
            # 武器匹配与扩展规则均由上游明确报告，不按总数反推某几条被锁定。
            matrix_statistics.update(pending_statistics)

        pending_statistics = {}
        current_matrix_skill = ""

    if not has_matrix_flow:
        return None, False

    if locked_count == 0:
        return {}, True

    return (matrix_statistics or None), True


def parse_maaend_pull_count_statistics(logs: list[str]) -> Optional[dict[str, int]]:
    """解析 MaaEnd 抽数计算任务输出的统计结果。"""

    content = "".join(logs)
    field_patterns = {
        "resource_pulls": (
            r'"ResourcePulls"\s*:\s*(\d+)',
            r"资源折算[：:]\s*(\d+)\s*抽",
        ),
        "carry_over_pulls": (
            r'"CarryToNextPulls"\s*:\s*(\d+)',
            r"可留到下版本的券[：:]\s*(\d+)\s*抽",
        ),
        "next_pool_shop_pulls": (
            r'"NextPoolShopPulls"\s*:\s*(\d+)',
            r"下版本商店[：:]\s*(\d+)\s*抽",
        ),
        "next_pool_signin_pulls": (
            r'"NextPoolSigninPulls"\s*:\s*(\d+)',
            r"下版本签到[：:]\s*(\d+)\s*抽",
        ),
        "current_pool_total": (
            r'"CurrentPoolTotal"\s*:\s*(\d+)',
            r"当前池可用[：:]\s*(\d+)\s*抽",
        ),
        "next_pool_total": (
            r'"NextPoolTotal"\s*:\s*(\d+)',
            r"下版本池子总计[：:]\s*(\d+)\s*抽",
        ),
    }

    statistics: dict[str, int] = {}
    for field, patterns in field_patterns.items():
        matches = [
            match for pattern in patterns for match in re.finditer(pattern, content)
        ]
        if matches:
            statistics[field] = int(matches[-1].group(1))

    return statistics if len(statistics) == len(field_patterns) else None


def parse_maaend_statistics(logs: list[str]) -> dict:
    """仅返回日志明确提供的统计，不推断执行成败。"""
    data = {}
    matrix, has_matrix_flow = parse_maaend_matrix_statistics(logs)
    if has_matrix_flow and matrix is not None:
        data["matrix_statistics"] = matrix
    pulls = parse_maaend_pull_count_statistics(logs)
    if pulls is not None:
        data["pull_count_statistics"] = pulls
    return data
