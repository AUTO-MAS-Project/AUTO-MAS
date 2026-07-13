from __future__ import annotations

import asyncio
import base64
import json
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
from automas_hsr_adapter_sra.runner import run_sra_single_task
from automas_script_hsr.adapter import HSRAdapterHooks
from automas_script_hsr.contracts import HSRRunResult
from automas_script_hsr.migration import migrate_legacy_hsr_config
from automas_script_hsr.plugin import Plugin as HSRPlugin
from automas_script_hsr.registry import HSRRegistryService
from automas_script_hsr.runtime.autoproxy import HSRAutoProxyTask
from automas_script_hsr.runtime.locks import (
    acquire_external_path_locks,
    release_external_path_locks,
)
from automas_script_hsr.runtime.manager import HSRManager
from automas_script_hsr.runtime.models import (
    HSRRetryableTaskError,
    HSRRunItem,
    HSRRuntimeState,
)
from automas_script_hsr.runtime.tasks import (
    HSR_TASK_MODULE_MAP,
    get_assigned_script,
    module_is_available,
)
from automas_script_hsr.runtime.notify import (
    load_user_custom_webhooks,
    render_hsr_mail_template,
)
from automas_script_hsr.schema import HSRConfig, HSRUserConfig
from app.core import Config
from app.core.script_types import script_type_registry
from app.models.config import HSRConfig as LegacyHSRConfig
from app.models.config import HSRUserConfig as LegacyHSRUserConfig
from app.models.config import Webhook
from app.models.ConfigBase import MultipleConfig
from app.models.plugin_script_config import PluginScriptConfig
from app.plugins import ScriptAdapterDefinition
from app.plugins.server import PluginHttpRequest
from app.plugins.script_config_store import ScriptConfigStore
from app.plugins.manager import _DeclaredScriptTypeBinding, _PluginManager
from app.models.schema import ScriptCreateIn, ScriptCreateOut, UserCreateOut
from app.models.task import UserItem


def _provider(registry: HSRRegistryService):
    return ScriptAdapterDefinition(
        type_key="HSR",
        display_name="HSR脚本",
        hooks_factory=HSRAdapterHooks,
        script_model=HSRConfig,
        user_model=HSRUserConfig,
        supported_modes=("AutoProxy", "ManualReview"),
        record_capability_resolver=registry.resolve_record_capability,
        metadata={"legacy_config_migrator": migrate_legacy_hsr_config},
    ).build_provider(owner="test")


def test_registry_exposes_atomic_engine_matrix() -> None:
    registry = HSRRegistryService()
    assert registry.snapshot().effective_engines == ()

    registry.register_group(
        owner="sra",
        task_catalog=SRATaskCatalog(),
        controller=SRAController(),
    )
    sra_only = registry.snapshot(selected_engines=["SRA", "M7A"])
    assert sra_only.effective_engines == ("SRA",)
    assert sra_only.supported_modes == ("AutoProxy", "ManualReview")

    registry.register_group(
        owner="m7a",
        task_catalog=M7ATaskCatalog(),
        controller=M7AController(),
    )
    both = registry.snapshot(selected_engines=["M7A", "SRA"])
    assert both.effective_engines == ("SRA", "M7A")
    assert {task["key"] for task in both.tasks} == {
        "Daily",
        "ReceiveRewards",
        "DivergentUniverse",
        "CurrencyWars",
        "ForgottenHall",
    }

    assert registry.unregister_owner("sra") == ("SRA",)
    assert registry.snapshot(selected_engines=["SRA", "M7A"]).effective_engines == (
        "M7A",
    )


def test_host_openapi_no_longer_declares_legacy_hsr_config_models() -> None:
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


def test_snapshot_never_probes_or_exposes_an_unselected_engine() -> None:
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

    snapshot = registry.snapshot(
        selected_engines=["SRA"],
        script_config=object(),
    )

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


def test_legacy_hsr_migration_uses_plugin_container_and_preserves_users() -> None:
    asyncio.run(_assert_legacy_hsr_migration())


