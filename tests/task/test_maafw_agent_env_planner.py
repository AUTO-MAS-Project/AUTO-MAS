"""`automas_maafw_agent_env` 的导入与命令计划纯逻辑回归。

该包由插件 `dev2/maafw-fixes-20260728` 移入（基准对照 §2），已按移植指南 §4
丢弃 `plugin.py`/`schema.py` 胶水、把跨包导入改写为树内绝对路径。
本文件只覆盖计划构建（不建 venv、不装依赖、不起子进程）。
"""

import os
import tempfile
import unittest
from pathlib import Path

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_agent_env import (
    MaaFWAgentCommandPlan,
    MaaFWAgentEnvError,
    MaaFWAgentEnvPrepareResult,
    MaaFWAgentEnvService,
    build_agent_env_manifest,
    build_maafw_agent_command_plans,
    compute_isolated_venv_path,
    prepare_agent_envs,
    venv_python_exe,
    write_agent_compat_shims,
)


class AgentEnvPackageImportTest(unittest.TestCase):
    def test_public_surface_is_importable(self) -> None:
        self.assertTrue(issubclass(MaaFWAgentEnvError, RuntimeError))
        for symbol in (
            MaaFWAgentCommandPlan,
            MaaFWAgentEnvPrepareResult,
            MaaFWAgentEnvService,
            build_agent_env_manifest,
            build_maafw_agent_command_plans,
            compute_isolated_venv_path,
            prepare_agent_envs,
            venv_python_exe,
            write_agent_compat_shims,
        ):
            self.assertTrue(callable(symbol))

    def test_plugin_glue_is_not_present(self) -> None:
        package_dir = (
            Path(__file__).resolve().parents[2]
            / "app"
            / "task"
            / "MaaFW"
            / "tools"
            / "core"
            / "automas_maafw_agent_env"
        )
        self.assertTrue(package_dir.is_dir())
        for glue in ("plugin.py", "schema.py"):
            self.assertFalse((package_dir / glue).exists(), glue)
        self.assertTrue((package_dir / "py.typed").exists())


