from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ok_script_adapter.adapter.autoproxy import (
    _build_descriptor_provider,
    _resolve_descriptor_provider,
)
from ok_script_adapter.plugin import (
    _descriptor_with_provider,
    _provider_client_metadata,
)
from ok_script_adapter.providers.okww import OKWW_PROVIDER
from ok_script_adapter.shell.descriptor import (
    OK_PROJECT_DESCRIPTOR_SCHEMA_VERSION,
    PROTOCOL_FRAMEWORK_CLI,
    OkProjectDescriptor,
)
from ok_script_adapter.shell.manifest import (
    inspect_ok_project,
    load_manifest,
    save_manifest,
)
from ok_script_adapter.shell.parser import ProjectParser
from ok_script_adapter.shell.runtime import OkShellRunner

from project_fixtures import PROJECT_FIXTURE_SPECS, build_project_fixture


def _write_config(path: Path, *, config_folder: str = "configs") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "version = '2.0.0'\n"
        "tasks = [('fixture.tasks', 'DailyTask')]\n"
        "config = {\n"
        f"    'config_folder': '{config_folder}',\n"
        "    'gui_title': 'Fixture Game',\n"
        "    'log_file': 'logs/fixture.log',\n"
        "    'onetime_tasks': tasks,\n"
        "}\n"
        "raise RuntimeError('config.py must not be executed')\n",
        encoding="utf-8",
    )


