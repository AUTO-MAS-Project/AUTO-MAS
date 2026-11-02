"""三条接入契约：匹配、装配错误、事务、上下文与宿主实例隔离。"""

import asyncio
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.config import ConfigCollection
from app.core.config.manager import AppConfig
from app.core.task_manager.manager import Task, TaskInfo, _TaskManager
from app.models.config import GeneralConfig, GeneralUserConfig
from app.models.script_contracts import ScriptConfigHandler
from app.models.task import ScriptItem
from app.task.registration import ScriptRegistration, build_script_capabilities
from app.task.restore_registry import RestorePoolResolver
from app.utils.common.config.restore import ConfigRestorePool


class AdapterConfig(GeneralConfig):
    pass


class DerivedAdapterConfig(AdapterConfig):
    pass


def declaration(entry_type=AdapterConfig, **changes):
    return replace(
        ScriptRegistration(
            config_type=entry_type,
            run_types=(entry_type,),
            manager_factory=lambda item, context: (item, context),
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
    config.ScriptConfig = ConfigCollection.build(
        [AdapterConfig, DerivedAdapterConfig, GeneralConfig]
    )
    config.QueueConfig = {}
    for entry_type, handler in capabilities.config_handlers:
        config.bind_script_config_handler(entry_type, handler)
    config.set_restore_pool_resolver(capabilities.resolve_restore_pools)
    return config


def task(factories):
    return Task(
        TaskInfo("AutoProxy", "test", None, None, None), [], manager_factories=factories
    )


def build(
    task, config, *, root_paths=(), emulator_key=None, owner="owner", script_uid=None
):
    return task._build_task_item(
        ScriptItem(script_id="adapter", name="adapter", status="等待"),
        config,
        script_uid=script_uid or uuid4(),
        reservation_owner=owner,
        root_paths=root_paths,
        emulator_key=emulator_key,
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
        assert build(task(caps.manager_factories), derived)[0].script_id == "adapter"
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


def test_reservations_keep_task_owner_roots_and_emulator(tmp_path):
    caps = build_script_capabilities([declaration()], expected_types=[AdapterConfig])
    runner = task(caps.manager_factories)
    root = tmp_path / "initial"
    extra = tmp_path / "extra"
    sid = uuid4()
    other = uuid4()
    assert runner.script_reservations.try_acquire(
        sid, "owner", root_paths=(root,), emulator_key="emulator"
    )
    item, context = build(
        runner,
        AdapterConfig(),
        root_paths=(root,),
        emulator_key="emulator",
        script_uid=sid,
    )
    assert context.root_paths == (root,)
    assert context.reserve_root(extra)
    assert not runner.script_reservations.try_acquire(
        other, "other", root_paths=(extra,)
    )
    assert not runner.script_reservations.try_acquire(
        other, "other", emulator_key="emulator"
    )
    assert not runner.script_reservations.release(sid, "other")
    assert runner.script_reservations.release(sid, "owner")
    assert runner.script_reservations.try_acquire(
        other, "other", root_paths=(root, extra), emulator_key="emulator"
    )


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
                    manager_factory=lambda item, context: label,
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
@pytest.mark.parametrize("mode", ["AutoProxy", "CycleRun"])
async def test_public_task_creation_passes_current_host_factories(mode, monkeypatch):
    from unittest.mock import AsyncMock, Mock

    import app.core.task_manager.manager as scheduler
    from app.models.config import QueueItem
    from app.models.schema import WSTaskScriptIdentityData

    caps = build_script_capabilities([declaration()], expected_types=[AdapterConfig])
    manager = _TaskManager()
    manager.bind_manager_factories(caps.manager_factories)
    script_uid, queue_uid, item_uid = uuid4(), uuid4(), uuid4()
    item = QueueItem()
    item.Info.ScriptId = script_uid
    queue = SimpleNamespace(
        Info=SimpleNamespace(CycleEnabled=True), QueueItem={item_uid: item}
    )
    config = SimpleNamespace(
        ScriptConfig={script_uid: AdapterConfig()},
        QueueConfig={queue_uid: queue},
        running_cycle_queue_ids=set(),
        get_script_task_resources=lambda script: SimpleNamespace(
            root_paths=(), emulator=None
        ),
    )
    monkeypatch.setattr(scheduler, "Config", config)
    monkeypatch.setattr(
        manager,
        "_script_identity",
        lambda uid: WSTaskScriptIdentityData(scriptId=str(uid), scriptType="test"),
    )
    monkeypatch.setattr(
        manager, "_queue_script_entries", lambda uid: [(script_uid, [])]
    )
    monkeypatch.setattr(Task, "execute", Mock())
    monkeypatch.setattr(manager, "_schedule_clean_task", Mock())
    monkeypatch.setattr(scheduler.Publisher, "send", AsyncMock())
    uid = await manager.add_task(mode, str(queue_uid))
    runner = manager.task_handler[uid]
    assert runner.task_info.is_cycle is (mode == "CycleRun")
    assert build(runner, config.ScriptConfig[script_uid])[0].script_id == "adapter"
    assert runner._manager_factories is caps.manager_factories


@pytest.mark.asyncio
async def test_unbound_task_manager_fails_before_mutating_task_state():
    manager = _TaskManager()
    with pytest.raises(RuntimeError):
        await manager.add_task("AutoProxy", str(uuid4()))
    assert manager.task_info == {} and manager.task_handler == {}
