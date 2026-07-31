"""配置基类 v2 基础功能自动检查（独立包，不依赖 app/）。

用法（仓库根目录）::

    python -m app.config.tests.test_config_base
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import UUID

from blinker import Signal
from pydantic import AfterValidator, Field

from app.config import (
    ConfigAggregateError,
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    CollectionChangeEvent,
    FieldChangeEvent,
    NodeState,
    Trigger,
    Virtual,
    config_manager,
)
from app.config.fields.encrypted import EncryptedValue, encrypted
from app.config.fields import RefDeleteAction
from app.config.shortcuts import ref, trigger_field
from app.config.examples.reference_config import (
    ExampleQueue,
    ExampleQueueItem,
    ExampleScript,
    ExampleWebhook,
)


def _fail(message: str) -> None:
    raise AssertionError(message)


def _ok(message: str) -> None:
    print(f"OK: {message}")


def _reset_signal(cls: type) -> None:
    cls.signal = Signal()


# ─────────────── ref 池：模块级脚本集合（name 全局唯一）───────────────

_scripts = ConfigCollection([ExampleScript], name="scripts")
_scripts_loaded = False


async def _ensure_scripts() -> ConfigCollection[ExampleScript]:
    global _scripts_loaded
    if not _scripts_loaded:
        await _scripts.activate()
        _scripts_loaded = True
    return _scripts


# ──────────────────────────── 测试 ────────────────────────────


async def test_entry_init_with_data() -> None:
    cfg = ExampleWebhook.build(
        uid="11111111-1111-4111-8111-111111111111",
        wire={"info": {"name": "构造注入", "enabled": False}},
    )
    await cfg.activate()
    if str(cfg.uid) != "11111111-1111-4111-8111-111111111111":
        _fail("构造 uid 未生效")
    if cfg.info.name != "构造注入" or cfg.info.enabled is not False:
        _fail("构造 data 未生效")
    _ok("ConfigEntry 构造 uid/data")


async def test_toml_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "webhook.toml"
        cfg = ExampleWebhook.build(file=path)
        await cfg.activate()
        cfg.info.name = "测试"
        cfg.data.url = "https://example.com/hook"
        await cfg.commit()
        await config_manager.flush()

        loaded = ExampleWebhook.build(file=path)
        await loaded.activate()
        if loaded.info.name != "测试":
            _fail("TOML 往返 name 不一致")
        if loaded.data.url != "https://example.com/hook":
            _fail("TOML 往返 url 不一致")
    _ok("Entry TOML 往返")


async def test_missing_toml_returns_default() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "missing.toml"
        cfg = ExampleWebhook.build(file=path)
        await cfg.activate()
        if cfg.info.name != "示例 Webhook":
            _fail("空 TOML 应保留默认")
    _ok("缺失 TOML 返回默认")


async def test_rejects_non_toml_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        try:
            ExampleWebhook.build(file=path)
            _fail("非 .toml 路径应拒绝")
        except ValueError:
            pass
    _ok("拒绝非 TOML 路径")


async def test_collection_init_with_data() -> None:
    uid = uuid.UUID("22222222-2222-4222-8222-222222222222")
    col = ConfigCollection.build(
        [ExampleQueue],
        wire={
            "order": [{"uid": str(uid), "type": "ExampleQueue"}],
            "data": {str(uid): {"info": {"name": "队列构造"}}},
        },
    )
    await col.activate()
    if uid not in col:
        _fail("Collection 构造后缺少实例")
    if col[uid].info.name != "队列构造":
        _fail("Collection 构造 data 未生效")
    if col[uid].activation_state != NodeState.ACTIVE:
        _fail(f"Wire 热化成员应为 ACTIVE，实际 {col[uid].activation_state}")
    dumped = await col[uid].to_dict()
    if dumped.get("info", {}).get("name") != "队列构造":
        _fail(f"成员 to_dict 异常: {dumped}")
    _ok("ConfigCollection 构造 data（Wire 形状）")


async def test_add_member_is_active() -> None:
    col = ConfigCollection([ExampleScript])
    await col.activate()
    uid = col.add(ExampleScript)
    await col.commit()
    member = col[uid]
    if member.activation_state != NodeState.ACTIVE:
        _fail(f"add+commit 后成员应为 ACTIVE，实际 {member.activation_state}")
    await member.to_dict()
    _ok("add+commit 成员为 ACTIVE")


async def test_add_duplicate_uid_rejected() -> None:
    col = ConfigCollection([ExampleScript])
    await col.activate()
    uid = col.add(ExampleScript)
    await col.commit()
    col.add(ExampleScript, uid=uid)
    try:
        await col.commit()
        _fail("重复 uid 应在 commit 时拒绝")
    except ConfigAggregateError as exc:
        if not any("已存在" in str(e) for e in exc.errors):
            _fail(f"应含 uid 已存在: {exc.errors}")
    if col._staged_ops:
        _fail("commit 执行后即使失败也应清空 stage")
    _ok("重复 uid 在 commit_op 拒绝")


async def test_entry_type_name_collision() -> None:
    type_a = type("SameName", (ExampleScript,), {"__module__": "pkg_a"})
    type_b = type("SameName", (ExampleScript,), {"__module__": "pkg_b"})
    try:
        ConfigCollection([type_a, type_b])
        _fail("同名不同类型应在声明时报错")
    except ValueError as exc:
        if "类型名冲突" not in str(exc):
            _fail(f"错误信息应含类型名冲突: {exc}")
    _ok("声明期 Entry 类型名冲突")


async def test_connect_reuse_wrapper_after_disconnect() -> None:
    received: list[str] = []

    class Info(ConfigGroup):
        name: str = ""

    class Cfg(ConfigEntry):
        info: Info = Field(default_factory=Info)

    _reset_signal(Cfg)
    cfg = Cfg()
    await cfg.activate()

    async def slot(sender: object, event: FieldChangeEvent) -> None:
        received.append(str(event.value))

    cfg.connect(slot, phase="runtime", group="info", field="name")
    try:
        cfg.connect(slot, phase="runtime", group="info", field="name")
        _fail("已连接时应拒绝重复 connect")
    except ValueError:
        pass

    cfg.disconnect(slot, phase="runtime", group="info", field="name")
    cfg.connect(slot, phase="runtime", group="info", field="name")  # 复用 wrappers 挂载
    cfg.info.name = "x"
    await cfg.commit()
    if received != ["x"]:
        _fail(f"disconnect 后再 connect 应能触发: {received}")
    _ok("disconnect 后复用 wrappers 再 connect")


async def test_ref_missing_target_raises() -> None:
    class Item(ConfigEntry):
        class Info(ConfigGroup):
            script_id: Annotated[
                str,
                ref("no_such_pool", default="-"),
            ] = "-"

        info: Info = Field(default_factory=Info)

    item = Item()
    try:
        await item.activate()
        _fail("未登记 ref 目标应在 activate 时报错")
    except ConfigAggregateError as exc:
        if not any(
            isinstance(e, LookupError) and "no_such_pool" in str(e) for e in exc.errors
        ):
            _fail(f"聚合错误应含目标 LookupError: {exc.errors}")
    if item.activation_state != NodeState.ACTIVE:
        _fail("部分失败后仍应 ACTIVE（事务已提交）")
    if item._pending_wire is not None:
        _fail("外层 COMMIT 后应清空 pending")
    _ok("ref 目标未登记时 activate 报错")


async def test_activate_collects_all_field_errors() -> None:
    class Info(ConfigGroup):
        a: Annotated[int, Field(ge=0)] = 0
        b: Annotated[int, Field(ge=0)] = 0

    class Cfg(ConfigEntry):
        info: Info = Field(default_factory=Info)

    cfg = Cfg.build(wire={"info": {"a": -1, "b": -2}})
    try:
        await cfg.activate()
        _fail("非法字段应导致 activate 失败")
    except ConfigAggregateError as exc:
        if len(exc.errors) < 2:
            _fail(f"应收集两个字段错误，实际 {exc.errors}")
    if cfg.activation_state != NodeState.ACTIVE:
        _fail("字段失败后仍应 ACTIVE（成功路径已 COMMIT）")
    if cfg.info.a != 0 or cfg.info.b != 0:
        _fail(f"失败字段应保留先验值，实际 a={cfg.info.a} b={cfg.info.b}")
    if cfg._pending_wire is not None:
        _fail("COMMIT 后 pending 应清空")
    try:
        await cfg.activate()
        _fail("已 ACTIVE 不可再次 activate")
    except ValueError:
        pass
    _ok("activate 收集全部字段错误")


async def test_activate_pending_survives_outer_rollback() -> None:
    """嵌套 activate 若父事务 ROLLBACK，live pending 须保留供重试。"""

    class Info(ConfigGroup):
        name: str = ""

    class Cfg(ConfigEntry):
        info: Info = Field(default_factory=Info)

    cfg = Cfg.build(wire={"info": {"name": "from-wire"}})
    if cfg._pending_wire is None:
        _fail("build(wire=) 应暂存 pending")

    from app.config.core.manager import config_manager

    try:
        async with config_manager.transaction():
            await cfg.activate()
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass

    if cfg.activation_state != NodeState.INACTIVE:
        _fail("父 ROLLBACK 后应仍为 INACTIVE")
    if cfg._pending_wire is None:
        _fail("父 ROLLBACK 后 live pending 应保留")
    await cfg.activate()
    if cfg.info.name != "from-wire":
        _fail(f"重试 activate 应消费原 wire，实际 name={cfg.info.name!r}")
    if cfg._pending_wire is not None:
        _fail("成功 activate 后应清空 pending")
    _ok("嵌套 activate 父 ROLLBACK 保留 pending")


async def test_activate_init_handler_failure_keeps_prior() -> None:
    """init_set handler 失败时 init 事务回滚，字段保留先验值（不脏写）。"""

    class Info(ConfigGroup):
        name: str = "cold"
        other: str = "keep"

    class Cfg(ConfigEntry):
        info: Info = Field(default_factory=Info)

    @Cfg.connect(phase="init", group="info", field="name")
    async def boom(sender: object, event: FieldChangeEvent) -> None:
        raise RuntimeError("init boom")

    cfg = Cfg.build(wire={"info": {"name": "hot", "other": "ok"}})
    try:
        await cfg.activate()
        _fail("init handler 失败应抛出聚合错误")
    except ConfigAggregateError as exc:
        # activate → commit 会嵌套 ConfigAggregateError（规格：不展平）
        def _walk(errs: list[Exception]) -> bool:
            for e in errs:
                if isinstance(e, RuntimeError) and "init boom" in str(e):
                    return True
                if isinstance(e, ConfigAggregateError) and _walk(e.errors):
                    return True
            return False

        if not _walk(exc.errors):
            _fail(f"应含 init boom: {exc.errors}")
    if cfg.activation_state != NodeState.ACTIVE:
        _fail("部分失败后仍应 ACTIVE")
    if cfg.info.name != "cold":
        _fail(f"name 应保留先验 cold，实际 {cfg.info.name!r}")
    if cfg.info.other != "ok":
        _fail(f"成功字段 other 应落地，实际 {cfg.info.other!r}")
    Cfg.disconnect(boom, phase="init", group="info", field="name")
    _ok("activate init handler 失败不脏写")


async def test_activate_init_add_handler_failure_keeps_prior() -> None:
    """P1（Collection）：init_add handler 失败时 init 回滚，已成功成员保留、失败成员不进普通 ws。"""

    class Item(ConfigEntry):
        class Info(ConfigGroup):
            name: str = ""

        info: Info = Field(default_factory=Info)

    ok_uid = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    boom_uid = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")

    @ConfigCollection.connect(phase="init")
    async def boom(sender: object, event: CollectionChangeEvent) -> None:
        if event.kind == "init_add" and event.uid == boom_uid:
            raise RuntimeError("init add boom")

    col = ConfigCollection.build(
        [Item],
        wire={
            "order": [
                {"uid": str(ok_uid), "type": "Item"},
                {"uid": str(boom_uid), "type": "Item"},
            ],
            "data": {
                str(ok_uid): {"info": {"name": "ok"}},
                str(boom_uid): {"info": {"name": "boom"}},
            },
        },
    )
    try:
        await col.activate()
        _fail("init_add handler 失败应抛出聚合错误")
    except ConfigAggregateError as exc:

        def _walk(errs: list[Exception]) -> bool:
            for e in errs:
                if isinstance(e, RuntimeError) and "init add boom" in str(e):
                    return True
                if isinstance(e, ConfigAggregateError) and _walk(e.errors):
                    return True
            return False

        if not _walk(exc.errors):
            _fail(f"应含 init add boom: {exc.errors}")
    finally:
        ConfigCollection.disconnect(boom, phase="init")

    if col.activation_state != NodeState.ACTIVE:
        _fail("部分失败后仍应 ACTIVE")
    if ok_uid not in col:
        _fail("成功成员应保留在集合中")
    if boom_uid in col:
        _fail("失败成员不应脏写入普通 ws")
    if col[ok_uid].info.name != "ok":
        _fail(f"成功成员 name 应落地，实际 {col[ok_uid].info.name!r}")
    _ok("activate init_add handler 失败不脏写")


async def test_init_add_failure_orphan_entry_may_reach_active() -> None:
    """设计固化：init_add 失败后成员可不在集合内，但 activate 结果仍可经外层 COMMIT 落地。

    集合壳 ROLLBACK_init；成员在共享外层事务中热化，失败 ADD 不撤销成员自身 COMMIT。
    未挂入集合的实例可被 GC，不视为缺陷。
    """

    class Item(ConfigEntry):
        class Info(ConfigGroup):
            name: str = ""

        info: Info = Field(default_factory=Info)

    boom_uid = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    held: list[Item] = []

    @ConfigCollection.connect(phase="init")
    async def boom(sender: object, event: CollectionChangeEvent) -> None:
        if event.kind == "init_add" and event.uid == boom_uid:
            held.append(cast(Item, event.entry))
            raise RuntimeError("init add boom")

    col = ConfigCollection.build(
        [Item],
        wire={
            "order": [{"uid": str(boom_uid), "type": "Item"}],
            "data": {str(boom_uid): {"info": {"name": "boom"}}},
        },
    )
    try:
        try:
            await col.activate()
        except ConfigAggregateError:
            pass
        if not held:
            _fail("应捕获失败成员实例")
        orphan = held[0]
        if boom_uid in col:
            _fail("失败成员不应在集合 data")
        if orphan.activation_state != NodeState.ACTIVE:
            _fail("设计下成员 activate 可完成并 ACTIVE")
        if orphan.info.name != "boom":
            _fail(f"成员热化结果可经外层 COMMIT 保留，实际 name={orphan.info.name!r}")
        _ok("init_add 失败：孤儿可 ACTIVE（设计）")
    finally:
        ConfigCollection.disconnect(boom, phase="init")


async def test_partial_ref_connect_leaves_active_without_retry_activate() -> None:
    """设计固化：activate 时部分 ref 订阅读失败仍可 ACTIVE；不可靠再 activate 修补。

    缺陷字段的处理：启动前保证目标池已登记；或抛弃重建节点；或改业务代码。
    框架不提供「对已 ACTIVE 节点再 activate / 自动补订 ref」的重试语义。
    """
    scripts = ConfigCollection([ExampleScript], name="scripts_partial_ref_design")
    await scripts.activate()

    class Item(ConfigEntry):
        class Info(ConfigGroup):
            ok_ref: Annotated[
                str,
                ref(
                    "scripts_partial_ref_design",
                    default="-",
                    allow_values=("-",),
                    on_delete=RefDeleteAction.SET_DEFAULT,
                ),
            ] = "-"
            late_ref: Annotated[
                str,
                ref(
                    "late_pool_partial_ref_design",
                    default="-",
                    allow_values=("-",),
                    on_delete=RefDeleteAction.SET_DEFAULT,
                ),
            ] = "-"

        info: Info = Field(default_factory=Info)

    item = Item.build(wire={"info": {"ok_ref": "-", "late_ref": "-"}})
    try:
        await item.activate()
        _fail("未登记 late 池应导致 activate 聚合错误")
    except ConfigAggregateError:
        pass
    if item.activation_state != NodeState.ACTIVE:
        _fail("部分订阅读失败后仍可 ACTIVE（与字段部分失败同策略）")
    if len(item._ref_receivers) != 1:
        _fail(f"仅成功字段订上，实际 receivers={len(item._ref_receivers)}")
    try:
        await item.activate()
        _fail("已 ACTIVE 不可再 activate（无重试修补入口）")
    except ValueError:
        pass
    _ok("部分 ref 失败：ACTIVE 且禁止再 activate（设计）")


async def test_encrypted_field() -> None:
    class Secrets(ConfigGroup):
        token: Annotated[str, encrypted()] = ""

    class Auth(ConfigEntry):
        secrets: Secrets = Field(default_factory=Secrets)

    cfg = Auth()
    await cfg.activate()
    cfg.secrets.token = "hello-secret"
    await cfg.commit()
    stored = cfg.secrets.__dict__["token"]
    if not isinstance(stored, EncryptedValue):
        _fail("加密字段内存应为 EncryptedValue")
    if stored.ciphertext() == "hello-secret" or not stored.ciphertext().startswith("DPAPI:"):
        _fail("加密字段应存密文")
    if cfg.secrets.token != "hello-secret":
        _fail("加密字段读取应得明文")
    dumped = await cfg.to_dict(if_decrypt=False)
    if dumped["secrets"]["token"] == "hello-secret":
        _fail("默认导出应为密文")
    dumped_plain = await cfg.to_dict(if_decrypt=True)
    if dumped_plain["secrets"]["token"] != "hello-secret":
        _fail("if_decrypt=True 应导出明文")
    _ok("加密字段 encrypted() + EncryptedValue")


async def test_encrypted_validate_before_encrypt() -> None:
    def strip_min8(value: str) -> str:
        text = value.strip()
        if len(text) < 8:
            raise ValueError("密钥长度不足 8")
        return text

    class Secrets(ConfigGroup):
        token: Annotated[str, AfterValidator(strip_min8), encrypted()] = "default00"

    class Auth(ConfigEntry):
        secrets: Secrets = Field(default_factory=Secrets)

    cfg = Auth()
    await cfg.activate()
    cfg.secrets.token = "short"
    try:
        await cfg.commit()
        _fail("校验应在 commit 时拒绝过短明文")
    except ConfigAggregateError:
        pass
    cfg.secrets.token = "  hello-secret  "
    await cfg.commit()
    got_token = cast(str, cfg.secrets.token)
    if got_token != "hello-secret":
        _fail("校验纠正后应去空白")
    if not isinstance(cfg.secrets.__dict__["token"], EncryptedValue):
        _fail("校验通过后应加密存储")
    _ok("加密字段先校验后加密")


async def test_encrypted_same_plaintext_no_signal() -> None:
    received: list[tuple[Any, Any]] = []

    class Secrets(ConfigGroup):
        token: Annotated[str, encrypted()] = ""

    class Auth(ConfigEntry):
        secrets: Secrets = Field(default_factory=Secrets)

    cfg = Auth()
    await cfg.activate()

    async def slot(sender: object, event: FieldChangeEvent) -> None:
        received.append((event.old_value, event.value))

    cfg.connect(slot, phase="runtime", group="secrets", field="token")
    cfg.secrets.token = "same-secret"
    await cfg.commit()
    cfg.secrets.token = "same-secret"
    await cfg.commit()
    if len(received) != 1:
        _fail(f"相同明文重复赋值应只触发一次，实际 {len(received)}")
    _ok("加密字段明文比较变更检测")


async def test_encrypted_corrupt_ciphertext_returns_cipher() -> None:
    """设计固化：损坏密文 ``plaintext()`` 回退返回密文字符串，不抛 ValueError。"""
    broken = EncryptedValue("DPAPI:not-a-valid-payload")
    plain = broken.plaintext()
    if plain != "DPAPI:not-a-valid-payload":
        _fail(f"损坏密文应回退返回原串，实际 {plain!r}")
    _ok("损坏密文 plaintext 回退密文（设计）")


async def test_file_path_field() -> None:
    from app.config import FilePath

    class Paths(ConfigGroup):
        binary: FilePath = ""

    class Cfg(ConfigEntry):
        paths: Paths = Field(default_factory=Paths)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        file_path = root / "app.exe"
        file_path.write_text("x", encoding="utf-8")
        dir_path = root / "folder"
        dir_path.mkdir()
        expected = file_path.resolve().as_posix()

        cfg = Cfg()
        await cfg.activate()
        if cfg.paths.binary != "":
            _fail("default should be empty str")

        cfg.paths.binary = str(file_path)
        await cfg.commit()
        if cfg.paths.binary != expected:
            _fail(f"should resolve to abs file path str, got {cfg.paths.binary!r}")
        dumped = await cfg.to_dict()
        if dumped["paths"]["binary"] != expected:
            _fail(f"wire should be posix str, got {dumped['paths']['binary']!r}")

        cfg.paths.binary = str(dir_path)
        await cfg.commit()
        if cfg.paths.binary != "":
            _fail("directory should correct to empty str")

        cfg.paths.binary = str(root / "missing.exe")
        await cfg.commit()
        if cfg.paths.binary != "":
            _fail("missing path should correct to empty str")

        try:
            import win32com.client
        except ImportError:
            _ok("FilePath file validate (skip .lnk: no pywin32)")
            return
        lnk = root / "app.lnk"
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(lnk))
        shortcut.TargetPath = str(file_path.resolve())
        shortcut.Save()
        cfg.paths.binary = str(lnk)
        await cfg.commit()
        if cfg.paths.binary != expected:
            _fail(f".lnk should resolve to target file, got {cfg.paths.binary!r}")

        dir_lnk = root / "folder.lnk"
        shortcut = shell.CreateShortcut(str(dir_lnk))
        shortcut.TargetPath = str(dir_path.resolve())
        shortcut.Save()
        cfg.paths.binary = str(dir_lnk)
        await cfg.commit()
        if cfg.paths.binary != "":
            _fail(".lnk to directory should correct to empty str")

    _ok("FilePath file validate, .lnk resolve, wire dump")


async def test_ref_normalization() -> None:
    scripts = await _ensure_scripts()
    script_uid = scripts.add(ExampleScript)
    await scripts.commit()

    item = ExampleQueueItem()
    await item.activate()
    item.info.script_id = str(script_uid)
    await item.commit()
    if item.info.script_id != str(script_uid):
        _fail("ref 字段未归一化为有效 UUID")
    item.info.script_id = "not-a-uuid"
    await item.commit()
    got_script_id = cast(str, item.info.script_id)
    if got_script_id != "-":
        _fail("无效 ref 未回退 default")
    _ok("UUID ref 归一化")


async def test_ref_duplicate_rejected() -> None:
    from app.config import ConfigEntry, ConfigGroup
    from app.config.shortcuts import ref
    from pydantic import Field

    try:

        class Bad(ConfigEntry):  # pyright: ignore[reportUnusedClass]
            class Info(ConfigGroup):
                script_id: Annotated[
                    str,
                    ref("scripts"),
                    ref("others"),
                ] = "-"

            info: Info = Field(default_factory=Info)

    except TypeError as exc:
        if "只能声明一个 ref" not in str(exc):
            _fail(f"错误信息不符: {exc}")
        _ok("同一字段多个 ref 在类定义时拒绝")
        return
    _fail("同一字段多个 ref 应在类定义时抛 TypeError")


async def test_nested_collection_must_use_factory() -> None:
    try:

        class Bad(ConfigEntry):  # pyright: ignore[reportUnusedClass]
            class Info(ConfigGroup):
                name: str = "x"

            info: Info = Field(default_factory=Info)
            items: ConfigCollection[ExampleQueueItem] = Field(
                default_factory=lambda: ConfigCollection([ExampleQueueItem])
            )

    except TypeError as exc:
        if "collection()" not in str(exc):
            _fail(f"错误信息不符: {exc}")
        _ok("嵌套 Collection 非 collection() 声明在类定义时拒绝")
        return
    _fail("嵌套 Collection 非 collection() 应在类定义时抛 TypeError")


async def test_ref_on_delete_set_default() -> None:
    scripts = await _ensure_scripts()
    script_uid = scripts.add(ExampleScript)
    await scripts.commit()
    item = ExampleQueueItem()
    await item.activate()
    item.info.script_id = str(script_uid)
    await item.commit()
    if item.info.script_id != str(script_uid):
        _fail("ref 赋值失败")

    scripts.remove(script_uid)
    await scripts.commit()
    if item.info.script_id != "-":
        _fail(f"删除引用目标后 ref 应回退 default，实际 {item.info.script_id!r}")
    _ok("ref on_delete set_default")


async def test_ref_on_delete_cascade() -> None:
    scripts = await _ensure_scripts()
    script_uid = scripts.add(ExampleScript)
    await scripts.commit()

    class CascadeItem(ConfigEntry):
        class Info(ConfigGroup):
            script_id: Annotated[
                str,
                ref(
                    "scripts",
                    default="-",
                    allow_values=("-",),
                    on_delete=RefDeleteAction.CASCADE,
                ),
            ] = "-"

        info: Info = Field(default_factory=Info)

    items = ConfigCollection([CascadeItem])
    await items.activate()
    item_uid = items.add(
        CascadeItem, wire={"info": {"script_id": str(script_uid)}}
    )
    await items.commit()
    if item_uid not in items:
        _fail("CASCADE 成员应已加入 Collection")

    scripts.remove(script_uid)
    await scripts.commit()
    if item_uid in items:
        _fail("CASCADE 应经 Collection.remove 即时删除引用方成员")
    _ok("ref on_delete cascade")


async def test_same_collection_cascade() -> None:
    """P0：同集合 CASCADE 在 send 内嵌套 commit 办完；A、B 皆删，无重入报错。"""

    class Peer(ConfigEntry):
        class Info(ConfigGroup):
            peer_id: Annotated[
                str,
                ref(
                    "peers",
                    default="-",
                    allow_values=("-",),
                    on_delete=RefDeleteAction.CASCADE,
                ),
            ] = "-"

        info: Info = Field(default_factory=Info)

    peers = ConfigCollection([Peer], name="peers")
    await peers.activate()
    a_uid = peers.add(Peer)
    await peers.commit()
    b_uid = peers.add(Peer, wire={"info": {"peer_id": str(a_uid)}})
    await peers.commit()
    if a_uid not in peers or b_uid not in peers:
        _fail("同集合成员应已加入")

    peers.remove(a_uid)
    await peers.commit()
    if a_uid in peers:
        _fail("目标 A 应已删除")
    if b_uid in peers:
        _fail("CASCADE 引用方 B 应在同一信号链路内删除")
    if peers._staged_ops:
        _fail("级联办完后不应残留 stage")
    _ok("同集合 CASCADE 信号内办完")


async def test_failed_member_activate_reaches_active() -> None:
    """激活语义：集合 activate 中成员字段失败后，成员仍应跑完为 ACTIVE（非 INITIALIZING）。

    嵌套 init 使用独立 ctx：字段失败只回退内层壳，``ACTIVE`` 写在普通 ws 上。
    未挂入集合的实例可被 GC，不视为缺陷。
    """

    class Item(ConfigEntry):
        class Info(ConfigGroup):
            name: str = ""

        info: Info = Field(default_factory=Info)

    ok_uid = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    bad_uid = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    held: list[ConfigEntry] = []
    orig = Item.activate

    async def wrap(self: Item) -> None:
        try:
            await orig(self)
        except Exception:
            held.append(self)
            raise

    Item.activate = wrap  # type: ignore[method-assign]

    @Item.connect(phase="init", group="info", field="name")
    async def boom(sender: object, event: FieldChangeEvent) -> None:
        if event.node.uid == bad_uid:
            raise RuntimeError("member boom")

    try:
        col = ConfigCollection.build(
            [Item],
            wire={
                "order": [
                    {"uid": str(ok_uid), "type": "Item"},
                    {"uid": str(bad_uid), "type": "Item"},
                ],
                "data": {
                    str(ok_uid): {"info": {"name": "ok"}},
                    str(bad_uid): {"info": {"name": "bad"}},
                },
            },
        )
        try:
            await col.activate()
        except ConfigAggregateError:
            pass
        if not held:
            _fail("应捕获失败成员实例")
        member = held[0]
        if member.uid in col:
            _fail("字段失败的成员不应进入集合 data")
        if member.activation_state == NodeState.INITIALIZING:
            _fail("激活应跑完，不得停在 INITIALIZING")
        if member.activation_state != NodeState.ACTIVE:
            _fail(f"激活语义下成员应为 ACTIVE，实际 {member.activation_state}")
        _ok("失败成员激活语义：ACTIVE（未挂集合）")
    finally:
        Item.activate = orig  # type: ignore[method-assign]
        Item.disconnect(boom, phase="init", group="info", field="name")


async def test_commit_serializes_concurrent_stage() -> None:
    """节点 commit 可重入锁：其它 Task 的 stage 排队至锁释放，不受本批失败 clear 影响。"""

    class Info(ConfigGroup):
        a: str = ""
        b: str = ""
        c: str = ""

    class Item(ConfigEntry):
        info: Info = Field(default_factory=Info)

    item = Item()
    await item.activate()
    barrier = asyncio.Barrier(2)

    @Item.connect(phase="runtime", group="info", field="a")
    async def on_a(sender: object, event: FieldChangeEvent) -> None:
        await barrier.wait()
        await barrier.wait()

    @Item.connect(phase="runtime", group="info", field="b")
    async def boom(sender: object, event: FieldChangeEvent) -> None:
        raise RuntimeError("op b fail")

    async def commit_ab() -> None:
        item.info.a = "1"
        item.info.b = "2"
        await item.commit()

    async def stage_c() -> None:
        await barrier.wait()
        item.info.c = "3"  # 持锁期间入 pending，不报错
        await barrier.wait()

    try:
        results = await asyncio.gather(commit_ab(), stage_c(), return_exceptions=True)
        if not any(
            isinstance(r, ConfigAggregateError)
            or (isinstance(r, Exception) and "op b fail" in str(r))
            for r in results
        ):
            _fail(f"commit_ab 应因 b 失败而报错，实际 {results!r}")
        if not item._staged_ops:
            _fail("并发 stage 应在锁释放后并入队列")
        await item.commit()
        if item.info.c != "3":
            _fail(f"排队的 c 应可提交，实际 {item.info.c!r}")
        _ok("commit 串行化：并发 stage 排队等待")
    finally:
        Item.disconnect(on_a, phase="runtime", group="info", field="a")
        Item.disconnect(boom, phase="runtime", group="info", field="b")


async def test_forbid_same_node_nested_init_transaction() -> None:
    """禁止同节点在 init handler 内再 commit（重复开启 init 事务）。"""

    class Info(ConfigGroup):
        name: str = "cold"
        other: str = "keep"

    class Cfg(ConfigEntry):
        info: Info = Field(default_factory=Info)

    @Cfg.connect(phase="init", group="info", field="name")
    async def on_name(sender: object, event: FieldChangeEvent) -> None:
        node = cast(Cfg, event.node)
        node.info.other = "dirty"
        await node.commit()

    cfg = Cfg.build(wire={"info": {"name": "hot", "other": "keep"}})
    try:
        try:
            await cfg.activate()
            _fail("同节点嵌套 init 应失败")
        except ConfigAggregateError as exc:

            def _walk(errs: list[Exception]) -> bool:
                for e in errs:
                    if isinstance(e, RuntimeError) and "禁止同节点重复开启 init" in str(
                        e
                    ):
                        return True
                    if isinstance(e, ConfigAggregateError) and _walk(e.errors):
                        return True
                return False

            if not _walk(exc.errors):
                _fail(f"应含禁止同节点重复开启 init: {exc.errors}")
        if cfg.info.other == "dirty":
            _fail("不得脏写 other")
        if cfg.info.other != "keep":
            _fail(f"other 应保持先验 keep，实际 {cfg.info.other!r}")
        if cfg.info.name != "cold":
            _fail(f"外层应回滚 name，实际 {cfg.info.name!r}")
        _ok("禁止同节点重复开启 init 事务")
    finally:
        Cfg.disconnect(on_name, phase="init", group="info", field="name")


async def test_commit_discards_residual_init_shell_before_merge() -> None:
    """回归：残留 init 壳不得并入 live；普通 ws 仍合并（现状：``_workspace=None`` 一并丢弃嵌套）。"""
    from app.config.core.manager import config_manager

    class Info(ConfigGroup):
        name: str = "live"
        tag: str = "L"

    class Cfg(ConfigEntry):
        info: Info = Field(default_factory=Info)

    cfg = Cfg()
    await cfg.activate()
    async with config_manager.transaction():
        cfg._build_workspace()
        object.__setattr__(cfg._workspace.info, "tag", "ord")  # type: ignore[union-attr]
        async with config_manager.init_transaction():
            cfg._build_init_workspace()
            init = cfg.init_workspace
            assert init is not None
            object.__setattr__(init.info, "name", "only-in-init")
            ctx = config_manager._current_init_ctx()
            assert ctx is not None
            ctx.registered.clear()
    if cfg.info.name == "only-in-init":
        _fail("残留 init 壳上的 name 不得并入 live")
    if cfg.info.tag != "ord":
        _fail(f"普通 ws 的 tag 应合并，实际 {cfg.info.tag!r}")
    if cfg._workspace is not None:
        _fail("COMMIT 后不应残留 workspace")
    _ok("_COMMIT 丢弃残留 init 壳且合并普通 ws")


async def test_set_default_auto_commit_flushes_other_stages() -> None:
    """逻辑审查：SET_DEFAULT 自动 commit 会提交同 Entry 上其它已 stage 字段。

    规格将此视为节点级队列的自然结果；本测试固化现状。若改为「只交 ref 那一条」才需改实现。
    """
    scripts = await _ensure_scripts()
    script_uid = scripts.add(ExampleScript)
    await scripts.commit()

    class Item(ConfigEntry):
        class Info(ConfigGroup):
            script_id: Annotated[
                str,
                ref(
                    "scripts",
                    default="-",
                    allow_values=("-",),
                    on_delete=RefDeleteAction.SET_DEFAULT,
                ),
            ] = "-"
            label: str = "keep"

        info: Info = Field(default_factory=Info)

    item = Item()
    await item.activate()
    item.info.script_id = str(script_uid)
    await item.commit()
    item.info.label = "should-stay-staged"
    if not item._staged_ops:
        _fail("label 应已 stage")
    scripts.remove(script_uid)
    await scripts.commit()
    if item.info.script_id != "-":
        _fail("SET_DEFAULT 应将 script_id 置 default")
    if item.info.label != "should-stay-staged":
        _fail(f"label 应随自动 commit 落盘，实际 {item.info.label!r}")
    if item._staged_ops:
        _fail("自动 commit 后不应残留 stage")
    _ok("SET_DEFAULT 自动 commit 冲同节点其它 stage（现状；改语义才需修）")


async def test_signal_must_commit_staged_ops() -> None:
    """信号回调只 stage 不 commit → 事务内判空失败并 ROLLBACK 本笔 op。"""
    col = ConfigCollection([ExampleScript])
    await col.activate()
    keep = col.add(ExampleScript)
    doomed = col.add(ExampleScript)
    await col.commit()

    @ConfigCollection.connect(phase="runtime")
    async def leak_stage(sender: object, event: CollectionChangeEvent) -> None:
        if event.kind != "remove" or event.uid != doomed:
            return
        cast(ConfigCollection[ExampleScript], sender).remove(keep)  # 只 stage，不 commit

    try:
        col.remove(doomed)
        try:
            await col.commit()
            _fail("只 stage 不 commit 应失败")
        except ConfigAggregateError as exc:
            if not any("须在返回前 commit" in str(e) for e in exc.errors):
                _fail(f"应含 stage 残留错误: {exc.errors}")
        if doomed not in col:
            _fail("事务内判空失败应 ROLLBACK，doomed 应仍在集合中")
        if keep not in col:
            _fail("未 commit 的 keep 删除不应落盘")
    finally:
        ConfigCollection.disconnect(leak_stage, phase="runtime")
    _ok("信号须 commit 当次 stage")


async def test_ref_on_delete_cascade_rejects_non_member() -> None:
    await _ensure_scripts()

    class CascadeRoot(ConfigEntry):
        class Info(ConfigGroup):
            script_id: Annotated[
                str,
                ref(
                    "scripts",
                    default="-",
                    allow_values=("-",),
                    on_delete=RefDeleteAction.CASCADE,
                ),
            ] = "-"

        info: Info = Field(default_factory=Info)

    root = CascadeRoot()
    try:
        await root.activate()
        _fail("非 Collection 成员使用 CASCADE 应在 activate 时失败")
    except ConfigAggregateError as exc:
        if not any(isinstance(e, TypeError) and "CASCADE" in str(e) for e in exc.errors):
            _fail(f"聚合错误应含 CASCADE TypeError: {exc.errors}")
    _ok("ref on_delete cascade 拒绝非 Collection 成员")


async def test_ref_on_delete_restrict() -> None:
    restrict_scripts = ConfigCollection([ExampleScript], name="scripts_restrict")
    await restrict_scripts.activate()

    class RestrictItem(ConfigEntry):
        class Info(ConfigGroup):
            script_id: Annotated[
                str,
                ref(
                    "scripts_restrict",
                    default="-",
                    allow_values=("-",),
                    on_delete=RefDeleteAction.RESTRICT,
                ),
            ] = "-"

        info: Info = Field(default_factory=Info)

    script_uid = restrict_scripts.add(ExampleScript)
    await restrict_scripts.commit()
    item = RestrictItem()
    await item.activate()
    item.info.script_id = str(script_uid)
    await item.commit()

    restrict_scripts.remove(script_uid)
    try:
        await restrict_scripts.commit()
        _fail("restrict 策略应阻止删除并返回 commit 错误")
    except ConfigAggregateError:
        pass
    if script_uid not in restrict_scripts:
        _fail("restrict 阻止删除后实例应仍存在")
    _ok("ref on_delete restrict")


async def test_virtual_field() -> None:
    script = ExampleScript()
    await script.activate()
    script.info.name = "有名字"
    await script.commit()
    if script.info.status != "enabled":
        _fail(f"虚拟字段计算错误: {script.info.status}")
    _ok("虚拟字段")


async def test_trigger_field() -> None:
    class TriggerExample(ConfigEntry):
        class Info(ConfigGroup):
            name: str = ""
            run: Trigger = False

        info: Info = Field(default_factory=Info)
        runs: int = 0

        @trigger_field("info.run")
        def on_run(self) -> None:
            self.runs += 1

    cfg = TriggerExample()
    await cfg.activate()
    if cfg.info.run is not False:
        _fail("触发器常态应为 False")
    cfg.info.run = True
    got_run = cast(bool, cfg.info.run)
    if got_run is not False:
        _fail("触发器执行后应复位 False")
    if cfg.runs != 1:
        _fail(f"触发器 handler 未执行: runs={cfg.runs}")
    cfg.info.run = False
    if cfg.runs != 1:
        _fail("触发器赋 False 不应重复执行")
    cold = TriggerExample.model_validate({"info": {"name": "", "run": True}})
    await cfg.update(cold)
    if cfg.runs != 2:
        _fail(f"update 应能触发触发器: runs={cfg.runs}")
    exported = await cfg.to_dict()
    if "run" in exported.get("info", {}):
        _fail("默认 to_dict 不应含响应式触发器字段")
    api = cfg.model_dump()
    if api["info"].get("run") is not False:
        _fail(f"model_dump 应携带触发器为 False: {api['info'].get('run')}")
    with_reactive = await cfg.to_dict(include_reactive=True)
    if with_reactive["info"].get("run") is not False:
        _fail("to_dict(include_reactive=True) 应含触发器")
    _ok("触发器字段")


async def test_reactive_unbound_raises() -> None:
    class OrphanInfo(ConfigGroup):
        status: Virtual[str] = None
        run: Trigger = False

    info = OrphanInfo()
    try:
        _ = info.status
        _fail("未绑定应拒绝读虚拟字段")
    except RuntimeError:
        pass
    try:
        info.run = True
        _fail("未绑定应拒绝写触发器")
    except RuntimeError:
        pass
    _ok("未绑定响应式字段报错")


async def test_lock() -> None:
    cfg = ExampleWebhook()
    await cfg.activate()
    await cfg.lock()
    try:
        cfg.info.name = "locked"
        _fail("锁定后赋值应失败")
    except ValueError:
        pass
    await cfg.unlock()
    cfg.info.name = "unlocked"
    await cfg.commit()
    if cfg.info.name != "unlocked":
        _fail("解锁后赋值失败")

    # 已 stage 后加锁：commit 入口拒绝，且不清空 stage
    before = cfg.info.name
    cfg.info.name = "staged-then-locked"
    await cfg.lock()
    try:
        await cfg.commit()
        _fail("锁定后 commit 应拒绝已暂存字段写")
    except ValueError:
        pass
    got_name = cast(str, cfg.info.name)
    if got_name != before:
        _fail("锁定拒绝 commit 后字段不应落盘")
    await cfg.unlock()
    await cfg.commit()
    if cfg.info.name != "staged-then-locked":
        _fail("解锁后应能提交先前暂存")
    _ok("配置锁定")


async def test_commit_cancelled_restores_batch() -> None:
    """CancelledError 中断 commit 时 batch 未排空 → 归还 stage，可再次 commit。"""
    cfg = ExampleWebhook()
    await cfg.activate()
    cfg.info.name = "pending"
    orig = type(cfg)._commit_op

    async def boom(self: object, op: object) -> None:
        raise asyncio.CancelledError()

    type(cfg)._commit_op = boom  # type: ignore[method-assign]
    try:
        try:
            await cfg.commit()
            _fail("应抛出 CancelledError")
        except asyncio.CancelledError:
            pass
    finally:
        type(cfg)._commit_op = orig  # type: ignore[method-assign]
    if not cfg._staged_ops:
        _fail("Cancel 中断时 batch 未排空应归还 stage")
    await cfg.commit()
    if cfg.info.name != "pending":
        _fail(f"再次 commit 应落盘，实际 name={cfg.info.name!r}")
    _ok("commit Cancel 后归还 batch 并可重试")


async def test_collection_lock_blocks_commit() -> None:
    col = ConfigCollection([ExampleScript])
    await col.activate()
    uid = col.add(ExampleScript)
    await col.lock()
    try:
        await col.commit()
        _fail("锁定后 Collection.commit 应拒绝")
    except ValueError:
        pass
    if uid in col:
        _fail("锁定拒绝 commit 后成员不应落盘")
    await col.unlock()
    await col.commit()
    if uid not in col:
        _fail("解锁后应能提交先前暂存的 add")
    _ok("Collection 锁定阻止 commit")


async def test_add_rejects_undeclared_type() -> None:
    col = ConfigCollection([ExampleScript])
    await col.activate()
    try:
        col.add(cast(Any, ExampleWebhook))
        _fail("未声明类型应在 add 时拒绝")
    except ValueError as exc:
        if "不支持的 Entry 类型" not in str(exc):
            _fail(f"错误信息应含不支持的类型: {exc}")

    try:
        col.add("ExampleWebhook")
        _fail("未声明类型名 str 应在 add 时拒绝")
    except ValueError as exc:
        if "不支持的 Entry 类型" not in str(exc):
            _fail(f"str 查找失败应报不支持: {exc}")

    uid = col.add("ExampleScript")
    await col.commit()
    if uid not in col:
        _fail("add 按类名 str 应成功")

    # Wire：type 必填；即使集合仅有单一类型也不可省略
    member_uid = uuid.uuid4()
    cold_ok = ConfigCollection(
        [ExampleScript],
        wire={
            "order": [{"uid": str(member_uid), "type": "ExampleScript"}],
            "data": {str(member_uid): {"info": {"name": "from-wire"}}},
        },
    )
    await cold_ok.activate()
    if member_uid not in cold_ok or cold_ok[member_uid].info.name != "from-wire":
        _fail("Wire 热化成员异常")

    missing_type_uid = uuid.uuid4()
    cold_bad = ConfigCollection(
        [ExampleScript],
        wire={
            "order": [{"uid": str(missing_type_uid)}],
            "data": {str(missing_type_uid): {"info": {"name": "x"}}},
        },
    )
    try:
        await cold_bad.activate()
        _fail("缺少 order[].type 应报错（不可因唯一类型省略）")
    except Exception:
        pass
    _ok("add 支持 type/str；Wire type 必填")


async def test_collection_persistence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "queue.toml"
        root = ConfigCollection.build([ExampleQueue], file=path)
        await root.activate()

        uid = root.add(ExampleQueue)
        await root.commit()
        queue = root[uid]
        queue.info.name = "持久化队列"
        _item_uid = queue.items.add(ExampleQueueItem)
        await queue.commit()
        await queue.items.commit()
        await config_manager.flush()

        reloaded = ConfigCollection.build([ExampleQueue], file=path)
        await reloaded.activate()
        if uid not in reloaded:
            _fail("Collection 持久化后实例丢失")
        if reloaded[uid].info.name != "持久化队列":
            _fail("Collection 持久化后字段错误")
        if len(reloaded[uid].items) != 1:
            _fail("嵌套 Collection 持久化丢失")
    _ok("ConfigCollection 持久化（含嵌套）")


async def test_set_order_permutation_and_signal() -> None:
    col = ConfigCollection([ExampleScript])
    await col.activate()
    u1 = col.add(ExampleScript)
    u2 = col.add(ExampleScript)
    u3 = col.add(ExampleScript)
    await col.commit()

    seen: list[tuple[list[UUID], list[UUID]]] = []

    @ConfigCollection.connect(phase="runtime")
    async def on_reorder(sender: object, event: CollectionChangeEvent) -> None:
        if event.kind != "set_order" or sender is not col:
            return
        assert event.old_order is not None and event.order is not None
        seen.append(
            ([i.uid for i in event.old_order], [i.uid for i in event.order])
        )

    col.set_order([u3, u1, u2])
    await col.commit()
    if [i.uid for i in col.order] != [u3, u1, u2]:
        _fail(f"order 未按 uuid 重排: {col.order}")
    if not seen or seen[-1] != ([u1, u2, u3], [u3, u1, u2]):
        _fail(f"set_order 信号应含新旧 order，实际 {seen}")

    # 校验在 commit 执行 op 时：缺损 / 多余 → ConfigAggregateError
    col.set_order([u1, u2])
    try:
        await col.commit()
        _fail("缺损 uuid 应在 commit 时拒绝")
    except ConfigAggregateError as exc:
        if not any("成员一致" in str(e) for e in exc.errors):
            _fail(f"缺损 uuid 应在 commit 时拒绝: {exc.errors}")
    if col._staged_ops:
        _fail("校验失败后 stage 应已清空")
    if [i.uid for i in col.order] != [u3, u1, u2]:
        _fail("校验失败后 order 不应被改写")

    col.set_order([u1, u2, u3, uuid.uuid4()])
    try:
        await col.commit()
        _fail("多余 uuid 应在 commit 时拒绝")
    except ConfigAggregateError as exc:
        if not any("成员一致" in str(e) for e in exc.errors):
            _fail(f"多余 uuid 应在 commit 时拒绝: {exc.errors}")
    if col._staged_ops:
        _fail("校验失败后 stage 应已清空")

    # 同批：先 remove 再 set_order（相对 remove 后的成员集）
    col.remove(u3)
    col.set_order([u2, u1])
    await col.commit()
    if [i.uid for i in col.order] != [u2, u1]:
        _fail(f"同批后 order 异常: {[i.uid for i in col.order]}")
    if u3 in col:
        _fail("同批 remove 后 u3 应已不在集合中")

    ConfigCollection.disconnect(on_reorder, phase="runtime")
    _ok("set_order 重排校验（op 内）与新旧 order 信号")


async def test_observable_auto_save() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "autosave.toml"
        cfg = ExampleWebhook.build(file=path)
        await cfg.activate()
        cfg.info.name = "随改随存"
        await cfg.commit()
        await config_manager.flush()
        if not path.exists() or path.stat().st_size == 0:
            _fail("随改随存未写入文件")
        if "随改随存" not in path.read_text(encoding="utf-8"):
            _fail("随改随存内容未落盘")
    _ok("Observable 随改随存")


async def test_runtime_field_signal() -> None:
    received: list[str] = []

    class Info(ConfigGroup):
        name: str = ""

    class Cfg(ConfigEntry):
        info: Info = Field(default_factory=Info)

    cfg = Cfg()
    await cfg.activate()

    async def slot(sender: object, event: FieldChangeEvent) -> None:
        received.append(str(event.value))

    cfg.connect(slot, phase="runtime", group="info", field="name")
    cfg.info.name = "bind-test"
    await cfg.commit()
    if received != ["bind-test"]:
        _fail(f"运行时字段信号未收到: {received}")
    _ok("运行时字段信号")


async def test_init_field_signal() -> None:
    received: list[str] = []

    class Info(ConfigGroup):
        name: str = "默认"
        enabled: bool = True

    class Cfg(ConfigEntry):
        info: Info = Field(default_factory=Info)

    async def slot(sender: object, event: FieldChangeEvent) -> None:
        received.append(f"{event.group}.{event.field}")

    Cfg.connect(slot, phase="init", group="info", field="name")
    Cfg.connect(slot, phase="init", group="info", field="enabled")

    cfg = Cfg.model_validate({"info": {"name": "示例", "enabled": True}})
    await cfg.activate()
    if set(received) != {"info.name", "info.enabled"}:
        _fail(f"首次 load 应对 data 内字段发 init 信号，实际 {received}")
    _ok("首次 load 发 init 信号")


async def test_entry_update() -> None:
    received: list[str] = []

    class Info(ConfigGroup):
        name: str = ""
        enabled: bool = True

    class Cfg(ConfigEntry):
        info: Info = Field(default_factory=Info)

    cfg = Cfg()
    await cfg.activate()

    async def slot(sender: object, event: FieldChangeEvent) -> None:
        received.append(f"{event.group}.{event.field}")

    cfg.connect(slot, phase="runtime", group="info", field="name")
    cold = Cfg.model_validate({"info": {"name": "更新", "enabled": False}})
    await cfg.update(cold)
    if cfg.info.name != "更新" or cfg.info.enabled is not False:
        _fail("update 未生效")
    received.clear()
    await cfg.update(Cfg.model_validate({"info": {"name": "更新", "enabled": False}}))
    if received:
        _fail(f"相同值 update 不应触发信号: {received}")
    _ok("entry.update 批量更新与变更检测")


async def test_disconnect_by_subscription_key() -> None:
    received_name: list[str] = []
    received_enabled: list[str] = []

    class Info(ConfigGroup):
        name: str = ""
        enabled: bool = True

    class Cfg(ConfigEntry):
        info: Info = Field(default_factory=Info)

    _reset_signal(Cfg)
    cfg = Cfg()
    await cfg.activate()

    async def slot(sender: object, event: FieldChangeEvent) -> None:
        if event.field == "name":
            received_name.append(str(event.value))
        elif event.field == "enabled":
            received_enabled.append(str(event.value))

    cfg.connect(slot, phase="runtime", group="info", field="name")
    cfg.connect(slot, phase="runtime", group="info", field="enabled")
    cfg.info.name = "a"
    cfg.info.enabled = False
    await cfg.commit()
    if received_name != ["a"] or received_enabled != ["False"]:
        _fail(f"双字段订阅应各自触发: name={received_name}, enabled={received_enabled}")

    cfg.disconnect(slot, phase="runtime", group="info", field="name")
    received_name.clear()
    received_enabled.clear()
    cfg.info.name = "b"
    cfg.info.enabled = True
    await cfg.commit()
    if received_name:
        _fail(f"disconnect name 后不应再收到 name 信号: {received_name}")
    if received_enabled != ["True"]:
        _fail(f"disconnect name 后 enabled 仍应触发: {received_enabled}")

    cfg.disconnect(slot, phase="runtime", group="info", field="enabled")
    received_enabled.clear()
    cfg.info.enabled = False
    await cfg.commit()
    if received_enabled:
        _fail(f"disconnect enabled 后不应再收到 enabled 信号: {received_enabled}")
    _ok("disconnect 按 (phase, group, field, sender) 精确解绑")


async def main() -> int:
    tests = [
        test_entry_init_with_data,
        test_toml_roundtrip,
        test_missing_toml_returns_default,
        test_rejects_non_toml_path,
        test_collection_init_with_data,
        test_add_member_is_active,
        test_add_duplicate_uid_rejected,
        test_entry_type_name_collision,
        test_connect_reuse_wrapper_after_disconnect,
        test_ref_missing_target_raises,
        test_activate_collects_all_field_errors,
        test_activate_pending_survives_outer_rollback,
        test_activate_init_handler_failure_keeps_prior,
        test_activate_init_add_handler_failure_keeps_prior,
        test_init_add_failure_orphan_entry_may_reach_active,
        test_partial_ref_connect_leaves_active_without_retry_activate,
        test_encrypted_field,
        test_encrypted_validate_before_encrypt,
        test_encrypted_same_plaintext_no_signal,
        test_encrypted_corrupt_ciphertext_returns_cipher,
        test_file_path_field,
        test_ref_normalization,
        test_ref_duplicate_rejected,
        test_nested_collection_must_use_factory,
        test_ref_on_delete_set_default,
        test_ref_on_delete_cascade,
        test_same_collection_cascade,
        test_signal_must_commit_staged_ops,
        test_failed_member_activate_reaches_active,
        test_commit_serializes_concurrent_stage,
        test_forbid_same_node_nested_init_transaction,
        test_commit_discards_residual_init_shell_before_merge,
        test_set_default_auto_commit_flushes_other_stages,
        test_ref_on_delete_cascade_rejects_non_member,
        test_ref_on_delete_restrict,
        test_virtual_field,
        test_trigger_field,
        test_reactive_unbound_raises,
        test_lock,
        test_commit_cancelled_restores_batch,
        test_collection_lock_blocks_commit,
        test_add_rejects_undeclared_type,
        test_collection_persistence,
        test_set_order_permutation_and_signal,
        test_observable_auto_save,
        test_runtime_field_signal,
        test_init_field_signal,
        test_entry_update,
        test_disconnect_by_subscription_key,
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
