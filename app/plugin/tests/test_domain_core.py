"""领域核心与适配器单测。"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.config import ConfigCollection
from app.config.shortcuts import collection
from app.core.plugin_adapters import ScriptAdapterRuntime
from app.core.plugin_manager import Plugin
from app.models.config import (
    GameEntry,
    PlanEntry,
    ScriptEntry,
    UserEntry,
)
from app.models.task import TaskItem, TaskMode
from app.plugin.base.script import ScriptAdapterPlugin, ScriptTypeDecl
from app.plugin.types import LifecycleContext
from app.task import ScriptExpander, UserExpander
from app.task import script_expander as script_expander_mod


def _expander(
    *,
    mode: str,
    queue_id: str | None,
    script_id: str | None,
    user_id: str | None,
) -> ScriptExpander:
    """造一个只带 info 的脚本展开层实例：真值表只读 ``item.info``。"""
    item = TaskItem.build(
        uid=uuid4(),
        payload={
            "info": {
                "mode": mode,
                "queue_id": queue_id,
                "script_id": script_id,
                "user_id": user_id,
            }
        },
    )
    asyncio.run(item.activate())
    return ScriptExpander(item)


def test_expand_scripts_truth_table(monkeypatch: pytest.MonkeyPatch) -> None:
    # 队列取数读 Config.queues，真值表本身不关心它怎么来，故在此桩掉
    def fake_queue_script_ids(queue_id: str | None) -> list[str]:
        return ["s1", "s2", "s3"] if queue_id else []

    monkeypatch.setattr(
        script_expander_mod, "queue_script_ids", fake_queue_script_ids
    )

    assert _expander(
        mode="ScriptConfig", queue_id="q", script_id="s1", user_id=None
    ).expand_scripts() == ["s1"]
    # 队列内断点续跑：自 s2 起向后取
    assert _expander(
        mode="AutoProxy", queue_id="q", script_id="s2", user_id=None
    ).expand_scripts() == ["s2", "s3"]


class _StubEntry:
    """只提供 uid 的脚本 Entry 替身：``expand_users`` 只读这一项。"""

    def __init__(self, uid: str) -> None:
        self.uid = uid


class _ProbeExpander(UserExpander):
    """绕开 parent 链直接给 ``task_item``：真值表只读 info 与 script_entry.uid。"""

    def __init__(self, task: TaskItem, current_script_id: str) -> None:
        super().__init__()
        self._probe_item = task
        self.script_entry = _StubEntry(current_script_id)  # type: ignore[assignment]

    @property
    def task_item(self) -> TaskItem:
        return self._probe_item


def _user_expander(
    *,
    mode: str,
    queue_id: str | None,
    script_id: str | None,
    user_id: str | None,
    current_script_id: str,
) -> _ProbeExpander:
    item = TaskItem.build(
        uid=uuid4(),
        payload={
            "info": {
                "mode": mode,
                "queue_id": queue_id,
                "script_id": script_id,
                "user_id": user_id,
            }
        },
    )
    asyncio.run(item.activate())
    return _ProbeExpander(item, current_script_id)


def test_expand_users_truth_table() -> None:
    users = ["u1", "u2", "u3"]
    assert (
        _user_expander(
            mode="ScriptConfig",
            queue_id=None,
            script_id="s",
            user_id=None,
            current_script_id="s",
        ).expand_users(mode=TaskMode.SCRIPT_CONFIG, enabled_user_ids=users)
        == ["Default"]
    )
    # 队列 + 脚本 + 用户且正好跑到该脚本 → 自 u2 起续跑
    assert _user_expander(
        mode="AutoProxy",
        queue_id="q",
        script_id="s1",
        user_id="u2",
        current_script_id="s1",
    ).expand_users(mode=TaskMode.AUTO_PROXY, enabled_user_ids=users) == ["u2", "u3"]
    # 跑到别的脚本 → 该脚本跑全量用户
    assert (
        _user_expander(
            mode="AutoProxy",
            queue_id="q",
            script_id="s1",
            user_id="u2",
            current_script_id="s2",
        ).expand_users(mode=TaskMode.AUTO_PROXY, enabled_user_ids=users)
        == users
    )


def test_domain_collections_crud() -> None:
    async def run() -> None:
        scripts = ConfigCollection[ScriptEntry].build([ScriptEntry])
        await scripts.activate()
        uid = scripts.add(ScriptEntry, payload={"info": {"name": "demo"}})
        await scripts.commit()
        assert scripts[uid].info.name == "demo"
        users = scripts[uid].users
        u = users.add(UserEntry, payload={"info": {"name": "u1"}})
        await users.commit()
        assert users[u].info.name == "u1"
        tags = users[u].info.tags
        assert any(t.text.startswith("代理") for t in tags)

        plans = ConfigCollection[PlanEntry].build([PlanEntry])
        await plans.activate()
        pid = plans.add(PlanEntry, payload={"info": {"name": "p1"}})
        await plans.commit()
        assert plans[pid].info.name == "p1"

        games = ConfigCollection[GameEntry].build([GameEntry])
        await games.activate()
        gid = games.add(GameEntry, payload={"info": {"name": "g1"}})
        await games.commit()
        assert games[gid].info.name == "g1"

        tasks = ConfigCollection[TaskItem].build([TaskItem])
        await tasks.activate()
        tid = tasks.add(
            TaskItem,
            payload={"info": {"mode": "AutoProxy", "script_id": str(uid)}},
        )
        await tasks.commit()
        assert tasks[tid].info.mode == "AutoProxy"

    asyncio.run(run())


def test_script_adapter_requires_narrowed_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """users 未收窄到 user_type 须在构造时上抛；禁用后用户配置随级联消失。

    user_type 不是 Config 可直达的类型，而是 ``entry_type.users`` 这个嵌套集合的
    类型域，故没有全局类型表可登记，只能要求子类在类体上 ``collection(user_type)``。
    校验一次到位后，插件禁用只需 ``remove_type``：脚本实例被级联软删，``users``
    与其成员随之而去，无需订阅 remove 再手工清用户。
    """

    async def run() -> None:
        import app.core.config as core_config

        scripts = ConfigCollection[ScriptEntry].build([ScriptEntry])
        plans = ConfigCollection[PlanEntry].build([PlanEntry])
        await scripts.activate()
        await plans.activate()
        monkeypatch.setattr(core_config.Config, "ScriptConfig", scripts)
        monkeypatch.setattr(core_config.Config, "PlanConfig", plans)

        class DemoUser(UserEntry):
            pass

        class DemoManager(UserExpander):
            pass

        class Narrowed(ScriptEntry):
            users: ConfigCollection[DemoUser] = collection(DemoUser)

        class Bare(ScriptEntry):
            pass  # users 仍是宿主骨架的 collection(UserEntry)

        def _plugin(entry_type: type[ScriptEntry]) -> type[ScriptAdapterPlugin]:
            class Demo(ScriptAdapterPlugin):
                script_type_key = "narrow-demo"
                decl = ScriptTypeDecl(
                    entry_type=entry_type,
                    user_type=DemoUser,
                    expander_class=DemoManager,
                )

            return Demo

        class Rec:
            uid = uuid4()

            class info:
                plugin_name = "demo"
                lifecycle_context = LifecycleContext.NORMAL

        with pytest.raises(ValueError, match="collection"):
            _plugin(Bare)(record=Rec())  # type: ignore[arg-type]

        record = Rec()
        plugin = _plugin(Narrowed)(record=record)  # type: ignore[arg-type]
        plugin.bind_runtime(ScriptAdapterRuntime(plugin))
        await plugin.system_enable()

        uid = scripts.add(Narrowed, payload={"info": {"name": "s"}})
        await scripts.commit()
        entry = scripts[uid]
        assert list(entry.users.effective._entry_types) == ["DemoUser"]

        u1 = entry.users.add(DemoUser)
        u2 = entry.users.add(DemoUser)
        await entry.users.commit()
        users = [entry.users.effective.data[u1], entry.users.effective.data[u2]]

        await plugin.system_disable()
        assert uid not in scripts
        assert entry.users.deleted
        assert all(u.deleted for u in users)
        assert "Narrowed" not in scripts.effective._entry_types

    asyncio.run(run())


def test_script_adapter_system_enable_disable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        import app.core.config as core_config

        scripts = ConfigCollection[ScriptEntry].build([ScriptEntry])
        plans = ConfigCollection[PlanEntry].build([PlanEntry])
        await scripts.activate()
        await plans.activate()
        monkeypatch.setattr(core_config.Config, "ScriptConfig", scripts)
        monkeypatch.setattr(core_config.Config, "PlanConfig", plans)

        class DemoUser(UserEntry):
            pass

        class DemoScript(ScriptEntry):
            # users 的类型域由类体收窄，适配器校验这一点（不走全局类型表）
            users: ConfigCollection[DemoUser] = collection(DemoUser)

        class DemoManager(UserExpander):
            pass

        class Demo(ScriptAdapterPlugin):
            script_type_key = "Demo"
            decl = ScriptTypeDecl(
                entry_type=DemoScript,
                user_type=DemoUser,
                expander_class=DemoManager,
            )

        class Rec:
            uid = uuid4()

            class info:
                plugin_name = "demo"
                lifecycle_context = LifecycleContext.NORMAL

        # record 只弱引用；本地强引用须活到 system_disable 之后
        record = Rec()
        plugin = Demo(record=record)  # type: ignore[arg-type]
        plugin.bind_runtime(ScriptAdapterRuntime(plugin))
        await plugin.system_enable()
        assert Plugin.script_types[record.uid] is Demo.decl

        uid = scripts.add(DemoScript, payload={"info": {"name": "s"}})
        await scripts.commit()
        assert uid in scripts

        await plugin.system_disable()
        assert record.uid not in Plugin.script_types

    asyncio.run(run())
