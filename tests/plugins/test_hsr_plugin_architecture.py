from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from automas_hsr_adapter_m7a.catalog import M7ATaskCatalog
from automas_hsr_adapter_m7a.controller import M7AController
from automas_hsr_adapter_m7a.control import HSRM7AControl
from automas_hsr_adapter_m7a.plugin import Plugin as M7APlugin
from automas_hsr_adapter_m7a.runtime import M7AControllerSessionImpl
from automas_hsr_adapter_m7a.runner import M7ARunner
from automas_hsr_adapter_sra.catalog import SRATaskCatalog
from automas_hsr_adapter_sra.controller import SRAController
from automas_hsr_adapter_sra.plugin import Plugin as SRAPlugin
from automas_hsr_adapter_sra.runtime import SRAControllerSessionImpl
from automas_hsr_adapter_sra.runner import build_sra_module_config, run_sra_single_task
from automas_script_hsr.adapter import HSRAdapterHooks
from automas_script_hsr.contracts import HSRRunResult
from automas_script_hsr.plugin import Plugin as HSRPlugin
from automas_script_hsr.registry import HSRRegistryService, resolve_configured_engines
from automas_script_hsr.runtime.autoproxy import HSRAutoProxyTask
from automas_script_hsr.runtime.locks import (
    acquire_external_path_locks,
    release_external_path_locks,
)
from automas_script_hsr.runtime.manager import HSRManager, _resolve_external_lock_paths
from automas_script_hsr.runtime.models import (
    HSRRetryableTaskError,
    HSRRunItem,
    HSRRuntimeState,
)
from automas_script_hsr.runtime.tasks import (
    HSR_TASK_MODULE_MAP,
    get_assigned_script,
)
from automas_script_hsr.runtime.notify import render_hsr_mail_template
from automas_script_hsr.schema import (
    HSRConfig,
    HSRRunConfig,
    HSRUserConfig,
    HSRUserDataConfig,
    HSRUserTaskSwitchConfig,
    build_hsr_tags,
)
from app.models.plugin_script_config import PluginScriptConfig
from app.plugins import ScriptAdapterDefinition
from app.plugins.server import PluginHttpRequest
from app.plugins.script_config_store import ScriptConfigStore
from app.models.schema import ScriptCreateIn, ScriptCreateOut, UserCreateOut
from app.models.task import UserItem
from app.utils.constants import UTC8


def _provider(registry: HSRRegistryService):
    return ScriptAdapterDefinition(
        type_key="HSR",
        display_name="HSR脚本",
        hooks_factory=HSRAdapterHooks,
        script_model=HSRConfig,
        user_model=HSRUserConfig,
        supported_modes=("AutoProxy", "ManualReview"),
        record_capability_resolver=registry.resolve_record_capability,
    ).build_provider(owner="test")


class _PathConfig:
    def __init__(self, *engines: str, mapping: str = "SRA") -> None:
        self.paths = {engine: f"C:/{engine}" for engine in engines}
        self.mapping = mapping

    def get(self, group: str, key: str):
        if key == "Path":
            return self.paths.get(group)
        if group == "TaskMapping":
            return self.mapping
        return None


def test_registry_exposes_atomic_engine_matrix() -> None:
    registry = HSRRegistryService()
    assert registry.snapshot().effective_engines == ()

    registry.register_group(
        owner="sra",
        task_catalog=SRATaskCatalog(),
        controller=SRAController(),
    )
    sra_only = registry.snapshot(script_config=_PathConfig("SRA", "M7A"))
    assert sra_only.effective_engines == ("SRA",)
    assert sra_only.supported_modes == ("AutoProxy", "ManualReview")

    registry.register_group(
        owner="m7a",
        task_catalog=M7ATaskCatalog(),
        controller=M7AController(),
    )
    both = registry.snapshot(script_config=_PathConfig("M7A", "SRA"))
    assert both.effective_engines == ("SRA", "M7A")
    assert {task["key"] for task in both.tasks} == {
        "Daily",
        "ReceiveRewards",
        "DivergentUniverse",
        "CurrencyWars",
    }
    assert "abyss_snapshot" not in M7ATaskCatalog().descriptor.capabilities

    assert registry.unregister_owner("sra") == ("SRA",)
    assert registry.snapshot(script_config=_PathConfig("SRA", "M7A")).effective_engines == (
        "M7A",
    )


