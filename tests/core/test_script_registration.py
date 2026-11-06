"""三条接入契约：匹配、装配错误、事务、上下文与宿主实例隔离。"""

import asyncio
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from app.config import ConfigCollection
from app.core.config.manager import AppConfig
from app.core.task_manager.manager import Task, TaskInfo
from app.models.config import GeneralConfig, GeneralUserConfig
from app.models.script_contracts import ScriptConfigHandler
from app.models.task import ScriptItem
from app.task.registration import ScriptRegistration, build_script_capabilities
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


def test_okww_shared_installation_is_reserved_across_scripts(tmp_path, monkeypatch):
    from app.core.task_manager.manager import _ScriptTaskReservations
    from app.models.config import OkwwConfig
    from app.task.Okww.registration import build_config_handler

    work = tmp_path / "mas"
    work.mkdir()
    root = tmp_path / "okww"
    root.mkdir()
    monkeypatch.chdir(work)
    script = OkwwConfig.model_validate({"Info": {"RootPath": str(root)}})
    resources = build_config_handler().task_resources(script)
    reservations = _ScriptTaskReservations()
    first, second = uuid4(), uuid4()
    assert reservations.try_acquire(first, "first", root_paths=resources.root_paths)
    assert not reservations.try_acquire(
        second, "second", root_paths=resources.root_paths
    )
    assert reservations.release(first, "first")
    assert reservations.try_acquire(second, "second", root_paths=resources.root_paths)


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
