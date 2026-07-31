"""P2：ui_hints / select / legacy / remove_guard / connect(kind=)。"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from pydantic import Field

from app.config import (
    CollectionChangeEvent,
    ConfigAggregateError,
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    ConfigRemoveRejected,
    FilePath,
    Select,
    encrypted,
    legacy,
    ui,
)
from app.config.core.manager import config_manager


def _ok(msg: str) -> None:
    print(f"OK: {msg}")


def _fail(msg: str) -> None:
    raise AssertionError(msg)


def _reset_signal(cls: type) -> None:
    from blinker import Signal

    cls.signal = Signal()
    cls._signal_workspace = None


async def test_ui_hints_virtual_field() -> None:
    class Info(ConfigGroup):
        enabled: bool = True
        name: str = ""
        kind: Literal["a", "b"] = "a"
        secret: Annotated[str, encrypted()] = ""
        path: FilePath = ""
        tags: Annotated[list[dict], ui(widget="tags")] = Field(default_factory=list)  # type: ignore[valid-type]

    class Cfg(ConfigEntry):
        info: Info = Field(default_factory=Info)

    hints = Cfg._cfg_ui_hints
    by_field: dict[str, dict[str, Any]] = {
        str(h.get("field", "")): cast(dict[str, Any], h)
        for h in hints["info"]
        if h.get("field") is not None
    }
    if by_field["enabled"].get("component") != "switch":
        _fail(f"bool → switch: {by_field['enabled']}")
    if by_field["kind"].get("component") != "select" or by_field["kind"].get("multiple"):
        _fail(f"Literal → select: {by_field['kind']}")
    if not by_field["secret"].get("secret"):
        _fail(f"encrypted → secret: {by_field['secret']}")
    if by_field["path"].get("component") != "path":
        _fail(f"FilePath → path: {by_field['path']}")
    if by_field["tags"].get("widget") != "tags":
        _fail(f"ui(widget=tags): {by_field['tags']}")

    cfg = Cfg()
    await cfg.activate()
    dumped = cfg.model_dump()
    ui_block = dumped.get("ui", {}).get("hints")
    if not isinstance(ui_block, dict) or "info" not in ui_block:
        _fail(f"model_dump 应含 ui.hints: {dumped.get('ui')}")
    plain = await cfg.to_dict()
    if "ui" in plain:
        _fail("默认 to_dict 不应含 ui")
    _ok("ui.hints 虚拟字段与类型推导")


async def test_select_endpoint_marker() -> None:
    class Data(ConfigGroup):
        emu: Annotated[str, Select(endpoint="/api/emu")] = ""

    class Cfg(ConfigEntry):
        data: Data = Field(default_factory=Data)

    hint: dict[str, Any] = {
        str(h.get("field", "")): cast(dict[str, Any], h)
        for h in Cfg._cfg_ui_hints["data"]
        if h.get("field") is not None
    }["emu"]
    if hint.get("component") != "select" or hint.get("endpoint") != "/api/emu":
        _fail(f"Select(endpoint=) 未生效: {hint}")
    _ok("Select endpoint 标记")


async def test_legacy_activate_fallback() -> None:
    class Data(ConfigGroup):
        username: Annotated[str, legacy(group="info", name="name")] = ""

    class Cfg(ConfigEntry):
        data: Data = Field(default_factory=Data)

    cfg = Cfg.build(wire={"info": {"name": "旧名"}})
    await cfg.activate()
    if cfg.data.username != "旧名":
        _fail(f"legacy 应从旧位置回退，实际 {cfg.data.username!r}")

    cfg2 = Cfg.build(wire={"data": {"username": "新名"}, "info": {"name": "旧名"}})
    await cfg2.activate()
    if cfg2.data.username != "新名":
        _fail("新位置有值时不应被 legacy 覆盖")
    _ok("legacy 激活回退")


async def test_remove_guard_rejects_and_keeps_live() -> None:
    class Item(ConfigEntry):
        class Info(ConfigGroup):
            name: str = ""

        info: Info = Field(default_factory=Info)

    col = ConfigCollection(Item)
    await col.activate()
    uid = col.add(Item, wire={"info": {"name": "x"}})
    await col.commit()

    async def guard(
        collection: ConfigCollection[Item],
        remove_uid: UUID,
        entry: ConfigEntry,
    ) -> None:
        raise ConfigRemoveRejected("仍在运行")

    col.register_remove_guard(guard)
    col.remove(uid)
    try:
        await col.commit()
        _fail("守卫拒绝后应抛 ConfigAggregateError")
    except ConfigAggregateError as exc:
        if not any(isinstance(e, ConfigRemoveRejected) for e in exc.errors):
            _fail(f"应聚合 ConfigRemoveRejected: {exc.errors}")

    if uid not in col:
        _fail("守卫失败后 live 成员应仍在")

    col.unregister_remove_guard(guard)
    col.remove(uid)
    await col.commit()
    if uid in col:
        _fail("卸守卫后应能删除")
    _ok("remove_guard 拒绝并保留 live")


async def test_connect_kind_filter() -> None:
    class Item(ConfigEntry):
        class Info(ConfigGroup):
            name: str = ""

        info: Info = Field(default_factory=Info)

    _reset_signal(ConfigCollection)
    col = ConfigCollection(Item)
    await col.activate()

    adds: list[str] = []
    removes: list[str] = []

    async def on_add(sender: object, event: CollectionChangeEvent) -> None:
        adds.append(event.kind)

    async def on_remove(sender: object, event: CollectionChangeEvent) -> None:
        removes.append(event.kind)

    col.connect(on_add, phase="runtime", kind="add")
    col.connect(on_remove, phase="runtime", kind="remove")

    uid = col.add(Item, wire={"info": {"name": "a"}})
    await col.commit()
    col.remove(uid)
    await col.commit()

    if adds != ["add"]:
        _fail(f"kind=add 过滤失败: {adds}")
    if removes != ["remove"]:
        _fail(f"kind=remove 过滤失败: {removes}")

    # init phase + kind=add 应匹配 init_add
    inits: list[str] = []

    async def on_init_add(sender: object, event: CollectionChangeEvent) -> None:
        inits.append(event.kind)

    ConfigCollection.connect(on_init_add, phase="init", kind="add")
    col2 = ConfigCollection(
        Item,
        wire={"order": [{"uid": str(UUID(int=1)), "type": "Item"}], "data": {}},
    )
    await col2.activate()
    if inits != ["init_add"]:
        _fail(f"phase=init kind=add 应匹配 init_add: {inits}")
    ConfigCollection.disconnect(on_init_add, phase="init", kind="add")
    _ok("connect(kind=) 过滤")


async def main() -> None:
    config_manager._collections.clear()
    config_manager._roots.clear()
    tests = [
        test_ui_hints_virtual_field,
        test_select_endpoint_marker,
        test_legacy_activate_fallback,
        test_remove_guard_rejects_and_keeps_live,
        test_connect_kind_filter,
    ]
    failed = 0
    for test in tests:
        try:
            await test()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            print(f"FAIL: {test.__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