def test_sra_currency_wars_runs_once() -> None:
    currency_wars = HSR_TASK_MODULE_MAP["CurrencyWars"]

    config = build_sra_module_config(
        currency_wars,
        _PathConfig("SRA"),
        _PathConfig(),
    )

    assert config["cosmicStrife"]["currencyWars.runtimes"] == 1


def test_hsr_completed_currency_wars_tag_keeps_task_label() -> None:
    now = datetime.now(tz=UTC8)
    year, week, _ = now.isocalendar()

    class Config:
        values = {
            ("Data", "WeeklyCompletedThisWeek"): True,
            ("Data", "WeeklyLastResetWeek"): f"{year:04d}-W{week:02d}",
            ("TaskSwitch", "CurrencyWars"): True,
        }

        def get(self, group: str, key: str):
            return self.values.get((group, key))

    tags = json.loads(build_hsr_tags(Config()))

    assert {"text": "货币战争 已完成", "color": "green"} in tags


def test_host_script_crud_no_longer_declares_legacy_hsr_config_models() -> None:
    from app.api.scripts import SCRIPT_BOOK, USER_BOOK

    assert "HSRConfig" not in SCRIPT_BOOK
    assert "HSRConfig" not in USER_BOOK
    assert "HSR" not in str(ScriptCreateIn.model_fields["type"].annotation)
    assert "HSRConfig" not in str(ScriptCreateOut.model_fields["data"].annotation)
    assert "HSRUserConfig" not in str(UserCreateOut.model_fields["data"].annotation)


def test_registry_rejects_engine_owner_conflict() -> None:
    registry = HSRRegistryService()
    registry.register_group(
        owner="first",
        task_catalog=SRATaskCatalog(),
        controller=SRAController(),
    )
    with pytest.raises(ValueError, match="first"):
        registry.register_group(
            owner="second",
            task_catalog=SRATaskCatalog(),
            controller=SRAController(),
        )


def test_snapshot_never_probes_or_exposes_an_unconfigured_engine() -> None:
    class CountingController:
        def __init__(self, descriptor) -> None:
            self.descriptor = descriptor
            self.probe_count = 0

        def probe(self, _script_config):
            self.probe_count += 1
            return True, ""

        async def open_session(self, **_kwargs):
            raise AssertionError("snapshot must not open a session")

    registry = HSRRegistryService()
    sra = CountingController(SRATaskCatalog().descriptor)
    m7a = CountingController(M7ATaskCatalog().descriptor)
    registry.register_group(
        owner="sra",
        task_catalog=SRATaskCatalog(),
        controller=sra,
    )
    registry.register_group(
        owner="m7a",
        task_catalog=M7ATaskCatalog(),
        controller=m7a,
    )

    snapshot = registry.snapshot(script_config=_PathConfig("SRA"))

    assert snapshot.effective_engines == ("SRA",)
    assert sra.probe_count == 1
    assert m7a.probe_count == 0
    assert {adapter["engine"] for adapter in snapshot.adapters} == {"SRA"}
    assert all("M7A" not in task["engines"] for task in snapshot.tasks)


def test_registry_closes_tracked_sessions_before_adapter_unload() -> None:
    async def scenario() -> None:
        class Session:
            def __init__(self) -> None:
                self.close_count = 0

            async def close(self) -> None:
                self.close_count += 1

        registry = HSRRegistryService()
        registry.register_group(
            owner="sra",
            task_catalog=SRATaskCatalog(),
            controller=SRAController(),
        )
        session = Session()
        registry.track_session("SRA", session)

        assert await registry.close_owner_sessions("sra") == ()
        assert session.close_count == 1
        assert await registry.close_owner_sessions("sra") == ()
        assert session.close_count == 1

    asyncio.run(scenario())


