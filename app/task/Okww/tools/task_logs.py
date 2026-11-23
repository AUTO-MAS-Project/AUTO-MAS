"""识别 OK-WW 自身报告的一次性任务终止。"""

import re
from collections.abc import Iterable

_ONETIME_TASK_STARTED = re.compile(
    r"^\S+ \S+ INFO TaskExecutor TaskExecutor:get (?:queued|one enabled) onetime_task (.+)"
)
_TASK_STOPPED = re.compile(
    r"^\S+ \S+ ERROR TaskExecutor TaskExecutor:(.+?) exception stopped(?:\s|$)"
)


def has_task_failure(lines: Iterable[str]) -> bool:
    """用执行器公布的任务名称区分一次性任务和后台触发任务。"""
    task_name = None
    for line in lines:
        if started := _ONETIME_TASK_STARTED.match(line):
            task_name = started[1].rstrip()
        elif (stopped := _TASK_STOPPED.match(line)) and stopped[1] == task_name:
            return True
    return False
