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


import re

from auto_mas_core.host.core_notify_task_content import (
    prepare_screenshot_images as prepare_screenshot_images,
)
from auto_mas_core.host.core_notify_task_content import (
    screenshot_entries as screenshot_entries,
)
from auto_mas_core.host.models_task import LogRecord
from auto_mas_core.host.utils import get_logger

from maa_adapter.constants import _MAA_CULTIVATE_TASK_NAME

logger = get_logger("MAA")

_ANNIHILATION_PROGRESS_RE = re.compile(
    r"(?:剿灭模式|剿滅模式|Annihilation(?: Mode| weekly limit)|殲滅作戦|섬멸 모드)\s*[:：]\s*(\d+)\s*/\s*(\d+)",
    re.IGNORECASE,
)


_MAA_SANITY_RECOGNITION_RE = re.compile(r"理智\s*[:：]\s*\d+\s*/\s*\d+")


# MAA 走到能看到理智的界面（进到副本门口）后，gui.log 才会出现无时间戳的
# 「理智: X/Y」识别行（v6.17.5 国服实测，繁服同字）；其余界面语言样本未核实，
# 命中不到时一律视为未进入战斗流程。
_MAA_SANITY_COMPLETION_MARKERS = (
    "完成任务: 理智任务",
    "完成任务: 活动关均衡理智",
    "完成任务: 库存保持与干员养成",
    "完成任务: 理智作战",
    "完成任务: 活动关优先",
    "完成任务: 活动库存保持",
    "完成任务: 库存保持",
    "完成任务: 养成计划",
)


_MAA_FIGHT_COMPLETION_MARKER = "Completed Task Chain: Fight"


_MAA_TASK_FAILURE_MARKERS = (
    "任务已完成，但出现错误！",
    "任务已结束，以下任务出现错误",
)


_MAA_SANITY_TASK_NAMES = {
    "Fight": ("理智任务", "理智作战", "剿灭作战"),
    "DepotMaintain": ("库存保持与干员养成", "库存保持", _MAA_CULTIVATE_TASK_NAME),
    "EventDepotMaintain": ("活动关均衡理智", "活动库存保持"),
}


def _has_maa_task_failure(log: str) -> bool:
    """检查 MAA 已输出的日志中是否包含既定任务失败标记，供现有结果汇总使用。"""
    return any(marker in log for marker in _MAA_TASK_FAILURE_MARKERS)


def _failed_maa_task_names(log: str) -> set[str]:
    """读取 MAA 公开失败清单；旧版只保留未被后续完成覆盖的错误行。"""

    summaries = re.findall(r"任务已结束，以下任务出现错误[:：]\s*([^\r\n]+)", log)
    if summaries:
        return {name.strip() for summary in summaries for name in summary.split(",")}
    failed_names = set()
    for error in re.finditer(r"任务出错:\s*([^\r\n]+)", log):
        name = error.group(1).strip()
        completions = re.finditer(rf"完成任务:\s*{re.escape(name)}\s*$", log, re.M)
        if not any(done.start() > error.start() for done in completions):
            failed_names.add(name)
    return failed_names


def _failed_maa_sanity_tasks(log: str) -> set[str]:
    """按 MAA 明确报错的任务名屏蔽体力任务，不反推游戏内消耗。"""

    failed_names = _failed_maa_task_names(log)
    return {
        task
        for task, names in _MAA_SANITY_TASK_NAMES.items()
        if any(
            re.fullmatch(
                rf"(?:{'|'.join(re.escape(name) for name in names)})(?: #\d+| \(仓库识别\))?",
                failed_name,
            )
            for failed_name in failed_names
        )
    }


def _should_retry_maa(
    status: str, log: str, *, managed: bool, pending_tasks: dict[str, bool]
) -> bool:
    """明确失败后只重试可单独下发的非体力任务，运行异常沿用次数限制。"""

    if status == "Success!":
        return False
    if status != "MAA 部分任务执行失败" or not _has_maa_task_failure(log):
        return True
    # 不能拆分来源队列，或还有无法确认结果的体力任务时，保持原有停止行为。
    if not managed or any(pending_tasks.get(task) for task in _MAA_SANITY_TASK_NAMES):
        return False
    return any(enabled for task, enabled in pending_tasks.items() if task != "StartUp")


def _parse_annihilation_weekly_progress(log: str) -> tuple[int, int] | None:
    """解析 MAA 输出的剿灭周进度。"""

    matches = _ANNIHILATION_PROGRESS_RE.findall(log)
    if not matches:
        return None
    current, total = (int(value) for value in matches[-1])
    return (current, total) if total > 0 else None


def _has_completed_annihilation_week(log: str) -> bool:
    """判断剿灭日志是否表明本周额度已完成。

    MAA 剿灭结束都会打印「完成任务: 剿灭作战」，以理智识别行区分战斗流程：

    - 无理智识别行：MAA 未进到副本门口，完成即周内剿灭在代理开始前已完成；
    - 有理智识别行但无进度行：进到门口却因理智不足没有开战，未达标；
    - 有进度行但 current < total：开战了但理智不足没能打满进度，未达标；
    - 进度 current >= total：本周剿灭已完成。

    未达标时不记周完成标记，宁可下次代理重试。
    """

    if "完成任务: 剿灭作战" not in log:
        return False

    if not _MAA_SANITY_RECOGNITION_RE.search(log):
        return True

    progress = _parse_annihilation_weekly_progress(log)
    return progress is not None and progress[0] >= progress[1]


def _has_completed_sanity_task(log_records: list[LogRecord]) -> bool:
    """判断日志记录中是否已经完成过体力任务。"""

    for log_record in log_records:
        lines = log_record.content
        # 只认刷关完成行，仓库识别等括号后缀不表示已经刷过关卡。
        if any(
            re.search(rf"{re.escape(marker)}(?:\s+#\d+)?\s*$", line)
            for line in lines
            for marker in _MAA_SANITY_COMPLETION_MARKERS
        ):
            return True

        for index, line in enumerate(lines):
            if _MAA_FIGHT_COMPLETION_MARKER not in line:
                continue
            previous_task = next(
                (item for item in reversed(lines[:index]) if "完成任务:" in item),
                "",
            )
            if "剿灭" in previous_task:
                continue
            if not previous_task and _ANNIHILATION_PROGRESS_RE.search(
                "".join(lines[max(0, index - 8) : index + 1])
            ):
                continue
            return True

    return False