def test_auto_proxy_executes_modules_through_unified_session_contract() -> None:
    async def scenario() -> None:
        class Session:
            def __init__(self, result: HSRRunResult) -> None:
                self.result = result
                self.requests = []

            async def run(self, request):
                self.requests.append(request)
                return self.result

        registry = HSRRegistryService()
        registry.register_group(
            owner="sra",
            task_catalog=SRATaskCatalog(),
            controller=SRAController(),
        )
        native_result = SimpleNamespace(success=True, output="completed")
        session = Session(
            HSRRunResult(
                status="completed",
                completion_evidence={"returncode": 0},
                native_result=native_result,
            )
        )
        runtime = HSRRuntimeState(log_lines=[], completion_writebacks=[])
        runtime.registry = registry
        runtime.sessions["SRA"] = session
        proxy = HSRAutoProxyTask.__new__(HSRAutoProxyTask)
        proxy.runtime = runtime
        proxy.script_info = SimpleNamespace(script_id="script-id", log="")
        proxy.script_config = object()
        proxy._log_lines = []
        proxy._current_user_log = None

        direct_run_count = 0

        async def direct_run():
            nonlocal direct_run_count
            direct_run_count += 1
            return native_result

        item = HSRRunItem(
            user_item=UserItem("user-id", "用户", "等待"),
            user_cfg=object(),
            user_name="用户",
            user_id="user-id",
            phase="daily",
            module_key="Daily",
            module_name="日常模块",
            script="SRA",
            description="contract test",
            timeout_seconds=30,
            run=direct_run,
            extra={"daily_eow_enabled": True},
        )

        result = await proxy._execute_run_item(item)
        assert result.native_result is native_result
        assert direct_run_count == 0
        assert len(session.requests) == 1
        assert session.requests[0].task.key == "Daily"
        assert session.requests[0].extra == {"daily_eow_enabled": True}
        assert "native_result" not in result.asdict()

        login_item = HSRRunItem(
            user_item=item.user_item,
            user_cfg=item.user_cfg,
            user_name=item.user_name,
            user_id=item.user_id,
            phase="daily",
            module_key="StartGame",
            module_name="SRA login",
            script="SRA",
            description="login through adapter capability",
            timeout_seconds=30,
            run=direct_run,
            extra={"phase": "daily"},
        )
        await proxy._execute_run_item(login_item)
        assert direct_run_count == 0
        assert session.requests[1].task.key == "StartGame"
        assert session.requests[1].task.native_tasks == ("StartGameTask",)

        session.result = HSRRunResult(status="completed")
        with pytest.raises(HSRRetryableTaskError, match="完成证据"):
            await proxy._execute_run_item(item)

    asyncio.run(scenario())


def test_auto_proxy_opens_sessions_only_for_effective_engines() -> None:
    async def scenario() -> None:
        class Session:
            async def run(self, _request):
                raise AssertionError("session must not run during open")

            async def cancel(self) -> None:
                return None

            async def close(self) -> None:
                return None

        class Controller:
            def __init__(self, descriptor) -> None:
                self.descriptor = descriptor
                self.open_count = 0

            def probe(self, _script_config):
                return True, ""

            async def open_session(self, **_kwargs):
                self.open_count += 1
                return Session()

        registry = HSRRegistryService()
        sra = Controller(SRATaskCatalog().descriptor)
        m7a = Controller(M7ATaskCatalog().descriptor)
        registry.register_group(
            owner="sra",
            task_catalog=SRATaskCatalog(),
            controller=sra,
        )
        registry.register_group(
            owner="m7a",
            task_catalog=M7ATaskCatalog(),
            controller=m7a,
        )
        proxy = HSRAutoProxyTask.__new__(HSRAutoProxyTask)
        proxy.runtime = HSRRuntimeState(
            log_lines=[],
            completion_writebacks=[],
            registry=registry,
        )
        proxy.script_config = SimpleNamespace(_hsr_effective_engines=("M7A",))
        proxy.script_info = SimpleNamespace(script_id="script")

        await proxy._open_adapter_sessions()

        assert sra.open_count == 0
        assert m7a.open_count == 1
        assert set(proxy.runtime.sessions) == {"M7A"}
        assert await registry.close_all_sessions() == ()

    asyncio.run(scenario())


