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
    ExportContext,
    FilePath,
    Select,
    UiVisibility,
    encrypted,
    legacy,
    ui,
)
from app.config.core.manager import config_manager
from app.config.shortcuts import ui_visibility
from app.utils.constants import UTC4, UTC8
from datetime import datetime


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
        path: FilePath = None
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
    for group_hints in ui_block.values():
        for h in group_hints:
            if "readonly" in h:
                _fail(f"hints 不应含 readonly: {h}")
            if "editable" not in h:
                _fail(f"hints 应含 editable: {h}")
    plain = await cfg.to_dict()
    if "ui" in plain:
        _fail("默认 to_dict 不应含 ui")
    _ok("ui.hints 虚拟字段与类型推导")


async def test_ui_visibility_and_lock() -> None:
    class Info(ConfigGroup):
        advanced: bool = False
        secret: str = ""
        always_off: Annotated[str, ui(visibility=UiVisibility.DISABLE)] = ""
        hidden: Annotated[str, ui(visibility=UiVisibility.HIDE)] = ""

    class Cfg(ConfigEntry):
        info: Info = Field(default_factory=Info)

        @ui_visibility("info.secret")
        def _vis_secret(self) -> UiVisibility:
            return (
                UiVisibility.SHOW
                if self.effective.info.advanced
                else UiVisibility.HIDE
            )

    cfg = Cfg()
    await cfg.activate()

    def by_field(hints: object) -> dict[str, dict[str, Any]]:
        block = cast(dict[str, Any], hints).get("info") or []
        return {
            str(h.get("field", "")): cast(dict[str, Any], h)
            for h in block
            if isinstance(h, dict)
        }

    h0 = by_field(cfg.ui.hints)
    if "secret" in h0 or "hidden" in h0:
        _fail(f"advanced=False 时 secret/hidden 应隐藏: {h0}")
    if h0.get("always_off", {}).get("editable") is not False:
        _fail(f"DISABLE 应为 editable=false: {h0.get('always_off')}")
    if h0.get("advanced", {}).get("editable") is not True:
        _fail(f"SHOW 字段应可改: {h0.get('advanced')}")

    cfg.info.advanced = True
    await cfg.commit()
    h1 = by_field(cfg.ui.hints)
    if "secret" not in h1:
        _fail(f"advanced=True 时应显示 secret: {h1}")
    if h1["secret"].get("editable") is not True:
        _fail(f"secret SHOW 应可改: {h1['secret']}")

    # update 跳过 hide/disable
    cold = Cfg.model_validate(
        {
            "info": {
                "advanced": True,
                "secret": "from-body",
                "always_off": "should-skip",
                "hidden": "also-skip",
            }
        }
    )
    await cfg.update(cold)
    if cfg.info.secret != "from-body":
        _fail(f"update 应写入 SHOW 字段 secret: {cfg.info.secret!r}")
    if cfg.info.always_off != "":
        _fail(f"update 应跳过 DISABLE: {cfg.info.always_off!r}")
    if cfg.info.hidden != "":
        _fail(f"update 应跳过 HIDE: {cfg.info.hidden!r}")

    # check_visibility=False：程序内调用全量写入，显隐不再拦
    cold2 = Cfg.model_validate(
        {"info": {"always_off": "forced", "hidden": "forced-too"}}
    )
    await cfg.update(cold2, check_visibility=False)
    if cfg.info.always_off != "forced":
        _fail(f"check_visibility=False 应写入 DISABLE: {cfg.info.always_off!r}")
    if cfg.info.hidden != "forced-too":
        _fail(f"check_visibility=False 应写入 HIDE: {cfg.info.hidden!r}")
    if cfg.info.secret != "from-body":
        _fail(f"未赋值字段仍应跳过，secret 不该被清: {cfg.info.secret!r}")

    # 跳过显隐 ≠ 跳过虚拟字段：ui 组是虚拟的，update 不该碰
    cold3 = Cfg.model_validate({"info": {"advanced": True}})
    await cfg.update(cold3, check_visibility=False)
    if cfg.ui.hints is None:
        _fail("虚拟字段 ui.hints 不应被 update 写坏")

    # api 导出剔除 hide
    api = cfg.model_dump(context=ExportContext(audience="api"))
    if "hidden" in api.get("info", {}):
        _fail("audience=api 不应含 hide 字段")
    if "secret" not in api.get("info", {}):
        _fail("audience=api 应含 SHOW secret")
    persist = await cfg.to_dict()
    if "hidden" not in persist.get("info", {}):
        _fail("persist 应忽视 UI，含 hidden")
    if "ui" in persist:
        _fail("persist 不应含 ui")

    ticket = await cfg.lock_x()
    h_locked = by_field(cfg.ui.hints)
    for fname, hint in h_locked.items():
        if hint.get("editable") is not False:
            _fail(f"上锁后 {fname} 应为 editable=false: {hint}")
    await cfg.unlock(ticket)
    h_unlocked = by_field(cfg.ui.hints)
    if h_unlocked.get("advanced", {}).get("editable") is not True:
        _fail("解锁后 advanced 应恢复可改")
    _ok("UI 显隐 / update 跳过 / audience / is_locked 全只读")