async def _assert_legacy_hsr_migration() -> None:
    legacy = LegacyHSRConfig()
    await legacy.set("Info", "Name", "旧 HSR")
    await legacy.set("Info", "SRAPath", r"D:\SRA")
    await legacy.set("Info", "M7APath", r"D:\M7A")
    user_id, user = await legacy.UserData.add(LegacyHSRUserConfig)
    await user.set("Info", "Name", "开拓者")
    await user.set("TaskSwitch", "CurrencyWars", True)

    registry = HSRRegistryService()
    provider = _provider(registry)
    migrated = await migrate_legacy_hsr_config(legacy, provider)

    assert isinstance(migrated, PluginScriptConfig)
    assert migrated.get("Meta", "PluginTypeKey") == "HSR"
    assert migrated.UserData.order == [user_id]

    store = ScriptConfigStore(provider=provider, storage_script_config=migrated)
    script_model = await store.load_script_model()
    user_model = await store.load_user_model(str(user_id))
    assert script_model.get("Engine", "EnabledEngines") == ["SRA", "M7A"]
    assert script_model.get("SRA", "Path").replace("/", "\\") == r"D:\SRA"
    assert script_model.get("M7A", "Path").replace("/", "\\") == r"D:\M7A"
    assert user_model.get("Info", "Name") == "开拓者"
    assert user_model.get("TaskSwitch", "CurrencyWars") is True


def test_legacy_hsr_migration_preserves_full_runtime_state_and_secrets() -> None:
    def encrypt(value: str) -> str:
        payload = base64.b64encode(value.encode("utf-8")).decode("ascii")
        return f"encrypted:{payload}"

    def decrypt(value: str) -> str:
        if value == "":
            return ""
        prefix = "encrypted:"
        if not isinstance(value, str) or not value.startswith(prefix):
            raise ValueError("invalid encrypted payload")
        return base64.b64decode(value[len(prefix):]).decode("utf-8")

    with (
        patch("app.models.ConfigBase.dpapi_encrypt", encrypt),
        patch("app.models.ConfigBase.dpapi_decrypt", decrypt),
    ):
        asyncio.run(_assert_full_legacy_hsr_migration())


def test_plugin_manager_migrates_legacy_hsr_in_place_with_same_uuid() -> None:
    async def scenario() -> None:
        scripts = MultipleConfig([LegacyHSRConfig, PluginScriptConfig])
        temp_dir = tempfile.TemporaryDirectory(dir=Path.cwd())
        await scripts.connect(Path(temp_dir.name) / "ScriptConfig.json")
        script_id, legacy = await scripts.add(LegacyHSRConfig)
        await legacy.set("Info", "Name", "manager migration")
        await legacy.set("Info", "SRAPath", r"D:\SRA")

        owner = "hsr-migration-test"
        provider = _provider(HSRRegistryService())
        manager = _PluginManager.__new__(_PluginManager)
        manager.loader = SimpleNamespace(
            records={
                owner: SimpleNamespace(
                    status="active",
                    plugin_name="automas_script_hsr",
                    instance_id=owner,
                )
            }
        )
        manager._resolve_declared_script_type_bindings = lambda *_args, **_kwargs: [
            _DeclaredScriptTypeBinding(
                type_key="HSR",
                display_name="HSR",
                legacy_config_class=LegacyHSRConfig,
            )
        ]

        original_scripts = Config.ScriptConfig
        script_type_registry.register(provider, owner=owner)
        try:
            Config.ScriptConfig = scripts
            await manager._sync_script_types_and_migrate_legacy_configs()
            assert list(scripts.keys()) == [script_id]
            assert isinstance(scripts[script_id], PluginScriptConfig)
            assert scripts[script_id].get("Meta", "PluginTypeKey") == "HSR"
            store = ScriptConfigStore(
                provider=provider,
                storage_script_config=scripts[script_id],
            )
            model = await store.load_script_model()
            assert model.get("SRA", "Path").replace("/", "\\") == r"D:\SRA"
        finally:
            Config.ScriptConfig = original_scripts
            script_type_registry.unregister_by_owner(owner)
            temp_dir.cleanup()

    asyncio.run(scenario())


