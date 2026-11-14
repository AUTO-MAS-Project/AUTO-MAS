"""专项接入声明匹配、装配错误与配置钩子事务。"""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from app.config import ConfigCollection
from app.core.config.manager import AppConfig
from app.core.task_manager import _TaskManager
from app.models.config import GeneralConfig, GeneralUserConfig, ScriptConfigType
from app.models.script_contracts import ScriptConfigHandler
from app.models.task import ScriptItem, TaskItem
from app.task.registration import ScriptRegistration, build_script_capabilities
from app.task.restore_registry import RestorePoolResolver
from app.task.script_expander import ScriptExpander
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