class ProjectParserFixtureTest(unittest.TestCase):
    def test_five_projects_cover_source_and_installed_descriptors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            for spec in PROJECT_FIXTURE_SPECS:
                with self.subTest(spec=spec.name):
                    fixture = build_project_fixture(base_dir, spec)
                    descriptor = ProjectParser(fixture.root).parse()

                    expected_target = (
                        "src.config:config"
                        if spec.config_location == "src/config.py"
                        else "config:config"
                    )
                    self.assertEqual(
                        descriptor.schema_version,
                        OK_PROJECT_DESCRIPTOR_SCHEMA_VERSION,
                    )
                    self.assertEqual(descriptor.resource_name, spec.resource_name)
                    self.assertEqual(descriptor.working_dir, fixture.working_dir.resolve())
                    self.assertEqual(descriptor.config_source, fixture.config_source.resolve())
                    self.assertEqual(descriptor.config_target, expected_target)
                    self.assertEqual(descriptor.config_folder, spec.config_folder)
                    self.assertEqual(descriptor.config_dir, fixture.config_dir.resolve())
                    self.assertEqual(
                        tuple(task.selector for task in descriptor.tasks),
                        spec.tasks,
                    )
                    self.assertTrue(descriptor.capabilities.config.verified)
                    self.assertTrue(descriptor.capabilities.task.verified)
                    self.assertFalse(descriptor.capabilities.runtime.verified)
                    self.assertIn(
                        "config-python",
                        {source.kind for source in descriptor.metadata_sources},
                    )

    def test_root_src_working_and_repo_config_targets(self) -> None:
        cases = (
            ("config.py", "config:config", Path(".")),
            ("src/config.py", "src.config:config", Path(".")),
            ("working/config.py", "config:config", Path("working")),
            ("working/src/config.py", "src.config:config", Path("working")),
            ("repo/config.py", "config:config", Path("repo")),
            ("repo/src/config.py", "src.config:config", Path("repo")),
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            for index, (location, target, working_relative) in enumerate(cases):
                with self.subTest(location=location):
                    root = base_dir / str(index) / "ok-custom"
                    root.mkdir(parents=True)
                    (root / "pyappify.yml").write_text(
                        "name: ok-custom\n",
                        encoding="utf-8",
                    )
                    _write_config(
                        root / location,
                        config_folder="settings/profiles",
                    )
                    expected_working = (root / working_relative).resolve()
                    expected_config = expected_working / "settings" / "profiles"
                    expected_config.mkdir(parents=True)

                    descriptor = inspect_ok_project(root)

                    self.assertEqual(descriptor.config_target, target)
                    self.assertEqual(descriptor.working_dir, expected_working)
                    self.assertEqual(descriptor.config_dir, expected_config.resolve())
                    self.assertEqual(descriptor.config_folder, "settings/profiles")

    def test_parser_never_executes_config_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "ok-static"
            root.mkdir()
            (root / "pyappify.yml").write_text(
                "name: ok-static\n",
                encoding="utf-8",
            )
            _write_config(root / "config.py")

            descriptor = inspect_ok_project(root)

            self.assertEqual(descriptor.tasks[0].selector, "DailyTask")
            self.assertEqual(descriptor.gui_title, "Fixture Game")

    def test_dynamic_config_object_is_not_reported_as_verified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "ok-dynamic"
            root.mkdir()
            (root / "pyappify.yml").write_text(
                "name: ok-dynamic\n",
                encoding="utf-8",
            )
            (root / "config.py").write_text(
                "version = '3.0.0'\n"
                "config = build_config()\n"
                "raise RuntimeError('config.py must not be executed')\n",
                encoding="utf-8",
            )

            descriptor = inspect_ok_project(root)

            self.assertEqual(descriptor.project_version, "3.0.0")
            self.assertFalse(descriptor.capabilities.config.available)
            self.assertFalse(descriptor.capabilities.config.verified)
            self.assertIn(
                "CONFIG_OBJECT_MISSING",
                {item.code for item in descriptor.diagnostics},
            )

    def test_fingerprint_changes_with_project_metadata(self) -> None:
        spec = next(item for item in PROJECT_FIXTURE_SPECS if item.name == "okww-source")
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture = build_project_fixture(Path(tmp_dir), spec)
            original = inspect_ok_project(fixture.root)
            content = fixture.config_source.read_text(encoding="utf-8")
            fixture.config_source.write_text(
                content.replace("FarmEchoTask", "SimulationTask"),
                encoding="utf-8",
            )
            changed = inspect_ok_project(fixture.root)

            self.assertNotEqual(original.fingerprint, changed.fingerprint)
            self.assertEqual(changed.tasks[1].selector, "SimulationTask")


class DescriptorCompatibilityTest(unittest.TestCase):
    def test_v1_manifest_migrates_and_round_trips_as_v2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "ok-v1"
            root.mkdir()
            _write_config(root / "src" / "config.py")
            config_dir = root / "configs"
            config_dir.mkdir()
            v1 = {
                "schemaVersion": 1,
                "adapterApiVersion": 1,
                "rootPath": str(root),
                "workingDirectory": str(root),
                "resourceName": "ok-v1",
                "displayName": "OK V1",
                "projectVersion": "1.0.0",
                "pythonExecutable": sys.executable,
                "configTarget": "src.config:config",
                "configDirectory": str(config_dir),
                "logPath": str(root / "logs" / "ok-script.log"),
                "tasks": [
                    {
                        "selector": "DailyTask",
                        "index": 1,
                        "module": "fixture.tasks",
                        "className": "DailyTask",
                        "label": "DailyTask",
                    }
                ],
                "protocols": [PROTOCOL_FRAMEWORK_CLI],
                "defaultProtocol": PROTOCOL_FRAMEWORK_CLI,
                "fingerprint": "legacy",
            }

            descriptor = OkProjectDescriptor.from_dict(v1)
            saved_path = root / "descriptor.json"
            save_manifest(descriptor, saved_path)
            loaded = load_manifest(saved_path)
            serialized = json.loads(saved_path.read_text(encoding="utf-8"))

            self.assertEqual(
                descriptor.schema_version,
                OK_PROJECT_DESCRIPTOR_SCHEMA_VERSION,
            )
            self.assertEqual(descriptor.config_source, (root / "src" / "config.py").resolve())
            self.assertFalse(descriptor.capabilities.runtime.verified)
            self.assertIn(
                "DESCRIPTOR_V1_MIGRATED",
                {item.code for item in descriptor.diagnostics},
            )
            self.assertEqual(serialized["schemaVersion"], 2)
            self.assertEqual(loaded.to_dict(), descriptor.to_dict())


class DescriptorConsumerTest(unittest.TestCase):
    def test_unknown_project_runtime_is_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "ok-unknown"
            root.mkdir()
            (root / "pyappify.yml").write_text(
                "name: ok-unknown\n",
                encoding="utf-8",
            )
            _write_config(root / "config.py")
            descriptor = inspect_ok_project(
                root,
                python_executable=sys.executable,
            )
            provider = _build_descriptor_provider(descriptor)

            self.assertTrue(descriptor.capabilities.runtime.available)
            self.assertFalse(descriptor.capabilities.runtime.verified)
            self.assertFalse(provider.runtime_verified)
            self.assertIn("尚未验证", provider.runtime_block_reason)

    def test_provider_metadata_uses_descriptor_task_set(self) -> None:
        spec = next(item for item in PROJECT_FIXTURE_SPECS if item.name == "okww-source")
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture = build_project_fixture(Path(tmp_dir), spec)
            descriptor = inspect_ok_project(fixture.root)
            metadata = _provider_client_metadata(descriptor, OKWW_PROVIDER)

            self.assertEqual(
                metadata["taskOptions"],
                [
                    {"value": 1, "label": "DailyTask（日常）"},
                    {"value": 2, "label": "FarmEchoTask"},
                ],
            )
            self.assertFalse(metadata["runtimeVerified"])
            self.assertIn("未探测到", metadata["runtimeBlockReason"])

            runnable_descriptor = _descriptor_with_provider(
                inspect_ok_project(
                    fixture.root,
                    python_executable=sys.executable,
                ),
                OKWW_PROVIDER,
            )
            runnable_metadata = _provider_client_metadata(
                runnable_descriptor,
                OKWW_PROVIDER,
            )
            self.assertTrue(runnable_metadata["runtimeVerified"])
            self.assertEqual(runnable_metadata["runtimeBlockReason"], "")

    def test_autoproxy_runtime_requires_provider_and_protocol_candidate(self) -> None:
        spec = next(item for item in PROJECT_FIXTURE_SPECS if item.name == "okww-source")
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture = build_project_fixture(Path(tmp_dir), spec)

            blocked, blocked_provider, provider_registered = (
                _resolve_descriptor_provider(inspect_ok_project(fixture.root))
            )
            self.assertIs(blocked_provider, OKWW_PROVIDER)
            self.assertTrue(provider_registered)
            self.assertFalse(blocked.capabilities.runtime.available)
            self.assertFalse(blocked.capabilities.runtime.verified)

            runnable, runnable_provider, provider_registered = (
                _resolve_descriptor_provider(
                    inspect_ok_project(
                        fixture.root,
                        python_executable=sys.executable,
                    )
                )
            )
            self.assertIs(runnable_provider, OKWW_PROVIDER)
            self.assertTrue(provider_registered)
            self.assertTrue(runnable.capabilities.runtime.available)
            self.assertTrue(runnable.capabilities.runtime.verified)

    def test_framework_cli_launch_uses_descriptor_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "ok-working"
            root.mkdir()
            (root / "pyappify.yml").write_text(
                "name: ok-working\n",
                encoding="utf-8",
            )
            _write_config(root / "working" / "config.py")
            descriptor = inspect_ok_project(
                root,
                python_executable=sys.executable,
            )
            runner = OkShellRunner(descriptor)
            with patch.object(
                runner,
                "available_protocols",
                return_value=(PROTOCOL_FRAMEWORK_CLI,),
            ):
                launch_spec = runner.build_launch_spec(
                    "1",
                    protocol=PROTOCOL_FRAMEWORK_CLI,
                )

            self.assertEqual(launch_spec.cwd, (root / "working").resolve())
            self.assertIn("config:config", launch_spec.command)


if __name__ == "__main__":
    unittest.main()
