"""任务失败信息要说清哪里坏了，而不是堆内部标识。

真机上用户看到的原文：

    🤝拜访好友：任务执行失败：VisitFriends: 任务执行失败: entry=VisitFriendsMain,
    task_id=200000001, status=failed(4000), last_nodes=[300000001, 300000002]:
    失败事件: Tasker.Task.Failed, VisitFriendsMain

四个毛病：任务名出现三次（标签「拜访好友」、name「VisitFriends」、
entry「VisitFriendsMain」）；「任务执行失败」出现两次；task_id / status(4000) /
last_nodes 是用户查不了的内部标识；而且**没说到底哪里出错**。

改法是把职责分开：宿主拼任务标签与「任务执行失败」，runner 只回答「哪里坏了」。
节点数字 id 解析成名字——那才是能定位的信息，数字对用户毫无意义，
完整内容本来就在 *.maafw.log 里。
"""

import sys
import unittest
from types import SimpleNamespace
from unittest import mock

import app.core  # noqa: F401  # 初始化宿主配置

MAA_MODULES = (
    "maa",
    "maa.agent_client",
    "maa.context",
    "maa.controller",
    "maa.custom_action",
    "maa.custom_recognition",
    "maa.define",
    "maa.event_sink",
    "maa.job",
    "maa.library",
    "maa.notification_handler",
    "maa.resource",
    "maa.tasker",
    "maa.toolkit",
)


def load(name: str):
    patcher = mock.patch.dict(
        sys.modules, {mod: mock.MagicMock() for mod in MAA_MODULES}
    )
    patcher.start()
    import importlib

    return importlib.import_module(name), patcher


def detail(entry="VisitFriendsMain", node_ids=(300000001, 300000002)):
    return SimpleNamespace(
        entry=entry, node_id_list=list(node_ids), task_id=200000001, status=None
    )


class RunnerReasonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module, patcher = load(
            "app.task.MaaFW.tools.core.automas_maafw_runner.runner"
        )
        self.addCleanup(patcher.stop)

    def _runner(self, names=None, summaries=()):
        runner = object.__new__(self.module.MaaFWRunner)
        runner._task_failure_summaries = list(summaries)
        if names is None:
            runner.tasker = None
        else:
            runner.tasker = SimpleNamespace(
                get_node_detail=lambda i: SimpleNamespace(name=names.get(i, ""))
            )
        return runner

    def test_node_ids_become_names(self) -> None:
        runner = self._runner({300000001: "EnterHome", 300000002: "CheckList"})
        self.assertEqual(
            runner._build_job_failure_message(detail()),
            "最后停在 EnterHome → CheckList",
        )

    def test_no_internal_identifiers_leak(self) -> None:
        runner = self._runner({300000001: "EnterHome", 300000002: "CheckList"})
        message = runner._build_job_failure_message(detail())
        for leaked in ("task_id", "300000001", "node_id", "status="):
            self.assertNotIn(leaked, message)

    def test_only_the_tail_nodes_are_listed(self) -> None:
        """再往前是正常走过的路径，列出来只会淹没重点。"""

        ids = tuple(range(300000001, 300000009))
        runner = self._runner({i: f"N{i - 300000000}" for i in ids})
        message = runner._build_job_failure_message(detail(node_ids=ids))
        self.assertEqual(
            message.count("→"), self.module.FAILURE_NODE_NAME_LIMIT - 1
        )
        self.assertIn("N8", message)
        self.assertNotIn("N1 ", message)

    def test_repeated_node_names_are_collapsed(self) -> None:
        """同名节点连着出现时说一次就够。"""

        runner = self._runner({300000001: "Retry", 300000002: "Retry"})
        self.assertEqual(runner._build_job_failure_message(detail()), "最后停在 Retry")

    def test_unresolvable_nodes_fall_back_to_the_entry(self) -> None:
        self.assertEqual(
            self._runner()._build_job_failure_message(detail()),
            "入口 VisitFriendsMain 未能走完",
        )

    def test_node_lookup_failure_is_tolerated(self) -> None:
        """诊断信息不该因为取不到名字而失败。"""

        def boom(_):
            raise RuntimeError("IPC 断了")

        runner = object.__new__(self.module.MaaFWRunner)
        runner._task_failure_summaries = []
        runner.tasker = SimpleNamespace(get_node_detail=boom)
        self.assertEqual(
            runner._build_job_failure_message(detail()),
            "入口 VisitFriendsMain 未能走完",
        )

    def test_the_redundant_framework_event_is_dropped(self) -> None:
        """`Tasker.Task.Failed, <entry>` 只是重复上面已经说过的入口名。"""

        runner = self._runner(
            {300000001: "EnterHome", 300000002: "CheckList"},
            summaries=["Tasker.Task.Failed, VisitFriendsMain"],
        )
        message = runner._build_job_failure_message(detail())
        self.assertNotIn("Tasker.Task.Failed", message)

    def test_informative_framework_events_are_kept(self) -> None:
        runner = self._runner(
            {300000001: "EnterHome", 300000002: "CheckList"},
            summaries=["Node.Action.Failed, 点击礼包屋"],
        )
        message = runner._build_job_failure_message(detail())
        self.assertIn("点击礼包屋", message)


class UserFacingSummaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module, patcher = load("app.task.MaaFW.tools.embedded.runner_task")
        self.addCleanup(patcher.stop)
        self.plan = SimpleNamespace(
            tasks=[
                SimpleNamespace(
                    name="VisitFriends",
                    entry="VisitFriendsMain",
                    label="🤝拜访好友",
                )
            ]
        )

    def _summary(self, reason: str) -> str:
        return self.module._failed_task_user_summary(
            SimpleNamespace(errorMessage=reason, failedTask="VisitFriends"), self.plan
        )

    def test_the_task_name_appears_once(self) -> None:
        summary = self._summary("最后停在 EnterHome → CheckList")
        self.assertEqual(summary.count("拜访好友"), 1)
        self.assertNotIn("VisitFriends", summary)

    def test_the_failure_phrase_appears_once(self) -> None:
        self.assertEqual(
            self._summary("最后停在 EnterHome → CheckList").count("任务执行失败"), 1
        )

    def test_python_exceptions_still_come_through(self) -> None:
        """缺模块这类异常必须原样可见，否则任务页上只剩四个字。"""

        summary = self._summary("ModuleNotFoundError: No module named 'httpx'")
        self.assertIn("ModuleNotFoundError", summary)
        self.assertIn("httpx", summary)


class DeadFormattersRemovedTest(unittest.TestCase):
    """产出那串内部标识的两个格式化函数已随本次改动删除。"""

    def test_they_are_gone(self) -> None:
        module, patcher = load(
            "app.task.MaaFW.tools.core.automas_maafw_runner.runner"
        )
        self.addCleanup(patcher.stop)
        for name in ("_format_maafw_task_detail", "_format_maafw_status"):
            with self.subTest(symbol=name):
                self.assertFalse(hasattr(module, name))


if __name__ == "__main__":
    unittest.main()
