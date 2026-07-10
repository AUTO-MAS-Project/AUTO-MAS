import asyncio
import json
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
for plugin_name in (
    "automas_maafw_agent_env",
    "automas_maafw_interface",
    "automas_maafw_project_update",
    "automas_maafw_runner",
    "automas_script_maafw",
):
    sys.path.insert(0, str(REPO_ROOT / "plugins" / plugin_name / "src"))

import automas_maafw_runner.runner as maafw_runner_module
from automas_maafw_interface.models import MaaFWInterface
from automas_maafw_runner.environment import (
    RUNNER_DEFAULT_PACKAGES,
    _build_manifest,
    _installed_maafw_version,
    build_runner_packages,
    prefer_active_venv_site_packages,
    prepare_runner_environment,
    requirement_distribution_name,
)
from automas_maafw_runner.models import MaaFWTaskRunPlan
from automas_maafw_runner.runner import (
    MaaFWDeviceConfig,
    MaaFWRunner,
    Toolkit,
    _format_task_config_log,
)
from automas_maafw_runner.service import MaaFWRunnerService
from automas_script_maafw.adapter import (
    MaaFWAdapterHooks,
    _load_legacy_script_config,
    _load_legacy_user_config,
)
from automas_script_maafw.runner_task import (
    MaaFWPluginAutoProxyTask,
    _WIN32_INPUT_METHODS,
    _WIN32_SCREENCAP_METHODS,
    _decode_subprocess_output,
    _format_run_overview_log,
    _resolve_win32_method,
)


