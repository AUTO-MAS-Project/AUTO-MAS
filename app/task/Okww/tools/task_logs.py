"""识别 OK-WW 自身报告的一次性任务终止。"""

import re
from collections.abc import Iterable

_ONETIME_TASK_STARTED = re.compile(
    r"^\S+ \S+ INFO TaskExecutor TaskExecutor:get (?:queued|one enabled) onetime_task (.+)"
)
_TASK_STOPPED = re.compile(
    r"^\S+ \S+ ERROR TaskExecutor TaskExecutor:(.+?) exception stopped(?:\s|$)"
)


def find_task_failure(lines: Iterable[str]) -> str | None:
    """当前一次性任务终止时返回对应错误行，无正文时返回空串。"""
    task_name = None
    detail = ""
    for line in lines:
        if started := _ONETIME_TASK_STARTED.match(line):
            task_name = started[1].rstrip()
            detail = ""
        elif stopped := _TASK_STOPPED.match(line):
            if stopped[1] == task_name:
                return detail
            detail = ""
        elif task_name is not None and " INFO TaskExecutor " in line:
            if ":info_set 错误" in line:
                detail = line
    return None