async def _assert_full_legacy_hsr_migration() -> None:
    legacy = LegacyHSRConfig()
    await legacy.set("Info", "Name", "完整迁移")
    await legacy.set("Info", "SRAPath", r"D:\SRA")
    await legacy.set("Info", "M7APath", r"D:\M7A")
    await legacy.set("Game", "Path", r"D:\Game\StarRail.exe")
    await legacy.set("Game", "Arguments", "-screen-fullscreen 0")
    await legacy.set("Game", "WaitTime", 75)
    await legacy.set("Run", "RunTimesLimit", 5)
    await legacy.set("Run", "DailyTimeLimit", 25)
    await legacy.set("Run", "WeeklyTimeLimit", 65)
    await legacy.set("Run", "MonthlyTimeLimit", 90)
    await legacy.set("Run", "LowPerformanceMode", True)
    await legacy.set("TaskMapping", "Daily", "M7A")
    await legacy.set("TaskMapping", "CurrencyWars", "SRA")

    first_id, first = await legacy.UserData.add(LegacyHSRUserConfig)
    second_id, second = await legacy.UserData.add(LegacyHSRUserConfig)
    await first.set("Info", "Name", "第一账号")
    await first.set("Info", "Status", False)
    await first.set("Info", "Id", "account@example.com")
    await first.set("Info", "Password", "password-value")
    await first.set("Info", "RemainedDay", 7)
    await first.set("Info", "Notes", "迁移备注")
    await first.set("Data", "LastProxyDate", "2026-07-12")
    await first.set("Data", "ProxyTimes", 2)
    await first.set("Data", "IfPassCheck", False)
    await first.set("Data", "EchoOfWarCompletedThisWeek", True)
    await first.set("Data", "EchoOfWarLastResetWeek", "2026-W28")
    await first.set("Data", "EchoOfWarLastCompletionDate", "2026-07-12")
    await first.set("Data", "WeeklyCompletedThisWeek", True)
    await first.set("Data", "WeeklyLastResetWeek", "2026-W28")
    await first.set("Data", "WeeklyLastCompletionDate", "2026-07-12")
    await first.set("Data", "AbyssCompletedThisMonth", True)
    await first.set("Data", "AbyssLastResetMonth", "2026-07")
    await first.set("Data", "AbyssLastCompletionDate", "2026-07-12")
    await first.set("TaskSwitch", "Daily", False)
    await first.set("TaskSwitch", "CurrencyWars", True)
    await first.set("TaskSwitch", "ForgottenHall", True)
    await first.set("Stage", "Channel", "Ornament")
    await first.set(
        "Stage",
        "ScriptStage",
        '{"SRA":{"id":"A"},"M7A":{"name":"B"}}',
    )
    await first.set(
        "Stage",
        "ScriptEchoOfWar",
        '{"SRA":{"id":"E"},"M7A":{"name":"F"}}',
    )
    await first.set("TaskOpt", "EchoOfWarWeekday", "Friday")
    await first.set(
        "Abyss",
        "Snapshots",
        '{"forgottenhall":{"team":"snapshot"}}',
    )
    await first.set("Notify", "Enabled", True)
    await first.set("Notify", "IfSendStatistic", True)
    await first.set("Notify", "IfSendMail", True)
    await first.set("Notify", "ToAddress", "notify@example.com")
    await first.set("Notify", "IfServerChan", True)
    await first.set("Notify", "ServerChanKey", "server-key")
    webhook_id, webhook = await first.Notify_CustomWebhooks.add(Webhook)
    await webhook.set("Info", "Name", "迁移 Webhook")
    await webhook.set("Info", "Enabled", True)
    await webhook.set("Data", "Url", "https://example.com/webhook")
    await webhook.set("Data", "Template", "{{ content }}")
    await webhook.set("Data", "Headers", '{"X-Test":"yes"}')
    await webhook.set("Data", "Method", "POST")
    await second.set("Info", "Name", "第二账号")

    id_cipher = first._config_item_index["Info"]["Id"].getValue(False)
    password_cipher = first._config_item_index["Info"]["Password"].getValue(False)

    registry = HSRRegistryService()
    provider = _provider(registry)
    migrated = await migrate_legacy_hsr_config(legacy, provider)
    assert migrated.UserData.order == [first_id, second_id]

    store = ScriptConfigStore(provider=provider, storage_script_config=migrated)
    script_model = await store.load_script_model()
    assert script_model.get("Engine", "EnabledEngines") == ["SRA", "M7A"]
    assert script_model.get("Game", "WaitTime") == 75
    assert script_model.get("Run", "RunTimesLimit") == 5
    assert script_model.get("M7A", "LowPerformanceMode") is True
    assert script_model.get("TaskMapping", "Daily") == "M7A"

    first_model = await store.load_user_model(first_id)
    assert first_model.get("Info", "Status") is False
    assert first_model.get("SRA", "Id") == "account@example.com"
    assert first_model.get("SRA", "Password") == "password-value"
    assert first_model.get("Data", "WeeklyCompletedThisWeek") is True
    assert first_model.get("TaskSwitch", "ForgottenHall") is True
    assert first_model.get("Stage", "Channel") == "Ornament"
    assert first_model.get("TaskOpt", "EchoOfWarWeekday") == "Friday"

    plugin_user = migrated.UserData[first_id]
    raw_plugin_user = json.loads(plugin_user.get("PluginData", "Config"))
    assert raw_plugin_user["SRA"]["Id"] == id_cipher
    assert raw_plugin_user["SRA"]["Password"] == password_cipher
    assert "password-value" not in plugin_user.get("PluginData", "Config")

    webhooks = await load_user_custom_webhooks(first_model)
    assert len(webhooks) == 1
    assert webhooks[0].get("Info", "Name") == "迁移 Webhook"
    assert webhooks[0].get("Data", "Url") == "https://example.com/webhook"
    raw_custom_webhooks = json.loads(first_model.get("Notify", "CustomWebhooks"))
    assert raw_custom_webhooks["instances"][0]["uid"] == str(webhook_id)


