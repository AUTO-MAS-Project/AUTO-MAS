"""重试不再补跑本轮已完成的任务：MSS 的灾变防线声明。

这条守的是「一期只能打一次」的常驻活动在重试里的行为：防线成功、后续任务失败时，
下一次尝试只该重跑没完成的任务；防线自己失败或没跑成，就该照常重试。判定完全复用
引擎的 ``skip_on_retry_entries`` 路径，这里只驱动真实的方法与真实的 MSS 声明——
MSS 那份 entry 列表一旦再被误删，第一条用例就会红。
"""

from types import SimpleNamespace

from app.models.config import MSSConfig
from app.task.MaaFW.tools.embedded import runner_task as runner_task_module

DEFENSE_ENTRY = "灾变防线_入口"
CLIMB_ENTRY = "星塔_入口_agent"


class _Plan(SimpleNamespace):
    """够用就行的运行计划替身：被测方法只用 tasks / skippedTasks / model_copy。"""

    def model_copy(self, update: dict) -> "_Plan":
        return _Plan(**{**self.__dict__, **update})


def _plan(*tasks: SimpleNamespace) -> _Plan:
    return _Plan(tasks=list(tasks), skippedTasks=[])


def _task(name: str, entry: str) -> SimpleNamespace:
    return SimpleNamespace(name=name, label=None, entry=entry)


def _runner(completed: list[str]) -> runner_task_module.MaaFWPluginAutoProxyTask:
    """只初始化重试筛选需要的状态，特调由真实配置解析。"""

    runner = object.__new__(runner_task_module.MaaFWPluginAutoProxyTask)
    runner.script_config = MSSConfig()
    runner._completed_this_run = completed
    runner._retry_rerun_duplicates = []
    return runner


def test_completed_defense_is_not_dispatched_again() -> None:
    plan = _plan(_task("灾变防线", DEFENSE_ENTRY), _task("新版爬塔", CLIMB_ENTRY))

    result = _runner(["灾变防线"])._skip_tasks_completed_this_run(plan)

    assert [task.entry for task in result.tasks] == [CLIMB_ENTRY]
    assert [task.entry for task in result.skippedTasks] == [DEFENSE_ENTRY]


def test_failed_defense_is_retried() -> None:
    plan = _plan(_task("灾变防线", DEFENSE_ENTRY), _task("新版爬塔", CLIMB_ENTRY))

    # 本次运行一个都没成功，说明防线没跑成：下一次尝试照常保留
    result = _runner([])._skip_tasks_completed_this_run(plan)

    assert result is plan
    assert [task.entry for task in result.tasks] == [DEFENSE_ENTRY, CLIMB_ENTRY]