def test_semantic_incomplete_result_is_not_overwritten_as_completed() -> None:
    async def scenario() -> None:
        proxy = HSRAutoProxyTask.__new__(HSRAutoProxyTask)
        proxy.runtime = HSRRuntimeState(log_lines=[], completion_writebacks=[])
        proxy._log_lines = []
        proxy.script_info = SimpleNamespace(log="")
        proxy._current_user_log = None

        async def run_item(_item):
            return HSRRunResult(
                status="completed",
                completion_evidence={"returncode": 0},
                native_result=SimpleNamespace(success=True),
            )

        async def restart_game(_user_name: str, _reason: str) -> None:
            return None

        proxy._run_item_with_game_guard = run_item
        proxy._restart_game = restart_game

        def mark_incomplete(_result) -> None:
            proxy._record_module_result(
                user_id="user",
                user_name="user",
                module_key="DivergentUniverse",
                module_name="weekly",
                script="SRA",
                status="incomplete",
                reason="completion marker missing",
            )

        item = HSRRunItem(
            user_item=UserItem("user", "user", "waiting"),
            user_cfg=object(),
            user_name="user",
            user_id="user",
            phase="weekly",
            module_key="DivergentUniverse",
            module_name="weekly",
            script="SRA",
            description="semantic evidence test",
            timeout_seconds=30,
            run=lambda: None,
            on_success=mark_incomplete,
        )

        assert await proxy._run_queue_items([item]) == []
        assert proxy.runtime.module_results[0].status == "incomplete"

    asyncio.run(scenario())


def test_adapter_sessions_restore_external_config_idempotently() -> None:
    asyncio.run(_assert_adapter_sessions_restore_idempotently())


def test_m7a_patch_is_atomic_whitelisted_and_preserves_unrelated_config() -> None:
    with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        config_path = Path(temp_dir) / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "unrelated": {"keep": True},
                    "weekly_divergent_stable_mode": False,
                    "notification_enable": True,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        HSRM7AControl.write_m7a_patch(
            config_path,
            {
                "weekly_divergent_stable_mode": True,
                "must_not_be_written": "blocked",
            },
            whitelist=frozenset({"weekly_divergent_stable_mode"}),
        )

        result = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert result["unrelated"] == {"keep": True}
        assert result["weekly_divergent_stable_mode"] is True
        assert result["notification_enable"] is False
        assert "must_not_be_written" not in result
        assert config_path.with_name("config.yaml.tmp").exists() is False


def test_sra_runner_uses_documented_inline_single_command_boundary() -> None:
    async def scenario() -> None:
        class Process:
            stdout = None
            stderr = None
            returncode = 0

            async def communicate(self):
                return b"completed", b""

        class Registry:
            def __init__(self) -> None:
                self.call = None
                self.cleared = 0

            async def open_process(self, program, *args, cwd):
                self.call = (program, args, cwd)
                return Process()

            async def clear(self) -> None:
                self.cleared += 1

        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            executable = root / "SRA-cli.exe"
            config = root / "task.json"
            executable.touch()
            config.write_text("{}", encoding="utf-8")
            registry = Registry()

            result = await run_sra_single_task(
                executable,
                "TrailblazePowerTask",
                config,
                process_registry=registry,
            )

            assert result.success is True
            assert registry.call == (
                str(executable),
                (
                    "--inline",
                    f'single TrailblazePowerTask --config "{config}"',
                    "quit",
                ),
                executable.parent,
            )
            assert registry.cleared == 1

    asyncio.run(scenario())