class IsolatedVenvPathTest(unittest.TestCase):
    def test_path_is_deterministic_and_project_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            first = Path(root) / "ProjectA"
            second = Path(root) / "ProjectB"
            first.mkdir()
            second.mkdir()
            managed = Path(root) / "envs"
            a1 = compute_isolated_venv_path(first, managed_env_root=managed)
            a2 = compute_isolated_venv_path(first, managed_env_root=managed)
            b1 = compute_isolated_venv_path(second, managed_env_root=managed)
            self.assertEqual(a1, a2)
            self.assertNotEqual(a1, b1)
            self.assertEqual(a1.parent, managed.resolve())
            self.assertTrue(a1.name.startswith("maafw_venv_"))

    @unittest.skipUnless(os.name == "nt", "仅 Windows 大小写不敏感")
    def test_windows_path_casing_does_not_split_the_venv(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "Project"
            project.mkdir()
            managed = Path(root) / "envs"
            self.assertEqual(
                compute_isolated_venv_path(project, managed_env_root=managed),
                compute_isolated_venv_path(
                    Path(str(project).upper()), managed_env_root=managed
                ),
            )

    def test_venv_python_exe_follows_the_platform_layout(self) -> None:
        exe = venv_python_exe(Path("X") / "venv")
        if os.name == "nt":
            self.assertEqual(exe, Path("X") / "venv" / "Scripts" / "python.exe")
        else:
            self.assertEqual(exe, Path("X") / "venv" / "bin" / "python")


class CommandPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name) / "project"
        self.project.mkdir()
        self.managed = Path(self._tmp.name) / "envs"

    def _plans(self, agent) -> list[MaaFWAgentCommandPlan]:
        return build_maafw_agent_command_plans(
            self.project,
            agent,
            managed_env_root=self.managed,
        )

    def test_no_agent_yields_no_plan(self) -> None:
        self.assertEqual(self._plans(None), [])
        self.assertEqual(self._plans([]), [])

    def test_bare_command_is_classified_external(self) -> None:
        plan = self._plans({"child_exec": "python"})[0]
        self.assertEqual(plan.runtimeKind, "external")
        self.assertEqual(plan.executable, "python")
        self.assertIsNone(plan.executableExists)
        self.assertIsNone(plan.fallbackReason)

    def test_project_dir_token_is_expanded_in_exec_and_args(self) -> None:
        agent_dir = self.project / "agent"
        agent_dir.mkdir()
        (agent_dir / "main.py").write_text("", encoding="utf-8")
        plan = self._plans(
            {
                "child_exec": "{PROJECT_DIR}/agent/main.py",
                "child_args": ["{PROJECT_DIR}/agent/main.py"],
            }
        )[0]
        self.assertNotIn("{PROJECT_DIR}", plan.executable)
        self.assertNotIn("{PROJECT_DIR}", plan.childArgs[0])
        self.assertEqual(plan.cwd, str(self.project.resolve()))

    def test_existing_project_python_is_classified_project_python(self) -> None:
        python_dir = self.project / "python"
        python_dir.mkdir()
        name = "python.exe" if os.name == "nt" else "python"
        (python_dir / name).write_text("", encoding="utf-8")
        plan = self._plans({"child_exec": "./python/" + name})[0]
        self.assertEqual(plan.runtimeKind, "project_python")
        self.assertTrue(plan.executableExists)

    def test_existing_project_binary_is_classified_project_binary(self) -> None:
        (self.project / "agent.bin").write_text("", encoding="utf-8")
        plan = self._plans({"child_exec": "./agent.bin"})[0]
        self.assertEqual(plan.runtimeKind, "project_binary")
        self.assertTrue(plan.executableExists)

    def test_missing_bundled_python_falls_back_to_isolated_venv(self) -> None:
        agent_dir = self.project / "agent"
        agent_dir.mkdir()
        (agent_dir / "main.py").write_text("", encoding="utf-8")
        plan = self._plans({"child_exec": "./python/python.exe"})[0]
        self.assertEqual(plan.runtimeKind, "isolated_venv")
        self.assertIsNotNone(plan.isolatedVenvPath)
        self.assertEqual(
            Path(plan.isolatedVenvPath).parent,
            self.managed.resolve(),
        )
        self.assertIn("隔离 venv", plan.fallbackReason or "")

    def test_missing_executable_without_bundled_pattern_reports_failure(self) -> None:
        plan = self._plans({"child_exec": "./missing/tool.bin"})[0]
        self.assertEqual(plan.runtimeKind, "external")
        self.assertFalse(plan.executableExists)
        self.assertIn("不存在", plan.fallbackReason or "")

    def test_embedded_agent_is_forced_into_a_subprocess(self) -> None:
        agent_dir = self.project / "agent"
        agent_dir.mkdir()
        (agent_dir / "main.py").write_text("", encoding="utf-8")
        plan = self._plans({"child_exec": "python", "embedded": True})[0]
        # embedded 请求不得让 agent 跑进 AUTO-MAS 主进程
        self.assertFalse(plan.embedded)
        self.assertIn("隔离子进程", plan.fallbackReason or "")
        self.assertEqual(plan.childArgs[0], "-u")
        self.assertTrue(plan.childArgs[1].endswith("main.py"))

    def test_embedded_agent_keeps_an_explicit_python_entry(self) -> None:
        (self.project / "custom.py").write_text("", encoding="utf-8")
        plan = self._plans(
            {
                "child_exec": "python",
                "child_args": ["custom.py"],
                "embedded": True,
            }
        )[0]
        self.assertEqual(plan.childArgs, ["custom.py"])

    def test_command_ends_with_the_socket_placeholder(self) -> None:
        plan = self._plans({"child_exec": "python", "child_args": ["-u", "x.py"]})[0]
        self.assertEqual(plan.command[0], plan.executable)
        self.assertEqual(plan.command[-1], "<socket_id>")
        self.assertEqual(plan.command[1:-1], plan.childArgs)

    def test_path_escaping_the_project_root_is_rejected(self) -> None:
        with self.assertRaises(MaaFWAgentEnvError):
            self._plans({"child_exec": "./../../evil.exe"})

    def test_multiple_agents_yield_one_plan_each(self) -> None:
        plans = self._plans(
            [
                {"child_exec": "python", "identifier": "a"},
                {"child_exec": "node", "identifier": "b"},
            ]
        )
        self.assertEqual([plan.identifier for plan in plans], ["a", "b"])


class AgentEnvServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name) / "project"
        self.project.mkdir()
        self.service = MaaFWAgentEnvService()

    def test_service_accepts_a_full_interface_payload(self) -> None:
        plans = self.service.build_command_plans(
            self.project,
            {
                "interface_version": 2,
                "name": "Demo",
                "agent": {"child_exec": "python", "child_args": ["-u", "main.py"]},
            },
            managed_env_root=Path(self._tmp.name) / "envs",
        )
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].childExec, "python")

    def test_service_accepts_a_bare_agent_mapping(self) -> None:
        plans = self.service.build_command_plans(
            self.project,
            {"child_exec": "python"},
            managed_env_root=Path(self._tmp.name) / "envs",
        )
        self.assertEqual(len(plans), 1)

    def test_interface_without_agent_yields_no_plan(self) -> None:
        plans = self.service.build_command_plans(
            self.project,
            {"interface_version": 2, "name": "Demo"},
        )
        self.assertEqual(plans, [])

    def test_classify_falls_back_to_external(self) -> None:
        self.assertEqual(self.service.classify({"child_exec": "python"}), "external")


if __name__ == "__main__":
    unittest.main()
