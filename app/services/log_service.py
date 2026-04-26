#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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

from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal

from app.utils import get_logger
from app.utils.constants import UTC4

logger = get_logger("日志服务")


class LogService:
    """Handles log saving, statistic merging, history search, and cleanup."""

    def __init__(self, history_path: Path) -> None:
        self._history_path = history_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _save_simple_log(
        log_path: Path,
        logs: list[str],
        result_key: str,
        result_value: str,
    ) -> None:
        """
        Shared implementation for simple log types (MaaEnd, SRC, General).

        Writes the concatenated log lines to ``log_path.with_suffix('.log')``
        and a minimal JSON statistics file next to it.

        Args:
            log_path: Base path (suffix will be replaced).
            logs: Raw log lines.
            result_key: JSON key for the result (e.g. ``"src_result"``).
            result_value: Result label for this run.
        """
        data: Dict[str, str] = {result_key: result_value}

        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.with_suffix(".log").write_text("".join(logs), encoding="utf-8")
        log_path.with_suffix(".json").write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def save_maa_log(
        self, log_path: Path, logs: list[str], maa_result: str
    ) -> bool:
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

        data: dict[str, Any] = {
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

        # 掉落统计
        # 存储所有关卡的掉落统计
        all_stage_drops: dict[str, dict[str, int]] = {}

        # 查找所有Fight任务的开始和结束位置
        fight_tasks: list[tuple[int, int]] = []
        for i, line in enumerate(logs):
            if "开始任务: Fight" in line or "开始任务: 理智作战" in line:
                # 查找对应的任务结束位置
                end_index = -1
                for j in range(i + 1, len(logs)):
                    if "完成任务: Fight" in logs[j] or "完成任务: 理智作战" in logs[j]:
                        end_index = j
                        break
                    # 如果遇到新的Fight任务开始, 则当前任务没有正常结束
                    if j < len(logs) and (
                        "开始任务: Fight" in logs[j] or "开始任务: 理智作战" in logs[j]
                    ):
                        break

                # 如果找到了结束位置, 记录这个任务的范围
                if end_index != -1:
                    fight_tasks.append((i, end_index))

        # 处理每个Fight任务
        for start_idx, end_idx in fight_tasks:
            # 提取当前任务的日志
            task_logs = logs[start_idx : end_idx + 1]

            # 查找任务中的最后一次掉落统计
            last_drop_stats: dict[str, int] = {}
            current_stage = None

            for line in task_logs:
                # 匹配掉落统计行, 如"1-7 掉落统计:"
                drop_match = re.search(r"([\u4e00-\u9fffA-Za-z0-9\-]+) 掉落统计:", line)
                if drop_match:
                    # 发现新的掉落统计, 重置当前关卡的掉落数据
                    current_stage = drop_match.group(1)
                    last_drop_stats = {}
                    continue

                # 如果已经找到了关卡, 处理掉落物
                if current_stage:
                    item_match: List[str] = re.findall(
                        r"^(?!\[)(\S+?)\s*:\s*([\d,]+[kK]?)(?:\s*\(\+[\d,]+[kK]?\))?",
                        line,
                        re.M,
                    )
                    for item, total in item_match:
                        total = total.replace(",", "")
                        if total.lower().endswith("k"):
                            total = int(total[:-1]) * 1000
                        else:
                            total = int(total)

                        # 黑名单
                        if item not in [
                            "当前次数",
                            "理智",
                            "最快截图耗时",
                            "专精等级",
                            "剩余时间",
                        ]:
                            last_drop_stats[item] = total

            # 如果任务中有掉落统计, 更新总统计
            if current_stage and last_drop_stats:
                if current_stage not in all_stage_drops:
                    all_stage_drops[current_stage] = {}

                # 累加掉落数据
                for item, count in last_drop_stats.items():
                    all_stage_drops[current_stage].setdefault(item, 0)
                    all_stage_drops[current_stage][item] += count

        # 将累加后的掉落数据保存到结果中
        data["drop_statistics"] = all_stage_drops

        # 保存日志
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("".join(logs), encoding="utf-8")
        # 保存统计数据
        log_path.with_suffix(".json").write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )

        logger.success(f"MAA 日志统计完成, 日志路径: {log_path}")

        return if_six_star

    async def save_maaend_log(
        self, log_path: Path, logs: list[str], maaend_result: str
    ) -> None:
        """
        Save MaaEnd logs and generate basic statistics data.

        Args:
            log_path (Path): Target log file path.
            logs (list[str]): Log lines.
            maaend_result (str): Result label for this run.
        """

        logger.info(
            f"开始处理MaaEnd日志, 日志长度: {len(logs)}, 日志标记: {maaend_result}"
        )

        self._save_simple_log(log_path, logs, "maaend_result", maaend_result)

        logger.success(f"MaaEnd日志统计完成, 日志路径: {log_path.with_suffix('.log')}")

    async def save_src_log(
        self, log_path: Path, logs: list[str], src_result: str
    ) -> None:
        """
        保存SRC日志并生成对应统计数据

        Args:
            log_path (Path): 日志文件保存路径
            logs (list): 日志内容列表
            src_result (str): 待保存的日志结果信息
        """

        logger.info(f"开始处理SRC日志, 日志长度: {len(logs)}, 日志标记: {src_result}")

        self._save_simple_log(log_path, logs, "src_result", src_result)

        logger.success(f"SRC日志统计完成, 日志路径: {log_path.with_suffix('.log')}")

    async def save_general_log(
        self, log_path: Path, logs: list[str], general_result: str
    ) -> None:
        """
        保存通用日志并生成对应统计数据

        :param log_path: 日志文件保存路径
        :param logs: 日志内容列表
        :param general_result: 待保存的日志结果信息
        """

        logger.info(
            f"开始处理通用日志, 日志长度: {len(logs)}, 日志标记: {general_result}"
        )

        self._save_simple_log(log_path, logs, "general_result", general_result)

        logger.success(f"通用日志统计完成, 日志路径: {log_path.with_suffix('.log')}")

    async def merge_statistic_info(
        self, statistic_path_list: List[Path]
    ) -> dict[str, Any]:
        """
        合并指定数据统计信息文件

        Args:
            statistic_path_list (List[Path]): 数据统计信息文件列表

        Returns:
            dict: 合并后的数据统计信息
        """

        data: Dict[str, Any] = {"index": {}}

        for json_file in statistic_path_list:
            try:
                single_data = json.loads(json_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(
                    f"无法解析文件 {json_file}, 错误信息: {type(e).__name__}: {str(e)}"
                )
                continue

            for key in single_data.keys():
                if key not in data:
                    data[key] = {}

                # 合并公招统计
                if key == "recruit_statistics":
                    for star_level, count in single_data[key].items():
                        if star_level not in data[key]:
                            data[key][star_level] = 0
                        data[key][star_level] += count

                # 合并掉落统计
                elif key == "drop_statistics":
                    for stage, drops in single_data[key].items():
                        if stage not in data[key]:
                            data[key][stage] = {}  # 初始化关卡

                        for item, count in drops.items():
                            if item not in data[key][stage]:
                                data[key][stage][item] = 0
                            data[key][stage][item] += count

                # 处理理智相关字段 - 使用最后一个文件的值
                elif key in ["sanity", "sanity_full_at"]:
                    data[key] = single_data[key]

                # 录入运行结果
                elif key in [
                    "maa_result",
                    "maaend_result",
                    "src_result",
                    "general_result",
                ]:
                    actual_date = (
                        datetime.strptime(
                            f"{json_file.parent.parent.name} {json_file.stem}",
                            "%Y-%m-%d %H-%M-%S",
                        )
                        .replace(tzinfo=UTC4)
                        .astimezone()
                    )

                    if single_data[key] != "Success!":
                        if "error_info" not in data:
                            data["error_info"] = {}
                        data["error_info"][
                            actual_date.strftime("%Y-%m-%d %H:%M:%S")
                        ] = single_data[key]

                    data["index"][actual_date] = {
                        "date": actual_date.strftime("%Y-%m-%d %H:%M:%S"),
                        "status": (
                            "DONE" if single_data[key] == "Success!" else "ERROR"
                        ),
                        "jsonFile": str(json_file),
                    }

        data["index"] = [data["index"][_] for _ in sorted(data["index"])]

        # 确保返回的字典始终包含 index 字段，即使为空
        result = {k: v for k, v in data.items() if v}
        if "index" not in result:
            result["index"] = []

        return result

    async def search_history(
        self,
        mode: Literal["DAILY", "WEEKLY", "MONTHLY"],
        start_date: date,
        end_date: date,
    ) -> dict[str, dict[str, list[Path]]]:
        """
        搜索指定时间范围内的历史记录

        Args:
            mode (Literal["DAILY", "WEEKLY", "MONTHLY"]): 合并模式
            start_date (date): 开始日期
            end_date (date): 结束日期
        """

        logger.info(
            f"开始搜索历史记录, 合并模式: {mode}, 日期范围: {start_date} 至 {end_date}"
        )

        history_dict: dict[str, dict[str, list[Path]]] = {}

        for date_folder in self._history_path.iterdir():
            if not date_folder.is_dir():
                continue  # 只处理日期文件夹

            try:
                folder_date = datetime.strptime(date_folder.name, "%Y-%m-%d").date()

                if not (start_date <= folder_date <= end_date):
                    continue  # 只统计在范围内的日期

                if mode == "DAILY":
                    date_name = folder_date.strftime("%Y-%m-%d")
                elif mode == "WEEKLY":
                    date_name = folder_date.strftime("%G-W%V")
                elif mode == "MONTHLY":
                    date_name = folder_date.strftime("%Y-%m")
                else:
                    raise ValueError("无效的合并模式")

                if date_name not in history_dict:
                    history_dict[date_name] = {}

                for user_folder in date_folder.iterdir():
                    if not user_folder.is_dir():
                        continue  # 只处理用户文件夹

                    if user_folder.stem not in history_dict[date_name]:
                        history_dict[date_name][user_folder.stem] = list(
                            user_folder.with_suffix("").glob("*.json")
                        )
                    else:
                        history_dict[date_name][user_folder.stem] += list(
                            user_folder.with_suffix("").glob("*.json")
                        )

            except ValueError as e:
                logger.warning(f"非日期格式的目录: {date_folder}, 错误: {e}")

        logger.success(f"历史记录搜索完成, 共计 {len(history_dict)} 条记录")

        return {
            k: v
            for k, v in sorted(history_dict.items(), key=lambda kv: kv[0], reverse=True)
        }

    async def clean_old_history(self, retention_days: int) -> None:
        """删除超过用户设定天数的历史记录文件（基于目录日期）

        Args:
            retention_days: Number of days to retain. ``0`` means keep forever.
        """

        if retention_days == 0:
            logger.info("历史记录永久保留, 跳过历史记录清理")
            return

        logger.info("开始清理超过设定天数的历史记录")

        deleted_count = 0

        for date_folder in self._history_path.iterdir():
            if not date_folder.is_dir():
                continue  # 只处理日期文件夹

            try:
                # 只检查 `YYYY-MM-DD` 格式的文件夹
                folder_date = datetime.strptime(date_folder.name, "%Y-%m-%d").date()
                if datetime.now(tz=UTC4).date() - folder_date > timedelta(
                    days=retention_days
                ):
                    shutil.rmtree(date_folder, ignore_errors=True)
                    deleted_count += 1
                    logger.debug(f"已删除超期日志目录: {date_folder}")
            except ValueError:
                logger.warning(f"非日期格式的目录: {date_folder}")

        logger.success(f"清理完成: {deleted_count} 个日期目录")