def test_script_selection_intersects_active_adapters() -> None:
    registry = HSRRegistryService()
    registry.register_group(
        owner="sra",
        task_catalog=SRATaskCatalog(),
        controller=SRAController(),
    )
    capability = registry.resolve_record_capability(
        {"Engine": {"EnabledEngines": ["M7A"]}}
    )
    assert capability.available is False
    assert capability.supported_modes == ()

    selected_sra = registry.resolve_record_capability(
        {"Engine": {"EnabledEngines": ["SRA"]}}
    )
    assert selected_sra.available is True
    assert selected_sra.supported_modes == ("AutoProxy", "ManualReview")


def test_hsr_config_rejects_an_explicit_empty_engine_selection() -> None:
    with pytest.raises(ValueError, match="至少选择一个引擎"):
        HSRConfig.model_validate({"Engine": {"EnabledEngines": []}})


def test_new_hsr_script_defaults_to_all_currently_available_engines() -> None:
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
    initial_factory = definition.metadata["initial_config_factory"]
    assert initial_factory() == {
        "Engine": {"EnabledEngines": ["SRA", "M7A"]}
    }


def test_task_assignment_uses_only_effective_engines_and_preserves_mapping() -> None:
    class Config:
        def __init__(self, engines: list[str], mapping: str = "SRA") -> None:
            self.engines = engines
            self.mapping = mapping

        def get(self, group: str, key: str):
            if group == "Engine" and key == "EnabledEngines":
                return self.engines
            if group == "TaskMapping":
                return self.mapping
            return None

    daily = HSR_TASK_MODULE_MAP["Daily"]
    abyss = HSR_TASK_MODULE_MAP["ForgottenHall"]

    assert get_assigned_script(daily, Config(["SRA"], "M7A")) == "SRA"
    assert get_assigned_script(daily, Config(["M7A"], "SRA")) == "M7A"
    assert get_assigned_script(daily, Config(["SRA", "M7A"], "M7A")) == "M7A"
    assert module_is_available(abyss, Config(["SRA"])) is False
    assert module_is_available(abyss, Config(["M7A"])) is True


def test_disabling_an_engine_preserves_its_namespaced_configuration() -> None:
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
                "Engine": {"EnabledEngines": ["SRA", "M7A"]},
                "SRA": {"Path": r"D:\SRA"},
                "M7A": {
                    "Path": r"D:\M7A",
                    "LowPerformanceMode": True,
                },
                "TaskMapping": {"Daily": "M7A"},
            }
        )

        await store.update_script_data(
            {"Engine": {"EnabledEngines": ["SRA"]}}
        )
        data = await store.read_script_data()

        assert data["Engine"]["EnabledEngines"] == ["SRA"]
        assert data["M7A"]["Path"].replace("/", "\\") == r"D:\M7A"
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


def test_plugin_api_rejects_unselected_engine_with_envelope() -> None:
    async def scenario() -> None:
        class Config:
            def get(self, group: str, key: str):
                if group == "Engine" and key == "EnabledEngines":
                    return ["SRA"]
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

        import_response = await plugin._import_m7a_abyss_snapshot(
            PluginHttpRequest(
                method="POST",
                path="/hsr/v1/m7a/abyss-snapshot/import",
                query={},
                headers={},
                body=b"",
                json={"scriptId": "script", "userId": "user"},
                instance_id="hsr",
            )
        )
        assert import_response.status_code == 409
        assert import_response.body["code"] == 409
        assert import_response.body["status"] == "error"
        assert import_response.body["data"] is None

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