def test_m7a_runner_passes_the_native_task_as_single_cli_argument() -> None:
    async def scenario() -> None:
        class Process:
            stdout = None
            stderr = None
            stdin = None
            returncode = 0

            async def communicate(self):
                return b"completed", b""

        class ProcessManager:
            def __init__(self) -> None:
                self.main_process = Process()
                self.call = None
                self.cleared = 0

            async def open_process(self, program, *args, **kwargs) -> None:
                self.call = (program, args, kwargs)

            async def clear(self) -> None:
                self.cleared += 1

        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            executable = root / "March7th Assistant.exe"
            executable.touch()
            runner = M7ARunner(root)
            process_manager = ProcessManager()
            runner._process_manager = process_manager

            with patch(
                "automas_hsr_adapter_m7a.runner.asyncio.subprocess.Process",
                Process,
            ):
                result = await runner.run_task("routine")

            assert result.success is True
            assert process_manager.call[0] == str(executable)
            assert process_manager.call[1] == ("routine",)
            assert process_manager.call[2]["cwd"] == root
            assert process_manager.cleared == 1

    asyncio.run(scenario())


def test_hsr_notification_templates_are_packaged_and_escape_user_content() -> None:
    html = render_hsr_mail_template(
        "result.html",
        {
            "title": "HSR <result>",
            "script_name": "script",
            "start_time": "start",
            "end_time": "end",
            "completed_count": 1,
            "uncompleted_count": 0,
            "result": "<script>alert(1)</script>",
        },
    )
    assert "HSR &lt;result&gt;" in html
    assert "<script>alert(1)</script>" not in html


async def _assert_adapter_sessions_restore_idempotently() -> None:
    class Terminator:
        def __init__(self) -> None:
            self.count = 0

        async def terminate_current_process(self) -> None:
            self.count += 1

    with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        root = Path(temp_dir)

        m7a_root = root / "M7A"
        m7a_root.mkdir()
        config_path = m7a_root / "config.yaml"
        backup_path = root / "M7A-session-config.yaml"
        config_path.write_text("patched: true\n", encoding="utf-8")
        backup_path.write_text("original: true\n", encoding="utf-8")
        m7a_terminator = Terminator()
        m7a_session = M7AControllerSessionImpl.__new__(M7AControllerSessionImpl)
        m7a_session.config_path = config_path
        m7a_session.backup_path = backup_path
        m7a_session.config_existed = True
        m7a_session._closed = False
        m7a_session.runner = m7a_terminator

        await m7a_session.close()
        await m7a_session.close()
        assert config_path.read_text(encoding="utf-8") == "original: true\n"
        assert backup_path.exists() is False
        assert m7a_terminator.count == 1

        sra_source = root / "settings.json"
        sra_backup = root / "SRA-session" / "settings.json"
        sra_source.write_text('{"patched": true}', encoding="utf-8")
        sra_backup.parent.mkdir()
        sra_backup.write_text('{"original": true}', encoding="utf-8")
        sra_terminator = Terminator()
        sra_session = SRAControllerSessionImpl.__new__(SRAControllerSessionImpl)
        sra_session.process_registry = sra_terminator
        sra_session.temp_files = []
        sra_session._backup_root = sra_backup.parent
        sra_session._backup_targets = [(sra_source, sra_backup, True)]
        sra_session._closed = False

        await sra_session.close()
        await sra_session.close()
        assert sra_source.read_text(encoding="utf-8") == '{"original": true}'
        assert sra_backup.parent.exists() is False
        assert sra_terminator.count == 1


@pytest.mark.parametrize(
    ("plugin_class", "catalog_key", "controller_key"),
    (
        (SRAPlugin, "hsr.task_catalog.sra.v1", "hsr.controller.sra.v1"),
        (M7APlugin, "hsr.task_catalog.m7a.v1", "hsr.controller.m7a.v1"),
    ),
)
def test_adapter_start_rolls_back_incomplete_service_publication(
    plugin_class,
    catalog_key: str,
    controller_key: str,
) -> None:
    class Registry:
        def __init__(self) -> None:
            self.registered = False

        def register_group(self, **_kwargs) -> None:
            self.registered = True

        def unregister_owner(self, _owner: str) -> None:
            self.registered = False

    class Context:
        instance_id = "adapter-test"

        def __init__(self) -> None:
            self.registry = Registry()
            self.services: dict[str, object | None] = {}

        def get(self, key: str):
            return self.registry if key == "hsr.registry.v1" else self.services.get(key)

        def set(self, key: str, value) -> None:
            if key == controller_key and value is not None:
                raise RuntimeError("publish failed")
            self.services[key] = value

    context = Context()
    with pytest.raises(RuntimeError, match="publish failed"):
        asyncio.run(plugin_class(context).on_start())

    assert context.registry.registered is False
    assert context.services[catalog_key] is None
    assert context.services[controller_key] is None