async def test_date_from_datetime_tz_and_ui_format() -> None:
    from datetime import date, timezone

    from app.config import tz

    class Info(ConfigGroup):
        only_hm: Annotated[datetime, ui(format="hm")] = datetime(
            2000, 1, 1, 8, 0, tzinfo=UTC8
        )
        day: date = date(2000, 1, 1)
        day_tz: Annotated[date, tz(UTC4)] = date(2000, 1, 1)

    class Cfg(ConfigEntry):
        info: Info = Field(default_factory=Info)

    hints = {
        str(h.get("field", "")): cast(dict[str, Any], h)
        for h in Cfg._cfg_ui_hints["info"]
    }
    if hints["only_hm"].get("component") != "time" or hints["only_hm"].get("format") != "hm":
        _fail(f"ui(format=hm) 应为 time/hm: {hints['only_hm']}")
    if hints["day"].get("component") != "date":
        _fail(f"date 组件: {hints['day']}")

    # ── 未激活态：validate_assignment 带 entry，时区转换应生效 ──
    cold = Cfg()
    cold.info.day = datetime(2000, 1, 1, 20, 0, tzinfo=timezone.utc)
    if cold.info.day != date(2000, 1, 2):
        _fail(f"未激活 date←datetime 应按 Entry.timezone: {cold.info.day!r}")

    cfg = Cfg()
    await cfg.activate()
    # datetime 字段不再强制时区（naive 保持 naive）
    cfg.info.only_hm = datetime(2000, 1, 1, 10, 15)
    await cfg.commit()
    if cfg.info.only_hm.tzinfo is not None:
        _fail(f"datetime 字段不应自动赋时区: {cfg.info.only_hm!r}")
    # date←datetime：字段 tz=UTC4
    cfg.info.day_tz = datetime(2000, 1, 1, 22, 0, tzinfo=UTC8)
    await cfg.commit()
    # 22:00 UTC+8 → 14:00 UTC+4 同日
    if cfg.info.day_tz != date(2000, 1, 1):
        _fail(f"字段 tz=UTC4 转换后日期不符: {cfg.info.day_tz!r}")
    _ok("date←datetime 时区转换（含未激活）与 UI format=hm")


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

    cfg = Cfg.build(payload={"info": {"name": "旧名"}})
    await cfg.activate()
    if cfg.data.username != "旧名":
        _fail(f"legacy 应从旧位置回退，实际 {cfg.data.username!r}")

    cfg2 = Cfg.build(payload={"data": {"username": "新名"}, "info": {"name": "旧名"}})
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
    uid = col.add(Item, payload={"info": {"name": "x"}})
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

    uid = col.add(Item, payload={"info": {"name": "a"}})
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
        payload={"order": [{"uid": str(UUID(int=1)), "type": "Item"}], "data": {}},
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
        test_ui_visibility_and_lock,
        test_date_from_datetime_tz_and_ui_format,
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
