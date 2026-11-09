"""三条接入契约：匹配、装配错误、事务、上下文与宿主实例隔离。"""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from app.config import ConfigCollection
from app.core.config.manager import AppConfig
from app.core.task_manager import _TaskManager
from app.models.config import GeneralConfig, GeneralUserConfig, ScriptConfigType
from app.models.script_contracts import ScriptConfigHandler
from app.models.task import ScriptItem, TaskItem, TaskTriggerReason
from app.task.registration import ScriptRegistration, build_script_capabilities
from app.task.restore_registry import RestorePoolResolver
from app.task.script_expander import ScriptExpander
from app.utils.common.config.restore import ConfigRestorePool
from tests.core.test_task_tree_dispatch import Builtin
from tests.core.test_task_tree_dispatch import scheduler as scheduler


class AdapterConfig(GeneralConfig):
    pass


class DerivedAdapterConfig(AdapterConfig):
    pass


def declaration(entry_type=AdapterConfig, **changes):
    return replace(
        ScriptRegistration(
            config_type=entry_type,
            run_types=(entry_type,),
            manager_factory=lambda item: item,
            create_config_handler=lambda: ScriptConfigHandler(
                user_config_class=GeneralUserConfig
            ),
            load_restore_pools=lambda: [ConfigRestorePool(key="test", kind="user")],
            config_priority=0,
            restore_priority=0,
        ),
        **changes,
    )


def host(capabilities):
    # 仅构建配置消费边界，集合不登记全局名称，不创建真实设备和持久化根。
    config = AppConfig.__new__(AppConfig)
    config.work_path = Path.cwd()
    config.data_path = config.work_path / "data"
    config.config_path = config.work_path / "config"
    config._script_config_handlers = {}
    config._restore_pool_resolver = None
    config.ScriptConfig = ConfigCollection[ScriptConfigType].build(
        [AdapterConfig, DerivedAdapterConfig, GeneralConfig]
    )
    config.QueueConfig = {}
    for entry_type, handler in capabilities.config_handlers:
        config.bind_script_config_handler(entry_type, handler)
    config.set_restore_pool_resolver(capabilities.resolve_restore_pools)
    return config


def task(factories):
    dispatcher = _TaskManager()
    dispatcher.bind_manager_factories(factories)
    return ScriptExpander(TaskItem(), dispatcher)


def build(task, config):
    factory = task.dispatcher.manager_factories.get(type(config))
    return (
        factory(ScriptItem(script_id="adapter", name="adapter", status="等待"))
        if factory is not None
        else None
    )


def test_independent_matching_orders_and_exact_runtime():
    parent_pool = [ConfigRestorePool(key="parent", kind="user")]
    child_pool = [ConfigRestorePool(key="child", kind="user")]
    parent = declaration(
        config_priority=0, restore_priority=1, load_restore_pools=lambda: parent_pool
    )
    child = declaration(
        DerivedAdapterConfig,
        config_priority=1,
        restore_priority=0,
        load_restore_pools=lambda: child_pool,
    )
    for entries in [(parent, child), (child, parent)]:
        caps = build_script_capabilities(
            entries, expected_types=[AdapterConfig, DerivedAdapterConfig]
        )
        config = host(caps)
        derived = DerivedAdapterConfig()
        assert (
            config._get_script_config_handler(derived)
            is dict(caps.config_handlers)[AdapterConfig]
        )
        assert caps.resolve_restore_pools(derived) is child_pool
        assert build(task(caps.manager_factories), derived).script_id == "adapter"
    caps = build_script_capabilities([parent], expected_types=[AdapterConfig])
    assert build(task(caps.manager_factories), DerivedAdapterConfig()) is None
    assert caps.resolve_restore_pools(DerivedAdapterConfig()) is parent_pool
    with pytest.raises(ValueError):
        caps.resolve_restore_pools(GeneralConfig())
    with pytest.raises(RuntimeError):
        host(caps)._get_script_config_handler(GeneralConfig())


def test_duplicate_and_missing_declarations_fail_before_building_handlers():
    calls = []
    entry = declaration(create_config_handler=lambda: calls.append("built"))
    with pytest.raises(ValueError):
        build_script_capabilities([entry, entry], expected_types=[AdapterConfig])
    with pytest.raises(ValueError):
        build_script_capabilities(
            [entry, declaration(DerivedAdapterConfig, run_types=(AdapterConfig,))],
            expected_types=[AdapterConfig],
        )
    with pytest.raises(ValueError):
        build_script_capabilities([entry], expected_types=[DerivedAdapterConfig])
    with pytest.raises(ValueError):
        build_script_capabilities([entry], expected_types=[GeneralConfig])
    assert calls == []
    with pytest.raises(ValueError):
        RestorePoolResolver(((AdapterConfig, None), (AdapterConfig, None)))


