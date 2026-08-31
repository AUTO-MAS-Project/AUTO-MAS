"""`automas_maafw_runner` 的导入与 run_plan 构建纯逻辑回归。

该包按《maafw-移植基准对照-20260830.md》§3.1 以插件 `dev2/maafw-fixes-20260728`
为骨架落库，并入 mfwa 的三处独有增量（见移植日志阶段 3）。

测试纪律：不实例化 `Tasker`/`Controller`，不起子进程，不加载 maa DLL。
只有 `runner`/`worker` 两个模块会 `import maa`，本文件在 mock 下验证其可导入。
"""

import ast
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_interface.models import (
    PRETASK_TASK_PREFIX,
)
from app.task.MaaFW.tools.core.automas_maafw_runner import (
    MaaFWRunPlanError,
    build_maafw_run_plan,
)
from app.task.MaaFW.tools.core.automas_maafw_runner.models import (
    MaaFWRunnerJobPayload,
)
from app.task.MaaFW.tools.core.automas_maafw_runner.run_plan import (
    MAX_LANGUAGE_FILE_BYTES,
    _load_i18n_mapping,
    _resolve_pretask_executable,
)

MAA_MODULES = (
    "maa",
    "maa.agent_client",
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

INTERFACE = {
    "interface_version": 2,
    "name": "Demo",
    "version": "v1.0.0",
    "controller": [
        {"name": "安卓", "type": "Adb"},
        {"name": "桌面", "type": "Win32", "win32": {"window_regex": "Demo"}},
    ],
    "resource": [{"name": "官服", "path": ["{PROJECT_DIR}/resource/base"]}],
    "task": [
        {"name": "主线", "entry": "Main", "default_check": True},
        {"name": "日常", "entry": "Daily", "default_check": True},
    ],
}


def top_level_maa_imports(path: Path) -> list[str]:
    """返回该文件模块级（含 try/if 块）导入的 maa 模块名，不含函数体内的延迟导入。"""

    found: list[str] = []

    def visit(nodes) -> None:
        for node in nodes:
            if isinstance(node, ast.Import):
                found.extend(
                    alias.name
                    for alias in node.names
                    if alias.name == "maa" or alias.name.startswith("maa.")
                )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "maa" or module.startswith("maa."):
                    found.append(module)
            elif isinstance(node, (ast.If, ast.Try)):
                visit(node.body)
                visit(node.orelse)
                visit(getattr(node, "handlers", []))
                visit(getattr(node, "finalbody", []))
            elif isinstance(node, ast.ExceptHandler):
                visit(node.body)

    visit(ast.parse(path.read_text(encoding="utf-8")).body)
    return found


def project_with_interface(root: Path, interface: dict | None = None) -> Path:
    project = root / "project"
    (project / "resource" / "base").mkdir(parents=True, exist_ok=True)
    (project / "interface.json").write_text(
        json.dumps(interface or INTERFACE, ensure_ascii=False),
        encoding="utf-8",
    )
    return project


class RunnerPackageImportTest(unittest.TestCase):
    MAA_FREE_MODULES = (
        "environment",
        "hotkey",
        "models",
        "pipeline_override",
        "run_plan",
        "service",
        "shared_agent",
        "worker_registry",
    )

    def test_maa_free_modules_are_importable(self) -> None:
        base = "app.task.MaaFW.tools.core.automas_maafw_runner"
        for name in self.MAA_FREE_MODULES:
            with self.subTest(module=name):
                self.assertIsNotNone(importlib.import_module(base + "." + name))

    def test_only_runner_and_worker_import_maa_at_module_level(self) -> None:
        """导入这些模块不得触发 maa DLL 加载（沿用 preview.py 的边界约定）。

        用静态检查而不是 `sys.modules` 断言：`app/core/maa_manager.py` 是上游
        基线既有的原生集成，全量跑时会合法地把 maa 载入进程，全局状态断言会
        随用例顺序漂移。
        """

        package_dir = (
            Path(__file__).resolve().parents[2]
            / "app"
            / "task"
            / "MaaFW"
            / "tools"
            / "core"
            / "automas_maafw_runner"
        )
        for name in self.MAA_FREE_MODULES:
            with self.subTest(module=name):
                self.assertEqual(
                    top_level_maa_imports(package_dir / (name + ".py")),
                    [],
                )
        # runner 是唯一直接持有 maa 的模块；worker 经 runner 间接引入，
        # 两者都只在 worker 子进程里被导入，主进程不碰
        self.assertTrue(top_level_maa_imports(package_dir / "runner.py"))
        self.assertEqual(top_level_maa_imports(package_dir / "worker.py"), [])

    def test_runner_and_worker_import_under_a_mocked_maa(self) -> None:
        import sys

        base = "app.task.MaaFW.tools.core.automas_maafw_runner"
        patched = {name: mock.MagicMock() for name in MAA_MODULES}
        with mock.patch.dict(sys.modules, patched):
            for name in ("runner", "worker"):
                with self.subTest(module=name):
                    module = importlib.import_module(base + "." + name)
                    self.assertTrue(hasattr(module, "__file__"))

    def test_plugin_glue_is_not_present(self) -> None:
        package_dir = (
            Path(__file__).resolve().parents[2]
            / "app"
            / "task"
            / "MaaFW"
            / "tools"
            / "core"
            / "automas_maafw_runner"
        )
        for glue in ("plugin.py", "schema.py"):
            self.assertFalse((package_dir / glue).exists(), glue)
        self.assertTrue((package_dir / "py.typed").exists())


class RunPlanBuildTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.project = project_with_interface(self.root)

    def _plan(self, **kwargs):
        kwargs.setdefault("managed_env_root", self.root / "envs")
        return build_maafw_run_plan(self.project, INTERFACE, **kwargs)

    def test_default_selection_picks_the_first_direct_controller(self) -> None:
        plan = self._plan()
        self.assertEqual(plan.controllerName, "安卓")
        self.assertEqual(plan.resourceName, "官服")

    def test_named_controller_and_resource_are_honoured(self) -> None:
        plan = self._plan(controller_name="桌面", resource_name="官服")
        self.assertEqual(plan.controllerName, "桌面")

    def test_unknown_controller_is_rejected(self) -> None:
        with self.assertRaises(MaaFWRunPlanError):
            self._plan(controller_name="不存在")

    def test_non_direct_controller_is_rejected_fail_closed(self) -> None:
        # 第二层对不支持的控制器类型必须 fail-closed，由第一层兜底
        interface = json.loads(json.dumps(INTERFACE))
        interface["controller"] = [{"name": "苹果", "type": "MacOS"}]
        with self.assertRaises(MaaFWRunPlanError):
            build_maafw_run_plan(self.project, interface)

    def test_interface_without_controller_is_rejected(self) -> None:
        interface = json.loads(json.dumps(INTERFACE))
        interface["controller"] = []
        with self.assertRaises(MaaFWRunPlanError):
            build_maafw_run_plan(self.project, interface)

    def test_selected_tasks_become_runnable_plans(self) -> None:
        plan = self._plan(task_names=["主线", "日常"])
        self.assertEqual([task.name for task in plan.tasks], ["主线", "日常"])

    def test_unknown_task_name_is_dropped_before_planning(self) -> None:
        plan = self._plan(task_names=["主线", "不存在的任务"])
        self.assertEqual([task.name for task in plan.tasks], ["主线"])

    def test_controller_incompatible_task_is_skipped_with_a_reason(self) -> None:
        interface = json.loads(json.dumps(INTERFACE))
        interface["task"] = [
            {"name": "主线", "entry": "Main", "default_check": True},
            {
                "name": "仅桌面",
                "entry": "DesktopOnly",
                "default_check": True,
                "controller": ["桌面"],
            },
        ]
        plan = build_maafw_run_plan(
            self.project,
            interface,
            controller_name="安卓",
            task_names=["主线", "仅桌面"],
            managed_env_root=self.root / "envs",
        )
        self.assertEqual([task.name for task in plan.tasks], ["主线"])
        self.assertEqual([task.name for task in plan.skippedTasks], ["仅桌面"])
        self.assertTrue(plan.skippedTasks[0].reason)

    def test_resource_path_escaping_the_project_is_rejected(self) -> None:
        interface = json.loads(json.dumps(INTERFACE))
        interface["resource"] = [{"name": "越界", "path": ["{PROJECT_DIR}/../../etc"]}]
        with self.assertRaises(MaaFWRunPlanError):
            build_maafw_run_plan(self.project, interface)

    def test_plan_round_trips_through_the_job_payload(self) -> None:
        plan = self._plan(task_names=["主线"])
        payload = MaaFWRunnerJobPayload(
            plan=plan,
            deviceConfig={"type": "Adb"},
            ownerPid=4321,
            ownerCreateTime=1234.5,
        )
        restored = MaaFWRunnerJobPayload.model_validate(
            json.loads(json.dumps(payload.model_dump(mode="json")))
        )
        self.assertEqual(restored.ownerPid, 4321)
        self.assertEqual(restored.ownerCreateTime, 1234.5)
        self.assertEqual(restored.plan.controllerName, plan.controllerName)

    def test_job_payload_owner_fields_default_to_none(self) -> None:
        payload = MaaFWRunnerJobPayload(
            plan=self._plan(),
            deviceConfig={"type": "Adb"},
        )
        self.assertIsNone(payload.ownerPid)
        self.assertIsNone(payload.ownerCreateTime)


class MergedMfwaIncrementTest(unittest.TestCase):
    """并入自 mfwa 的三处增量（移植日志阶段 3 记录）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.project = project_with_interface(self.root)

    def test_oversized_language_file_is_ignored(self) -> None:
        from app.task.MaaFW.tools.core.automas_maafw_interface.models import (
            MaaFWInterface,
        )

        language_path = self.project / "i18n" / "zh_cn.json"
        language_path.parent.mkdir(parents=True, exist_ok=True)
        language_path.write_text('{"a": "b"}', encoding="utf-8")
        interface = MaaFWInterface.model_validate(
            {**INTERFACE, "languages": {"zh_cn": "{PROJECT_DIR}/i18n/zh_cn.json"}}
        )
        base = self.project.resolve()

        self.assertEqual(_load_i18n_mapping(base, interface), {"a": "b"})

        # 并入自 mfwa：超过上限的语言文件直接忽略，不进解析
        padding = " " * (MAX_LANGUAGE_FILE_BYTES + 1 - len('{"a": "b"}'))
        language_path.write_text('{"a": "b"}' + padding, encoding="utf-8")
        self.assertGreater(
            language_path.stat().st_size,
            MAX_LANGUAGE_FILE_BYTES,
        )
        self.assertEqual(_load_i18n_mapping(base, interface), {})

    def test_pretask_executable_suffix_probe_is_windows_only(self) -> None:
        (self.project / "tool.exe").write_text("", encoding="utf-8")
        base = self.project.resolve()

        with mock.patch(
            "app.task.MaaFW.tools.core.automas_maafw_runner.run_plan.os.name",
            "nt",
        ):
            self.assertTrue(
                _resolve_pretask_executable(base, "tool").endswith("tool.exe")
            )

        with mock.patch(
            "app.task.MaaFW.tools.core.automas_maafw_runner.run_plan.os.name",
            "posix",
        ):
            with self.assertRaises(MaaFWRunPlanError):
                _resolve_pretask_executable(base, "tool")

    def test_pretask_args_expand_the_project_dir_token(self) -> None:
        interface = json.loads(json.dumps(INTERFACE))
        (self.project / "pre.exe").write_text("", encoding="utf-8")
        interface["pretask"] = [
            {
                "name": "准备",
                "exec": "{PROJECT_DIR}/pre.exe",
                "args": ["{PROJECT_DIR}/config.json", "--plain"],
            }
        ]
        plan = build_maafw_run_plan(
            self.project,
            interface,
            # 计划里至少要有一个普通任务，否则命中"没有可执行任务"的守卫
            task_names=["主线", PRETASK_TASK_PREFIX + "准备"],
            managed_env_root=self.root / "envs",
        )
        self.assertEqual(len(plan.pretasks), 1)
        pretask_args = [arg for pre in plan.pretasks for arg in pre.args]
        if pretask_args:
            self.assertNotIn(
                "{PROJECT_DIR}",
                " ".join(pretask_args),
                "pretask 参数里的 {PROJECT_DIR} 必须展开",
            )
            self.assertIn("--plain", pretask_args)


if __name__ == "__main__":
    unittest.main()
