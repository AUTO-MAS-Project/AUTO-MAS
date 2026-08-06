"""ConfigCollection add_type / remove_type / reload_type（§5.4）。

用法（仓库根目录）::

    python -m app.config.tests.test_collection_entry_types
"""

from __future__ import annotations

import asyncio
from typing import ClassVar
from uuid import UUID

from pydantic import Field

from app.config import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    CollectionChangeEvent,
)
from blinker import Signal


def _fail(message: str) -> None:
    raise AssertionError(message)


def _ok(message: str) -> None:
    print(f"OK: {message}")


def _reset_signal(cls: type) -> None:
    cls.signal = Signal()


class BoundEntry(ConfigEntry):
    """域上界。"""

    class Info(ConfigGroup):
        name: str = "bound"

    info: Info = Field(default_factory=Info)


class OtherEntry(ConfigEntry):
    """非 BoundEntry 子类，用于上界校验。"""

    class Info(ConfigGroup):
        name: str = "other"

    info: Info = Field(default_factory=Info)


class BoundCollection(ConfigCollection[BoundEntry]):
    _default_entry_types: ClassVar[tuple[type, ...]] = ()


async def test_add_type_then_add() -> None:
    class PluginItem(BoundEntry):
        class Info(ConfigGroup):
            name: str = "p"
            tag: str = "v1"

        info: Info = Field(default_factory=Info)

    col = BoundCollection()
    await col.activate()
    try:
        col.add(PluginItem)
        _fail("未 add_type 应拒绝 add")
    except ValueError:
        pass
    col.add_type(PluginItem)
    await col.commit()
    if PluginItem.__name__ not in col._entry_types:
        _fail("commit 后 live._entry_types 应含新类型")
    if col._entry_types[PluginItem.__name__] is not PluginItem:
        _fail("_entry_types 应指向新类")
    uid = col.add(PluginItem, wire={"info": {"name": "a", "tag": "t"}})
    await col.commit()
    if col[uid].info.name != "a":
        _fail("add_type 后 add 失败")
    _ok("add_type 后可 add，_COMMIT 写回类型表")


async def test_add_type_signal_can_add_new_type() -> None:
    """同事务内 add_type 写入 effective 后，信号回调应能 add 该类型。"""

    class PluginItem(BoundEntry):
        class Info(ConfigGroup):
            name: str = "p"

        info: Info = Field(default_factory=Info)

    col = BoundCollection()
    await col.activate()
    created: list[UUID] = []

    async def on_add_type(sender: object, event: CollectionChangeEvent) -> None:
        if event.kind != "add_type":
            return
        uid = col.add(PluginItem, wire={"info": {"name": "from-signal"}})
        await col.commit()
        created.append(uid)

    _reset_signal(type(col))
    type(col).connect(on_add_type, phase="runtime", kind="add_type")
    col.add_type(PluginItem)
    await col.commit()
    type(col).disconnect(on_add_type, phase="runtime", kind="add_type")
    if not created or created[0] not in col:
        _fail("add_type 信号内应能 add 新类型")
    if col[created[0]].info.name != "from-signal":
        _fail("信号内 add 的成员字段异常")
    _ok("add_type 信号内可 add 新类型（effective 类型表）")


async def test_same_batch_remove_type_then_add_rejected() -> None:
    """同批先 remove_type 再 add：commit 时类型表已无该类，add 须失败且整笔不留下成员。"""

    class PluginItem(BoundEntry):
        class Info(ConfigGroup):
            name: str = "p"

        info: Info = Field(default_factory=Info)

    col = BoundCollection()
    await col.activate()
    col.add_type(PluginItem)
    await col.commit()
    col.remove_type(PluginItem)
    uid = col.add(PluginItem, wire={"info": {"name": "ghost"}})
    try:
        await col.commit()
        _fail("同批 remove_type 后 add 应在 commit 失败")
    except Exception:
        pass
    # 各 op 独立事务：remove_type 已提交；随后 add 因类型表无该类失败
    if PluginItem.__name__ in col._entry_types:
        _fail("remove_type 提交后类型表应无该类")
    if uid in col:
        _fail("不应留下幽灵成员")
    _ok("同批 remove_type 后 add 在 commit 被拒")


async def test_add_type_rejects_non_bound() -> None:
    col = BoundCollection()
    await col.activate()
    try:
        col.add_type(OtherEntry)  # type: ignore[arg-type]
        _fail("非上界子类应 TypeError")
    except TypeError:
        pass
    _ok("add_type 拒绝非上界子类")


async def test_add_type_name_conflict() -> None:
    class PluginItem(BoundEntry):
        class Info(ConfigGroup):
            name: str = "p1"

        info: Info = Field(default_factory=Info)

    class PluginItemAlt(BoundEntry):
        class Info(ConfigGroup):
            name: str = "p2"

        info: Info = Field(default_factory=Info)

    PluginItemAlt.__name__ = "PluginItem"  # 强制同名异类
    col = BoundCollection()
    await col.activate()
    col.add_type(PluginItem)
    await col.commit()
    try:
        col.add_type(PluginItemAlt)  # type: ignore[arg-type]
        _fail("同名异类应 ValueError")
    except ValueError:
        pass
    col.add_type(PluginItem)  # 幂等
    if col._staged_ops:
        _fail("同对象幂等不应 stage")
    _ok("add_type 同名冲突与幂等")