def test_explicit_unsupported_is_distinct_from_missing():
    caps = build_script_capabilities(
        [
            declaration(
                manager_factory=None,
                create_config_handler=None,
                load_restore_pools=None,
            )
        ],
        expected_types=[AdapterConfig],
    )
    config = host(caps)
    assert config._get_script_config_handler(AdapterConfig()) is None
    assert build(task(caps.manager_factories), AdapterConfig()) is None
    with pytest.raises(ValueError):
        caps.resolve_restore_pools(AdapterConfig())
    with pytest.raises(ValueError):
        config.bind_script_config_handler(AdapterConfig, ScriptConfigHandler())
    manager = _TaskManager()
    manager.bind_manager_factories(caps.manager_factories)
    with pytest.raises(RuntimeError):
        manager.bind_manager_factories(caps.manager_factories)
    with pytest.raises(TypeError):
        caps.manager_factories[GeneralConfig] = None


@pytest.mark.asyncio
async def test_test_adapter_three_lines_and_two_hosts_share_no_dependencies(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    current = asyncio.current_task()
    events = []

    def capabilities(label):
        async def prepare(script, user, *, data):
            assert asyncio.current_task() is current
            events.append((label, "save"))

        async def remove(script):
            assert asyncio.current_task() is current
            events.append((label, "prepare"))

        async def cleanup(sid):
            events.append((label, "cleanup"))

        async def restore(ctx, ts):
            assert asyncio.current_task() is current
            ctx.script_config.Info.Name = label + ts
            await ctx.script_config.commit()
            events.append((ctx.config, label, "restore", ctx.force))

        return build_script_capabilities(
            [
                declaration(
                    manager_factory=lambda item: label,
                    create_config_handler=lambda: ScriptConfigHandler(
                        user_config_class=GeneralUserConfig,
                        prepare_user_update=prepare,
                        prepare_script_removal=remove,
                        cleanup_script_files=cleanup,
                    ),
                    load_restore_pools=lambda: [
                        ConfigRestorePool(key="test", kind="user", restore=restore)
                    ],
                )
            ],
            expected_types=[AdapterConfig],
        )

    configs = []
    for label in ("first", "second"):
        caps = capabilities(label)
        config = host(caps)
        await config.ScriptConfig.activate()
        sid = config.ScriptConfig.add(AdapterConfig)
        await config.ScriptConfig.commit()
        uid, _ = await config.add_user(str(sid))
        configs.append((label, caps, config, sid, uid))
    for label, caps, config, sid, uid in reversed(configs):
        assert build(task(caps.manager_factories), config.ScriptConfig[sid]) == label
        await config.update_user(str(sid), str(uid), {"Info": {"Name": label}})
        await config.restore_service(str(sid), str(uid), force=True).restore(
            "test", "-restored"
        )
        assert config.ScriptConfig[sid].Info.Name == label + "-restored"
        assert (config, label, "restore", True) in events
        await config.del_script(str(sid))
        assert events[-2:] == [(label, "prepare"), (label, "cleanup")]
    assert configs[0][2]._get_script_config_handler(AdapterConfig()) is not configs[1][
        2
    ]._get_script_config_handler(AdapterConfig())


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError, asyncio.CancelledError])
async def test_associated_hook_commits_and_failure_stay_in_same_transaction(error):
    other = GeneralConfig()
    await other.activate()
    before = other.Info.Name
    owner = asyncio.current_task()

    async def initialize(script):
        assert asyncio.current_task() is owner
        other.Info.Name = "changed"
        await other.commit()
        raise error()

    caps = build_script_capabilities(
        [
            declaration(
                GeneralConfig,
                create_config_handler=lambda: ScriptConfigHandler(
                    initialize=initialize
                ),
            )
        ],
        expected_types=[GeneralConfig],
    )
    config = host(caps)
    await config.ScriptConfig.activate()
    with pytest.raises(error):
        await config.add_script("General")
    assert not config.ScriptConfig
    assert other.Info.Name == before


@pytest.mark.asyncio
@pytest.mark.parametrize("source", [TaskTriggerReason.MANUAL, TaskTriggerReason.TIMED])
async def test_public_task_creation_passes_current_host_factories(scheduler, source):
    _, _, _, sid = scheduler
    constructed = []

    def build_builtin(item):
        constructed.append(item)
        return Builtin(item)

    caps = build_script_capabilities(
        [declaration(GeneralConfig, manager_factory=build_builtin)],
        expected_types=[GeneralConfig],
    )
    manager = _TaskManager()
    manager.bind_manager_factories(caps.manager_factories)
    uid = await manager.start(
        "AutoProxy",
        {
            0: {
                "uid": "-",
                "children": {0: {"uid": str(sid)}},
            }
        },
        trigger=source,
    )
    runner = manager.task_handler[uid]
    await asyncio.wait_for(runner.accomplish.wait(), 3)
    assert runner.task_info.status == "success"
    assert constructed[0] is runner.task_info.script_list[0]
    assert runner.dispatcher.manager_factories == caps.manager_factories


@pytest.mark.asyncio
async def test_unbound_task_manager_fails_before_mutating_task_state():
    manager = _TaskManager()
    with pytest.raises(RuntimeError):
        await manager.start("AutoProxy", {})
    assert manager.task_info == {} and manager.task_handler == {}
