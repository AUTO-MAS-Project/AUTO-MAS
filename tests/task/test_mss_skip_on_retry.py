"""重试不再补跑本轮已完成的任务：MSS 的灾变防线声明。

这条守的是「一期只能打一次」的常驻活动在重试里的行为：防线成功、后续任务失败时，
下一次尝试只该重跑没完成的任务；防线自己失败或没跑成，就该照常重试。判定完全复用
引擎的 ``skip_on_retry_entries`` 路径，这里只驱动真实的方法与真实的 MSS 声明——
MSS 那份 entry 列表一旦再被误删，第一条用例就会红。
"""

from types import SimpleNamespace

import pytest

from app.task.MaaFW.tools.embedded import runner_task as runner_task_module
from app.task.MSS.flavor import MSSFlavor

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
    """绕过 __init__ 造出只带重试状态的实例；resolve_flavor 由 fixture 换成真实特调。"""

    runner = object.__new__(runner_task_module.MaaFWPluginAutoProxyTask)
    runner.script_config = None
    runner._completed_this_run = completed
    runner._retry_rerun_duplicates = []
    return runner


@pytest.fixture(autouse=True)
def _mss_flavor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runner_task_module, "resolve_flavor", lambda _config: MSSFlavor()
    )


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


def test_duplicate_named_defense_keeps_existing_rerun_policy() -> None:
    plan = _plan(_task("灾变防线", DEFENSE_ENTRY), _task("灾变防线", DEFENSE_ENTRY))

    runner = _runner(["灾变防线"])
    result = runner._skip_tasks_completed_this_run(plan)

    # 同名两份分不清完成的是哪份：沿用引擎的保守策略，全部重跑
    assert result is plan
    assert set(runner._retry_rerun_duplicates) == {"灾变防线"}


def test_mss_declares_defense_entry() -> None:
    """直接钉住声明本身：删掉这一条时上面的用例也会红，这里给出更直白的原因。"""

    assert DEFENSE_ENTRY in MSSFlavor.skip_on_retry_entries