async def test_remove_type_cascade() -> None:
    class PluginItem(BoundEntry):
        class Info(ConfigGroup):
            name: str = "p"

        info: Info = Field(default_factory=Info)

    class KeepItem(BoundEntry):
        class Info(ConfigGroup):
            name: str = "k"

        info: Info = Field(default_factory=Info)

    col = BoundCollection([KeepItem])
    await col.activate()
    col.add_type(PluginItem)
    await col.commit()
    u1 = col.add(PluginItem, wire={"info": {"name": "a"}})
    u2 = col.add(PluginItem, wire={"info": {"name": "b"}})
    uk = col.add(KeepItem, wire={"info": {"name": "keep"}})
    await col.commit()
    removes: list[UUID] = []

    async def on_remove(sender: object, event: CollectionChangeEvent) -> None:
        if event.kind == "remove" and event.uid is not None:
            removes.append(event.uid)

    _reset_signal(type(col))
    type(col).connect(on_remove, phase="runtime", kind="remove")
    col.remove_type(PluginItem.__name__)
    await col.commit()
    type(col).disconnect(on_remove, phase="runtime", kind="remove")
    if PluginItem.__name__ in col._entry_types:
        _fail("remove_type 后类型应消失")
    if u1 in col or u2 in col:
        _fail("该类实例应被级联删除")
    if uk not in col:
        _fail("他类型成员应保留")
    if set(removes) != {u1, u2}:
        _fail(f"应发两条 remove，收到 {removes}")
    _ok("remove_type 级联清空该类实例")


async def test_remove_type_guard_rollback() -> None:
    class PluginItem(BoundEntry):
        class Info(ConfigGroup):
            name: str = "p"

        info: Info = Field(default_factory=Info)

    col = BoundCollection()
    await col.activate()
    col.add_type(PluginItem)
    await col.commit()
    uid = col.add(PluginItem, wire={"info": {"name": "x"}})
    await col.commit()

    async def refuse(
        collection: ConfigCollection[BoundEntry],
        member_uid: UUID,
        entry: BoundEntry,
    ) -> None:
        raise RuntimeError("refuse remove")

    col.register_remove_guard(refuse)
    col.remove_type(PluginItem)
    try:
        await col.commit()
        _fail("guard 失败应整笔失败")
    except Exception:
        pass
    if PluginItem.__name__ not in col._entry_types:
        _fail("回滚后类型应仍在")
    if uid not in col:
        _fail("回滚后成员应仍在")
    if col[uid].info.name != "x":
        _fail("回滚后字段应不变")
    col.unregister_remove_guard(refuse)
    _ok("remove_type guard 失败整笔回滚")


async def test_reload_type_preserves_uid_order() -> None:
    class PluginItem(BoundEntry):
        class Info(ConfigGroup):
            name: str = "p"
            tag: str = "v1"

        info: Info = Field(default_factory=Info)

    class Spacer(BoundEntry):
        class Info(ConfigGroup):
            name: str = "s"

        info: Info = Field(default_factory=Info)

    col = BoundCollection([Spacer])
    await col.activate()
    col.add_type(PluginItem)
    await col.commit()
    s = col.add(Spacer, wire={"info": {"name": "mid"}})
    a = col.add(PluginItem, wire={"info": {"name": "a", "tag": "t1"}})
    b = col.add(PluginItem, wire={"info": {"name": "b", "tag": "t2"}})
    await col.commit()
    # 顺序: mid, a, b → 调成 a, mid, b
    col.set_order([a, s, b])
    await col.commit()

    class PluginItem(BoundEntry):  # noqa: F811 — 同名新类
        class Info(ConfigGroup):
            name: str = "p"
            tag: str = "v2"
            note: str = "n"

        info: Info = Field(default_factory=Info)

    seen: list[str] = []

    async def on_reload(sender: object, event: CollectionChangeEvent) -> None:
        if event.kind == "reload_type":
            seen.append("reload")
            if event.reloaded_uids != (a, b):
                _fail(f"reloaded_uids 异常: {event.reloaded_uids}")

    async def on_remove(sender: object, event: CollectionChangeEvent) -> None:
        if event.kind == "remove":
            seen.append("remove")

    _reset_signal(type(col))
    type(col).connect(on_reload, phase="runtime", kind="reload_type")
    type(col).connect(on_remove, phase="runtime", kind="remove")
    col.reload_type(PluginItem)
    await col.commit()
    type(col).disconnect(on_reload, phase="runtime", kind="reload_type")
    type(col).disconnect(on_remove, phase="runtime", kind="remove")

    if "remove" in seen:
        _fail("reload 中间不应发 remove")
    if seen != ["reload"]:
        _fail(f"应仅发 reload_type，收到 {seen}")
    if [item.uid for item in col.order] != [a, s, b]:
        _fail(f"order 应保持: {[item.uid for item in col.order]}")
    if type(col[a]) is not PluginItem or type(col[b]) is not PluginItem:
        _fail("成员类应换为新 PluginItem")
    if col[a].info.name != "a" or col[a].info.tag != "t1":
        _fail("Wire 字段应保留")
    if getattr(col[a].info, "note", None) != "n":
        _fail("新类默认字段应生效")
    if col._entry_types["PluginItem"] is not PluginItem:
        _fail("类型表应指向新类")
    _ok("reload_type 保留 uid/order 且换类")