def test_configured_paths_intersect_active_adapters() -> None:
    registry = HSRRegistryService()
    registry.register_group(
        owner="sra",
        task_catalog=SRATaskCatalog(),
        controller=SRAController(),
    )
    capability = registry.resolve_record_capability(
        {"M7A": {"Path": r"D:\M7A"}}
    )
    assert capability.available is False
    assert capability.supported_modes == ()

    selected_sra = registry.resolve_record_capability({"SRA": {"Path": r"D:\SRA"}})
    assert selected_sra.available is True
    assert selected_sra.supported_modes == ("AutoProxy", "ManualReview")


def test_hsr_config_has_no_separate_engine_selection() -> None:
    assert "Engine" not in HSRConfig.model_fields
    assert resolve_configured_engines(HSRConfig()) == ()
    assert "MonthlyTimeLimit" not in HSRRunConfig.model_fields
    assert "ForgottenHall" not in HSRUserTaskSwitchConfig.model_fields
    assert "AbyssCompletedThisMonth" not in HSRUserDataConfig.model_fields


def test_new_hsr_script_does_not_persist_an_engine_selection() -> None:
    registry = HSRRegistryService()
    registry.register_group(
        owner="sra",
        task_catalog=SRATaskCatalog(),
        controller=SRAController(),
    )
    registry.register_group(
        owner="m7a",
        task_catalog=M7ATaskCatalog(),
        controller=M7AController(),
    )
    plugin = HSRPlugin.__new__(HSRPlugin)
    plugin.registry = registry
    definition = plugin.build_script_adapters()[0]
    assert "initial_config_factory" not in definition.metadata
    assert "legacy_config_migrator" not in definition.metadata
    assert definition.legacy_config_class_name is None
    assert definition.legacy_user_config_class_name is None
    assert not hasattr(HSRPlugin, "_import_m7a_abyss_snapshot")
    assert resolve_configured_engines(definition.script_model()) == ()


def test_task_assignment_uses_only_effective_engines_and_preserves_mapping() -> None:
    daily = HSR_TASK_MODULE_MAP["Daily"]

    assert get_assigned_script(daily, _PathConfig("SRA", mapping="M7A")) == "SRA"
    assert get_assigned_script(daily, _PathConfig("M7A", mapping="SRA")) == "M7A"
    assert get_assigned_script(daily, _PathConfig("SRA", "M7A", mapping="M7A")) == "M7A"


def test_clearing_an_engine_path_preserves_its_namespaced_configuration() -> None:
    async def scenario() -> None:
        provider = _provider(HSRRegistryService())
        storage = PluginScriptConfig()
        await storage.set("Meta", "PluginTypeKey", "HSR")
        store = ScriptConfigStore(
            provider=provider,
            storage_script_config=storage,
        )
        await store.write_script_data(
            {
                "SRA": {"Path": r"D:\SRA"},
                "M7A": {
                    "Path": r"D:\M7A",
                    "LowPerformanceMode": True,
                },
                "TaskMapping": {"Daily": "M7A"},
            }
        )

        await store.update_script_data({"M7A": {"Path": ""}})
        data = await store.read_script_data()

        assert resolve_configured_engines(data) == ("SRA",)
        assert data["M7A"]["Path"] == ""
        assert data["M7A"]["LowPerformanceMode"] is True
        assert data["TaskMapping"]["Daily"] == "M7A"

    asyncio.run(scenario())


def test_m7a_only_runs_the_first_persisted_executable_account() -> None:
    manager = HSRManager.__new__(HSRManager)
    manager.effective_engines = ("M7A",)
    assert manager._m7a_only_skip_reason(0) is None
    assert "M7A-only" in manager._m7a_only_skip_reason(1)

    manager.effective_engines = ("SRA", "M7A")
    assert manager._m7a_only_skip_reason(1) is None