class MaaFWPluginRuntimeTest(unittest.TestCase):
    def test_task_config_log_precedes_task_start(self) -> None:
        logs: list[str] = []
        task = MaaFWTaskRunPlan(
            name="崩坏三 启动！",
            entry="登录方式选择接口",
            options={"登录凭据": {"密码": "do-not-log-this"}},
            pipelineOverride={"登录参数": {"attach": {"密码": "do-not-log-this"}}},
            logOptions={"登录凭据": {"密码": "<已配置>"}},
            overrideNodes=["登录参数"],
        )
        job = SimpleNamespace(wait=lambda: None, failed=False)
        tasker = SimpleNamespace(post_task=lambda *_args: job)
        runner = MaaFWRunner(SimpleNamespace(tasks=[task]), send_log=logs.append)
        runner.tasker = tasker

        runner._run_tasks()

        self.assertTrue(logs[0].startswith("MaaFW 任务配置:"))
        self.assertEqual(logs[1], "正在运行任务: 崩坏三 启动！")
        self.assertNotIn("do-not-log-this", "\n".join(logs))

    def test_runner_enables_native_file_logging_without_draws(self) -> None:
        initialized = maafw_runner_module._MAAFW_INITIALIZED
        try:
            with TemporaryDirectory() as temporary_dir:
                root = Path(temporary_dir)
                project_path = root / "project"
                project_path.mkdir()
                maafw_runner_module._MAAFW_INITIALIZED = False
                with (
                    patch.object(maafw_runner_module.Path, "cwd", return_value=root),
                    patch.object(
                        maafw_runner_module,
                        "_ensure_maafw_client_library_mode",
                    ),
                    patch.object(
                        maafw_runner_module.Toolkit,
                        "init_option",
                        return_value=True,
                    ) as init_option,
                ):
                    maafw_runner_module._ensure_maafw_global_init(project_path)

                options = json.loads(
                    (project_path / "config" / "maa_option.json").read_text(
                        encoding="utf-8"
                    )
                )
        finally:
            maafw_runner_module._MAAFW_INITIALIZED = initialized

        self.assertTrue(options["logging"])
        self.assertFalse(options["save_draw"])
        init_option.assert_called_once_with(str(project_path.resolve()))
        self.assertEqual(
            project_path / maafw_runner_module.MAAFW_DEBUG_LOG_PATH,
            project_path / "debug" / "maafw.log",
        )

    def test_project_maafw_requirement_overrides_runner_fallback(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            project_path = Path(temporary_dir)
            (project_path / "requirements.txt").write_text(
                "json-with-comments\nMaaFw\n",
                encoding="utf-8",
            )

            packages = build_runner_packages(project_path)

        self.assertIn("MaaFw", packages)
        self.assertNotIn("maafw", packages)
        self.assertIn("pydantic==2.11.7", packages)

    def test_runner_fallback_is_kept_without_project_maafw_requirement(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            packages = build_runner_packages(temporary_dir)

        self.assertEqual(packages, list(RUNNER_DEFAULT_PACKAGES))
        self.assertIn("maafw", packages)

    def test_runner_environment_upgrades_unpinned_project_maafw(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            project_path = root / "project"
            project_path.mkdir()
            (project_path / "requirements.txt").write_text(
                "MaaFw\n",
                encoding="utf-8",
            )

            with (
                patch(
                    "automas_maafw_runner.environment._is_valid_venv",
                    return_value=True,
                ),
                patch(
                    "automas_maafw_runner.environment._manifest_matches",
                    return_value=False,
                ),
                patch("automas_maafw_runner.environment._run_setup_command") as run,
                patch("automas_maafw_runner.environment._write_manifest"),
                patch(
                    "automas_maafw_runner.environment._installed_maafw_version",
                    return_value="5.11.1",
                ),
            ):
                prepare_runner_environment(
                    project_path,
                    managed_env_root=root / "venvs",
                )

        command = run.call_args.args[0]
        self.assertIn("--upgrade", command)
        self.assertIn("MaaFw", command)

    def test_runner_environment_skips_upgrade_when_manifest_matches(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            project_path = root / "project"
            project_path.mkdir()

            with (
                patch(
                    "automas_maafw_runner.environment._is_valid_venv",
                    return_value=True,
                ),
                patch(
                    "automas_maafw_runner.environment._manifest_matches",
                    return_value=True,
                ),
                patch("automas_maafw_runner.environment._run_setup_command") as run,
                patch(
                    "automas_maafw_runner.environment._installed_maafw_version",
                    return_value="5.11.1",
                ),
            ):
                prepare_runner_environment(
                    project_path,
                    managed_env_root=root / "venvs",
                )

        run.assert_not_called()

    def test_runner_manifest_changes_with_project_interface(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            project_path = Path(temporary_dir)
            interface_path = project_path / "interface.json"
            interface_path.write_text('{"version": "1.12.8"}', encoding="utf-8")
            before = _build_manifest(project_path, ("maafw",))

            interface_path.write_text('{"version": "1.12.9"}', encoding="utf-8")
            after = _build_manifest(project_path, ("maafw",))

        self.assertNotEqual(before["interfaceHash"], after["interfaceHash"])

    def test_requirement_distribution_name_is_pep503_normalized(self) -> None:
        self.assertEqual(requirement_distribution_name("MaaFw>=5.11"), "maafw")
        self.assertEqual(requirement_distribution_name("maa_fw[extra]"), "maa-fw")

    def test_win32_methods_fall_back_to_interface_declaration(self) -> None:
        self.assertEqual(
            _resolve_win32_method(
                0,
                "PrintWindow",
                _WIN32_SCREENCAP_METHODS,
                _WIN32_SCREENCAP_METHODS["DXGI_DesktopDup"],
            ),
            _WIN32_SCREENCAP_METHODS["PrintWindow"],
        )
        self.assertEqual(
            _resolve_win32_method(
                0,
                "PostMessageWithCursorPos",
                _WIN32_INPUT_METHODS,
                _WIN32_INPUT_METHODS["Seize"],
            ),
            _WIN32_INPUT_METHODS["PostMessageWithCursorPos"],
        )

    def test_explicit_win32_method_overrides_interface_declaration(self) -> None:
        self.assertEqual(
            _resolve_win32_method(
                _WIN32_SCREENCAP_METHODS["ScreenDC"],
                "PrintWindow",
                _WIN32_SCREENCAP_METHODS,
                _WIN32_SCREENCAP_METHODS["DXGI_DesktopDup"],
            ),
            _WIN32_SCREENCAP_METHODS["ScreenDC"],
        )

    def test_worker_stderr_decodes_utf8_and_gbk_chinese(self) -> None:
        message = "模板大小不对"

        self.assertEqual(_decode_subprocess_output(message.encode("utf-8")), message)
        self.assertEqual(_decode_subprocess_output(message.encode("gbk")), message)

    def test_runner_venv_packages_precede_shared_plugin_packages(self) -> None:
        with TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            active_site_packages = root / "runner" / "site-packages"
            shared_site_packages = root / "plugins" / "site-packages"
            active_site_packages.mkdir(parents=True)
            shared_site_packages.mkdir(parents=True)
            original_sys_path = list(sys.path)
            try:
                sys.path[:] = [str(shared_site_packages), str(active_site_packages)]

                prefer_active_venv_site_packages(active_site_packages)

                self.assertEqual(sys.path[0], str(active_site_packages.resolve()))
                self.assertEqual(sys.path[1], str(shared_site_packages))
            finally:
                sys.path[:] = original_sys_path

    def test_maafw_version_probe_ignores_shared_pythonpath(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="5.11.1\n")
        with patch(
            "automas_maafw_runner.environment.subprocess.run",
            return_value=completed,
        ) as run:
            version = _installed_maafw_version(
                Path("python"),
                {"PYTHONPATH": "shared-plugin-site", "KEEP": "value"},
            )

        self.assertEqual(version, "5.11.1")
        probe_env = run.call_args.kwargs["env"]
        self.assertNotIn("PYTHONPATH", probe_env)
        self.assertEqual(probe_env["KEEP"], "value")

    def test_runner_discovers_missing_adb_path_with_active_toolkit(self) -> None:
        runner = MaaFWRunner(SimpleNamespace())
        device_config = MaaFWDeviceConfig(
            type="Adb",
            address="127.0.0.1:5555",
        )
        discovered = SimpleNamespace(
            address="127.0.0.1:5555",
            adb_path="C:/emulator/adb.exe",
        )

        with patch.object(Toolkit, "find_adb_devices", return_value=[discovered]):
            runner._resolve_adb_device(device_config)

        self.assertEqual(device_config.adbPath, "C:/emulator/adb.exe")


class MaaFWRunnerTaskTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _config(values: dict[tuple[str, str], object]) -> SimpleNamespace:
        return SimpleNamespace(get=lambda section, key: values.get((section, key)))

    def test_user_controller_and_resource_override_script_defaults(self) -> None:
        task = object.__new__(MaaFWPluginAutoProxyTask)
        task.script_config = self._config(
            {
                ("Info", "Controller"): "desktop",
                ("Info", "Resource"): "official",
                ("Emulator", "Id"): "-",
            }
        )
        task.cur_user_config = self._config(
            {
                ("Info", "Controller"): "adb",
                ("Info", "Resource"): "bilibili",
            }
        )
        interface_model = MaaFWInterface.model_validate(
            {
                "interface_version": 2,
                "name": "M9A",
                "controller": [
                    {"name": "desktop", "type": "Win32"},
                    {"name": "adb", "type": "Adb"},
                ],
                "resource": [
                    {"name": "official", "path": [], "controller": ["desktop"]},
                    {"name": "bilibili", "path": [], "controller": ["adb"]},
                ],
                "task": [],
            }
        )

        controller_name = task._select_controller_name(interface_model)
        resource_name = task._select_resource_name(interface_model, controller_name)

        self.assertEqual(controller_name, "adb")
        self.assertEqual(resource_name, "bilibili")

    def test_blank_user_controller_and_resource_inherit_script_defaults(self) -> None:
        task = object.__new__(MaaFWPluginAutoProxyTask)
        task.script_config = self._config(
            {
                ("Info", "Controller"): "desktop",
                ("Info", "Resource"): "official",
                ("Emulator", "Id"): "-",
            }
        )
        task.cur_user_config = self._config(
            {
                ("Info", "Controller"): "",
                ("Info", "Resource"): "",
            }
        )
        interface_model = MaaFWInterface.model_validate(
            {
                "interface_version": 2,
                "name": "M9A",
                "controller": [{"name": "desktop", "type": "Win32"}],
                "resource": [
                    {"name": "official", "path": [], "controller": ["desktop"]}
                ],
                "task": [],
            }
        )

        controller_name = task._select_controller_name(interface_model)
        resource_name = task._select_resource_name(interface_model, controller_name)

        self.assertEqual(controller_name, "desktop")
        self.assertEqual(resource_name, "official")

    async def test_runner_environment_log_returns_to_event_loop_thread(self) -> None:
        event_loop_thread = threading.get_ident()
        log_threads: list[int] = []
        task = object.__new__(MaaFWPluginAutoProxyTask)
        task.run_plan = SimpleNamespace()
        task.project_path = Path.cwd()

        def append_log(_message: str) -> None:
            log_threads.append(threading.get_ident())

        task._append_log = append_log

        def prepare_environment(*_args, send_log, **_kwargs):
            send_log("runner setup")
            raise RuntimeError("stop after environment log")

        with (
            patch.object(
                MaaFWRunnerService,
                "prepare_environment",
                side_effect=prepare_environment,
            ),
            patch(
                "automas_script_maafw.runner_task.get_plugin_import_paths",
                return_value=[],
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop after environment log"):
                await task._run_maafw_worker(SimpleNamespace())

        await asyncio.sleep(0)
        self.assertEqual(log_threads, [event_loop_thread])


class MaaFWAdapterConfigTest(unittest.IsolatedAsyncioTestCase):
    async def test_plugin_form_json_fields_reach_legacy_runtime(self) -> None:
        task_snapshot = {
            "taskOrder": ["崩坏三 启动！"],
            "taskChecked": {"崩坏三 启动！": True},
            "taskOptions": {
                "崩坏三 启动！": {
                    "登录方式": "账号密码",
                    "登录凭据": {
                        "账号": "captain@example.com",
                        "密码": "do-not-log-this",
                    },
                },
            },
        }
        period_records = {"weekly": {"任务": "2026-W28"}}
        user_id = "400407d9-0775-44ca-921c-8df19787b10f"
        runtime = SimpleNamespace(
            storage=SimpleNamespace(
                read_user_data_pairs=AsyncMock(
                    return_value=[
                        (
                            user_id,
                            {
                                "Task": {"TaskSnapshot": task_snapshot},
                                "Data": {"PeriodTaskRecords": period_records},
                            },
                        )
                    ]
                )
            )
        )

        users = await _load_legacy_user_config(runtime)
        script = await _load_legacy_script_config(
            {
                "Run": {
                    "DailyOnceTasks": ["每日任务"],
                    "WeeklyOnceTasks": ["每周任务"],
                    "MonthlyOnceTasks": ["每月任务"],
                }
            }
        )

        user = next(iter(users.items()))[1]
        self.assertEqual(json.loads(user.get("Task", "TaskSnapshot")), task_snapshot)
        self.assertEqual(
            json.loads(user.get("Data", "PeriodTaskRecords")),
            period_records,
        )
        self.assertEqual(json.loads(script.get("Run", "DailyOnceTasks")), ["每日任务"])
        self.assertEqual(json.loads(script.get("Run", "WeeklyOnceTasks")), ["每周任务"])
        self.assertEqual(json.loads(script.get("Run", "MonthlyOnceTasks")), ["每月任务"])

        interface_model = MaaFWInterface.model_validate(
            {
                "interface_version": 2,
                "name": "Maa_bbb",
                "controller": [{"name": "desktop", "type": "Win32"}],
                "resource": [{"name": "base", "path": []}],
                "task": [
                    {
                        "name": "崩坏三 启动！",
                        "entry": "登录方式选择接口",
                        "default_check": True,
                        "option": ["登录方式", "登录凭据"],
                    }
                ],
                "option": {
                    "登录方式": {
                        "type": "select",
                        "default_case": "游客",
                        "cases": [
                            {
                                "name": "游客",
                                "pipeline_override": {
                                    "登录方式选择接口": {"next": ["游客登录"]}
                                },
                            },
                            {
                                "name": "账号密码",
                                "pipeline_override": {
                                    "登录方式选择接口": {"next": ["账号密码登录"]}
                                },
                            },
                        ],
                    },
                    "登录凭据": {
                        "type": "input",
                        "inputs": [
                            {"name": "账号"},
                            {"name": "密码"},
                        ],
                        "pipeline_override": {
                            "登录参数": {
                                "attach": {
                                    "账号": "{账号}",
                                    "密码": "{密码}",
                                }
                            }
                        },
                    }
                },
            }
        )
        plan = MaaFWRunnerService().build_plan(
            REPO_ROOT,
            interface_model,
            task_snapshot=json.loads(user.get("Task", "TaskSnapshot")),
        )

        self.assertEqual(
            plan.tasks[0].options,
            {
                "登录方式": "账号密码",
                "登录凭据": {
                    "账号": "captain@example.com",
                    "密码": "do-not-log-this",
                },
            },
        )
        self.assertEqual(
            plan.tasks[0].pipelineOverride,
            {
                "登录方式选择接口": {"next": ["账号密码登录"]},
                "登录参数": {
                    "attach": {
                        "账号": "captain@example.com",
                        "密码": "do-not-log-this",
                    }
                },
            },
        )
        self.assertEqual(
            plan.tasks[0].logOptions,
            {
                "登录方式": "账号密码",
                "登录凭据": {
                    "账号": "<已配置>",
                    "密码": "<已配置>",
                },
            },
        )
        self.assertEqual(
            plan.tasks[0].overrideNodes,
            ["登录方式选择接口", "登录参数"],
        )

        overview_log = _format_run_overview_log(
            plan,
            selected_preset="日常",
        )
        task_log = _format_task_config_log(plan.tasks[0])
        self.assertIn("enabled_tasks(1)=崩坏三 启动！", overview_log)
        self.assertIn('"登录方式":"账号密码"', task_log)
        self.assertIn('"账号":"<已配置>"', task_log)
        self.assertIn("override_nodes=登录方式选择接口, 登录参数", task_log)
        self.assertNotIn("captain@example.com", overview_log + task_log)
        self.assertNotIn("do-not-log-this", overview_log + task_log)


class MaaFWAdapterFinalizeTest(unittest.IsolatedAsyncioTestCase):
    async def test_finalize_preserves_check_failure_status(self) -> None:
        runtime = SimpleNamespace(
            mode="AutoProxy",
            user_config=None,
            check_result="请设置 MaaFW 项目路径",
            script_info=SimpleNamespace(status="异常", user_list=[]),
            storage=SimpleNamespace(unlock=AsyncMock()),
        )

        await MaaFWAdapterHooks().finalize(runtime)

        self.assertEqual(runtime.script_info.status, "异常")

    async def test_finalize_preserves_prepare_crash_status(self) -> None:
        runtime = SimpleNamespace(
            mode="AutoProxy",
            user_config=None,
            check_result="-",
            script_info=SimpleNamespace(status="异常", user_list=[]),
            storage=SimpleNamespace(unlock=AsyncMock()),
        )

        await MaaFWAdapterHooks().finalize(runtime)

        self.assertEqual(runtime.script_info.status, "异常")


if __name__ == "__main__":
    unittest.main()