async def test_reload_type_activate_failure_rollback() -> None:
    class PluginItem(BoundEntry):
        class Info(ConfigGroup):
            name: str = "p"
            tag: str = "ok"

        info: Info = Field(default_factory=Info)

    col = BoundCollection()
    await col.activate()
    col.add_type(PluginItem)
    await col.commit()
    uid = col.add(PluginItem, wire={"info": {"name": "keep", "tag": "old"}})
    await col.commit()
    old_cls = col._entry_types["PluginItem"]

    class PluginItem(BoundEntry):  # noqa: F811
        class Info(ConfigGroup):
            name: str = "p"
            # 必填且无默认 → 旧 Wire 缺字段时 activate 可能仍用默认；改用校验器拒绝
            tag: str = "x"

        info: Info = Field(default_factory=Info)

        async def _activate_from_payload(self, payload: dict) -> None:  # type: ignore[override]
            raise RuntimeError("boom activate")

    col.reload_type(PluginItem)
    try:
        await col.commit()
        _fail("activate 失败应整笔回滚")
    except Exception:
        pass
    if col._entry_types["PluginItem"] is not old_cls:
        _fail("回滚后类型表应仍是旧类")
    if uid not in col or type(col[uid]) is not old_cls:
        _fail("回滚后实例应仍是旧类")
    if col[uid].info.name != "keep":
        _fail("回滚后字段应不变")
    _ok("reload_type activate 失败整笔回滚")


async def test_reload_type_locked_member() -> None:
    class PluginItem(BoundEntry):
        class Info(ConfigGroup):
            name: str = "p"

        info: Info = Field(default_factory=Info)

    col = BoundCollection()
    await col.activate()
    col.add_type(PluginItem)
    await col.commit()
    uid = col.add(PluginItem, wire={"info": {"name": "x"}})
    await col.commit()
    ticket = await col[uid].lock_x()

    class PluginItem(BoundEntry):  # noqa: F811
        class Info(ConfigGroup):
            name: str = "p"
            extra: int = 1

        info: Info = Field(default_factory=Info)

    try:
        col.reload_type(PluginItem)
        _fail("锁定成员应拒绝 reload_type")
    except ValueError:
        pass
    await col[uid].unlock(ticket)
    _ok("成员锁定时拒绝 reload_type")


async def test_reload_type_str_force_rematerialize() -> None:
    class PluginItem(BoundEntry):
        class Info(ConfigGroup):
            name: str = "p"

        info: Info = Field(default_factory=Info)

    col = BoundCollection()
    await col.activate()
    col.add_type(PluginItem)
    await col.commit()
    uid = col.add(PluginItem, wire={"info": {"name": "x"}})
    await col.commit()
    old = col[uid]
    col.reload_type("PluginItem")  # 同类强制重建
    await col.commit()
    if uid not in col:
        _fail("str reload 应保留 uid")
    if col[uid] is old:
        _fail("str reload 应换新实例")
    if type(col[uid]) is not PluginItem:
        _fail("str reload 应仍是表内类")
    if col[uid].info.name != "x":
        _fail("字段应保留")
    _ok("reload_type(str) 按表内类强制 rematerialize")


async def test_reload_type_unregistered() -> None:
    class PluginItem(BoundEntry):
        class Info(ConfigGroup):
            name: str = "p"

        info: Info = Field(default_factory=Info)

    col = BoundCollection()
    await col.activate()
    try:
        col.reload_type("PluginItem")
        _fail("未登记应 ValueError")
    except ValueError:
        pass
    _ok("未登记名 reload_type 拒绝")


async def main() -> int:
    tests = [
        test_add_type_then_add,
        test_add_type_signal_can_add_new_type,
        test_same_batch_remove_type_then_add_rejected,
        test_add_type_rejects_non_bound,
        test_add_type_name_conflict,
        test_remove_type_cascade,
        test_remove_type_guard_rollback,
        test_reload_type_preserves_uid_order,
        test_reload_type_activate_failure_rollback,
        test_reload_type_locked_member,
        test_reload_type_str_force_rematerialize,
        test_reload_type_unregistered,
    ]
    failed = 0
    for test in tests:
        try:
            await test()
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback

            print(f"FAIL: {test.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