def test_plugin_api_rejects_unconfigured_engine_with_envelope() -> None:
    async def scenario() -> None:
        class Config:
            def get(self, group: str, key: str):
                if group == "SRA" and key == "Path":
                    return r"D:\SRA"
                return None

        registry = HSRRegistryService()
        registry.register_group(
            owner="sra",
            task_catalog=SRATaskCatalog(),
            controller=SRAController(),
        )
        registry.register_group(
            owner="m7a",
            task_catalog=M7ATaskCatalog(),
            controller=M7AController(),
        )
        plugin = HSRPlugin.__new__(HSRPlugin)
        plugin.registry = registry

        async def load_script(_script_id: str):
            return object(), Config()

        plugin._load_script = load_script
        stage_response = await plugin._stage_options(
            PluginHttpRequest(
                method="GET",
                path="/hsr/v1/stage-options",
                query={"scriptId": "script", "engine": "M7A"},
                headers={},
                body=b"",
                json=None,
                instance_id="hsr",
            )
        )
        assert stage_response.status_code == 409
        assert stage_response.body["code"] == 409
        assert stage_response.body["status"] == "error"
        assert stage_response.body["data"] is None

    asyncio.run(scenario())


def test_external_root_lock_serializes_same_upstream_directory() -> None:
    async def scenario() -> None:
        external_root = Path.cwd() / "test-external-root"
        first = await acquire_external_path_locks([external_root])
        waiting = asyncio.create_task(acquire_external_path_locks([external_root]))
        await asyncio.sleep(0)
        assert waiting.done() is False
        release_external_path_locks(first)
        second = await asyncio.wait_for(waiting, timeout=1)
        release_external_path_locks(second)

    asyncio.run(scenario())


def test_sra_external_locks_include_shared_app_data() -> None:
    class ScriptConfig:
        def get(self, section: str, key: str):
            assert key == "Path"
            return {"SRA": "C:/SRA-one", "M7A": "C:/M7A"}.get(section)

    shared_app_data = Path("C:/Users/test/AppData/Roaming/SRA")
    with patch(
        "automas_hsr_adapter_sra.runner.get_sra_app_data_dir",
        return_value=shared_app_data,
    ):
        paths = _resolve_external_lock_paths(ScriptConfig(), ("SRA", "M7A"))

    assert paths == ["C:/SRA-one", "C:/M7A", shared_app_data]


def test_legacy_hsr_routes_translate_plugin_contracts() -> None:
    from app.api.scripts import get_hsr_stage_options_api, router

    async def dispatch(_method: str, path: str, **_kwargs):
        assert path.endswith("stage-options")
        return {
            "code": 200,
            "status": "success",
            "message": "success",
            "data": {
                "engine": "M7A",
                "categories": [
                    {
                        "key": "calyx",
                        "label": "拟造花萼",
                        "options": [
                            {
                                "id": "calyx-golden",
                                "label": "回忆之蕾",
                                "detail": "角色经验",
                                "cost": 10,
                                "max_count": 6,
                                "native_payload": {
                                    "m7a": {
                                        "instanceType": "CalyxGolden",
                                        "instanceName": "回忆之蕾",
                                    }
                                },
                            }
                        ],
                    }
                ],
            },
        }

    async def scenario() -> None:
        with patch("app.api.scripts._dispatch_hsr_plugin_http", new=dispatch):
            stage = await get_hsr_stage_options_api("script", "M7A")

        assert stage.code == 200
        assert stage.data is not None
        assert stage.data.categories[0].options[0].m7a is not None
        assert stage.data.categories[0].options[0].m7a.instanceType == "CalyxGolden"

    legacy_paths = {"/api/scripts/hsr/stage-options"}
    legacy_routes = [route for route in router.routes if route.path in legacy_paths]
    assert {route.path for route in legacy_routes} == legacy_paths
    assert all(route.include_in_schema is False for route in legacy_routes)
    assert all(route.path != "/api/scripts/user/import-m7a-abyss-snapshot" for route in router.routes)
    asyncio.run(scenario())
