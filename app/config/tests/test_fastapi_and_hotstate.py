"""配置基类 v2：FastAPI 字段提示导出 + 热态校验边界场景检查。

覆盖两类目标：

1. 作为 FastAPI ``response_model`` / ``Body`` 时能否正常导出字段提示
   （OpenAPI schema 嵌套 Group/Entry 字段），以及冷态 ``model_validate``
   → ``activate`` 的热化链路。
2. 热态数据校验的边界场景：拒绝并回滚、自动纠正、数值边界、批量 update
   局部错误、锁定与删除守卫。

用法（仓库根目录）::

    python -m app.config.tests.test_fastapi_and_hotstate
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, cast
from uuid import UUID

from blinker import Signal
from fastapi import Body, FastAPI
from fastapi.testclient import TestClient
from pydantic import Field

from app.config import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    FieldChangeEvent,
    NodeState,
    config_manager,
)
from app.config.errors import (
    ConfigAggregateError,
    DeletedNodeError,
)
from app.config.examples.reference_config import ExampleWebhook
from app.config.types import HHMMString


def _fail(message: str) -> None:
    raise AssertionError(message)


def _ok(message: str) -> None:
    print(f"OK: {message}")


def _reset_signal(cls: type) -> None:
    cls.signal = Signal()


# ──────────────── 类型化集合（FastAPI 字段提示） ────────────────


class WebhookCollection(ConfigCollection[ExampleWebhook]):
    """类型化集合子类：data 标注具体 Entry 类型，供 OpenAPI 导出字段提示。"""

    _default_entry_types = (ExampleWebhook,)
    data: dict[UUID, ExampleWebhook] = Field(default_factory=dict)


# ════════════════════ FastAPI / Schema 导出 ════════════════════


async def test_entry_json_schema_field_hints() -> None:
    schema = ExampleWebhook.model_json_schema()
    props = schema.get("properties", {})
    if set(props) != {"ui", "info", "data"}:
        _fail(f"Entry 顶层字段应为 ui/info/data，实际 {list(props)}")
    defs = schema.get("$defs", {})
    if "Info" not in defs or "Data" not in defs:
        _fail("应导出嵌套 Info/Data 定义")
    data_props = defs["Data"].get("properties", {})
    if "url" not in data_props or "method" not in data_props:
        _fail("Data 字段提示缺失")
    if data_props["method"].get("enum") != ["POST", "GET"]:
        _fail("Literal 字段应导出 enum 提示")
    _ok("Entry JSON Schema 导出嵌套字段提示")


async def test_collection_json_schema_field_hints() -> None:
    schema = WebhookCollection.model_json_schema()
    props = schema.get("properties", {})
    if set(props) != {"order", "data"}:
        _fail(f"Collection 顶层字段应为 order/data，实际 {list(props)}")
    data_schema = props["data"]
    add = data_schema.get("additionalProperties", {})
    if "$ref" not in add or not add["$ref"].endswith("ExampleWebhook"):
        _fail("类型化集合 data 应引用 Entry schema，导出成员字段提示")
    _ok("类型化 Collection JSON Schema 导出成员字段提示")


async def test_fastapi_entry_roundtrip() -> None:
    app = FastAPI()

    @app.post("/echo", response_model=ExampleWebhook)
    def echo(payload: ExampleWebhook = Body(...)) -> ExampleWebhook:
        return payload

    _ = (echo,)

    client = TestClient(app)

    schema = client.get("/openapi.json").json()
    comps = schema["components"]["schemas"]
    if not any(name.startswith("ExampleWebhook") for name in comps):
        _fail(f"OpenAPI 应包含 Entry schema，实际 {list(comps)}")
    if "Data" not in comps or "Info" not in comps:
        _fail(f"OpenAPI 应包含嵌套 Group schema，实际 {list(comps)}")

    body = {
        "info": {"name": "hi", "enabled": False},
        "data": {"url": "https://e.com", "method": "GET"},
    }
    resp = client.post("/echo", json=body)
    if resp.status_code != 200:
        _fail(f"合法 Body 应 200，实际 {resp.status_code}: {resp.text}")
    payload = resp.json()
    payload.pop("ui", None)  # 虚拟字段由 model_dump 展开；TypeAdapter 路径不保证
    if payload != body:
        _fail(f"往返业务字段不一致: {payload}")
    _ok("FastAPI Entry 往返（Body/response_model）")


async def test_fastapi_invalid_body_rejected() -> None:
    app = FastAPI()

    @app.post("/echo", response_model=ExampleWebhook)
    def echo(payload: ExampleWebhook = Body(...)) -> ExampleWebhook:
        return payload

    _ = (echo,)

    client = TestClient(app)
    # method 非法 Literal + url 非法 → 边界拒绝
    bad = {"info": {"name": "x"}, "data": {"url": "https://e.com", "method": "PUT"}}
    resp = client.post("/echo", json=bad)
    if resp.status_code != 422:
        _fail(f"非法 Body 应 422，实际 {resp.status_code}")
    _ok("FastAPI 非法 Body 在边界被 422 拒绝")


async def test_fastapi_collection_export() -> None:
    col = WebhookCollection()
    await col.activate()
    col.add(
        ExampleWebhook, wire={"info": {"name": "w1"}, "data": {"url": "https://a.b"}}
    )
    await col.commit()

    app = FastAPI()

    @app.get("/col", response_model=WebhookCollection)
    def get_col() -> WebhookCollection:
        return col

    _ = (get_col,)

    client = TestClient(app)
    resp = client.get("/col")
    if resp.status_code != 200:
        _fail(f"集合响应应 200，实际 {resp.status_code}: {resp.text}")
    payload = resp.json()
    if set(payload) != {"order", "data"}:
        _fail(f"集合 Wire 顶层应为 order/data，实际 {list(payload)}")
    if len(payload["order"]) != 1 or payload["order"][0]["type"] != "ExampleWebhook":
        _fail("集合 order 导出异常")
    only = next(iter(payload["data"].values()))
    if only["info"]["name"] != "w1" or only["data"]["url"] != "https://a.b":
        _fail(f"集合成员 Wire 导出异常: {only}")
    _ok("FastAPI 类型化 Collection 导出 Wire 文档")


# ════════════════════ 冷态 → 热态链路 ════════════════════


async def test_cold_validate_populates_groups() -> None:
    e = ExampleWebhook.model_validate(
        {
            "info": {"name": "A", "enabled": False},
            "data": {"url": "https://x.com", "method": "GET"},
        }
    )
    if e.activation_state != NodeState.INACTIVE:
        _fail("model_validate 产物应为未激活态")
    dumped = e.model_dump()
    expect = {
        "info": {"name": "A", "enabled": False},
        "data": {"url": "https://x.com", "method": "GET"},
    }
    ui_block = dumped.pop("ui", None)
    if dumped != expect:
        _fail(f"冷态导出与输入不一致: {dumped}")
    if not isinstance((ui_block or {}).get("hints"), dict):
        _fail(f"冷态 model_dump 应携带 ui.hints: {ui_block}")
    await e.activate()
    if e.activation_state != NodeState.ACTIVE:
        _fail("activate 后应为激活态")
    if e.data.url != "https://x.com" or e.data.method != "GET" or e.info.name != "A":
        _fail("热化后字段值丢失")
    _ok("冷态 model_validate 填充全部分组并热化")


async def test_cold_load_activates_all_fields_including_defaults() -> None:
    received: list[str] = []

    class Info(ConfigGroup):
        name: str = ""
        enabled: bool = True

    class Cfg(ConfigEntry):
        info: Info = Field(default_factory=Info)

    _reset_signal(Cfg)

    async def slot(sender: object, event: FieldChangeEvent) -> None:
        received.append(f"{event.group}.{event.field}")

    Cfg.connect(slot, phase="init", group="info", field="name")
    Cfg.connect(slot, phase="init", group="info", field="enabled")

    # 仅显式提供 name；enabled 为默认值，activate 仍应对二者发 init_set
    cfg = Cfg.model_validate({"info": {"name": "仅名字"}})
    await cfg.activate()
    if set(received) != {"info.name", "info.enabled"}:
        _fail(f"应对全部持久化字段发 init 信号，实际 {received}")
    _ok("冷态热化对全部字段发 init_set（含默认值）")


# ════════════════════ 热态校验边界场景 ════════════════════


async def test_hot_reject_invalid_url_rollback() -> None:
    e = ExampleWebhook()
    await e.activate()
    e.data.url = "https://ok.com"
    await e.commit()
    e.data.url = "not-a-url"
    try:
        await e.commit()
        _fail("非法 URL 应在 commit 时被拒绝")
    except ConfigAggregateError:
        pass
    got_url = cast(str, e.data.url)
    if got_url != "https://ok.com":
        _fail(f"拒绝后应回滚到旧值，实际 {e.data.url!r}")
    _ok("热态非法 URL 拒绝并回滚")


async def test_hot_reject_invalid_literal_rollback() -> None:
    e = ExampleWebhook()
    await e.activate()
    e.data.method = "GET"
    await e.commit()
    e.data.method = cast(Any, "PUT")  # 故意注入非法 Literal，测 commit 拒绝
    try:
        await e.commit()
        _fail("非法 Literal 应在 commit 时被拒绝")
    except ConfigAggregateError:
        pass
    if e.data.method != "GET":
        _fail(f"拒绝后 Literal 应回滚，实际 {e.data.method!r}")
    _ok("热态非法 Literal 拒绝并回滚")


async def test_hot_autocorrect_field() -> None:
    class G(ConfigGroup):
        t: HHMMString = "08:00"

    class Cfg(ConfigEntry):
        g: G = Field(default_factory=G)

    cfg = Cfg()
    await cfg.activate()
    cfg.g.t = "25:99"  # 非法时刻 → 自动纠正为默认
    await cfg.commit()
    got_t = cast(str, cfg.g.t)
    if got_t != "00:00":
        _fail(f"非法时刻应自动纠正为默认，实际 {cfg.g.t!r}")
    cfg.g.t = "09:30"
    await cfg.commit()
    if cfg.g.t != "09:30":
        _fail("合法时刻应保留")
    _ok("热态纠正型字段自动回退默认")


async def test_hot_numeric_bounds() -> None:
    class G(ConfigGroup):
        n: Annotated[int, Field(ge=0)] = 0
        p: Annotated[int, Field(ge=1)] = 1

    class Cfg(ConfigEntry):
        g: G = Field(default_factory=G)

    cfg = Cfg()
    await cfg.activate()
    cfg.g.n = -1
    try:
        await cfg.commit()
        _fail("ge=0 字段应在 commit 时拒绝负值")
    except ConfigAggregateError:
        pass
    got_n = cast(int, cfg.g.n)
    if got_n != 0:
        _fail("拒绝后应回滚")
    cfg.g.p = 0
    try:
        await cfg.commit()
        _fail("ge=1 字段应在 commit 时拒绝 0")
    except ConfigAggregateError:
        pass
    cfg.g.n = 7
    cfg.g.p = 3
    await cfg.commit()
    if cfg.g.n != 7 or cfg.g.p != 3:
        _fail("合法数值应生效")
    _ok("热态数值边界校验")


async def test_hot_update_partial_errors() -> None:
    e = ExampleWebhook()
    await e.activate()
    cold = ExampleWebhook.model_validate(
        {
            "info": {"name": "示例 Webhook", "enabled": True},
            "data": {"url": "https://good.com", "method": "GET"},
        }
    )
    # 绕过冷态校验，注入热态才会失败的非法 Literal
    # runtime 为 dict；部分 pydantic stubs 将 __dict__ 标为 MappingProxyType
    cast(dict[str, Any], cold.data.__dict__)["method"] = "PATCH"
    try:
        await e.update(cold)
        _fail("非法 method 应抛 ConfigAggregateError")
    except ConfigAggregateError as exc:
        if not any("method" in str(err) for err in exc.errors):
            _fail(f"ConfigAggregateError 应含 method 错误，实际 {exc.errors}")
    if e.data.url != "https://good.com":
        _fail("update 中合法字段应已生效")
    if e.data.method != "POST":
        _fail("非法字段应保持原值")
    _ok("热态批量 update 局部错误隔离")


async def test_hot_update_skips_unset_fields() -> None:
    """未出现在 Body / model_fields_set 的字段不得被默认值覆盖。"""
    e = ExampleWebhook()
    await e.activate()
    e.info.name = "keep-name"
    e.info.enabled = False
    e.data.url = "https://keep.example"
    e.data.method = "GET"
    await e.commit()

    await e.update(ExampleWebhook.model_validate({"info": {"name": "only-name"}}))
    if e.info.name != "only-name":
        _fail("已赋值 name 应更新")
    if e.info.enabled is not False:
        _fail("未赋值 enabled 应保持 False，不得被默认 True 覆盖")
    if e.data.url != "https://keep.example" or e.data.method != "GET":
        _fail("未赋值的 data Group 应整组跳过")
    _ok("update 跳过未赋值字段")


async def test_fastapi_update_from_body() -> None:
    """Body 冷态实例直接 update 热态 cfg，成功返回；校验失败可回报。"""
    hot = ExampleWebhook()
    await hot.activate()

    app = FastAPI()

    @app.put("/webhook", response_model=ExampleWebhook)
    async def put_webhook(body: ExampleWebhook = Body(...)) -> ExampleWebhook:
        await hot.update(body)
        return hot

    _ = (put_webhook,)

    client = TestClient(app)
    body = {
        "info": {"name": "from-api", "enabled": False},
        "data": {"url": "https://api.example", "method": "GET"},
    }
    resp = client.put("/webhook", json=body)
    if resp.status_code != 200:
        _fail(f"合法 Body update 应 200，实际 {resp.status_code}: {resp.text}")
    if hot.info.name != "from-api" or hot.data.method != "GET":
        _fail("FastAPI Body update 未写入热态")
    if resp.json()["info"]["name"] != "from-api":
        _fail("响应应反映更新后热态")
    _ok("FastAPI Body → entry.update 热补丁")


async def test_locked_write_guard() -> None:
    e = ExampleWebhook()
    await e.activate()
    await e.lock()
    try:
        e.info.name = "x"
        _fail("锁定后写入应失败")
    except ValueError:
        pass
    if e.info.name == "x":
        _fail("锁定写入不应生效")
    await e.unlock()
    e.info.name = "ok"
    await e.commit()
    if e.info.name != "ok":
        _fail("解锁后写入应生效")
    _ok("热态锁定写守卫")


async def test_deleted_node_guard() -> None:
    e = ExampleWebhook()
    await e.activate()
    async with config_manager.transaction():
        await e._delete()
    if not e.deleted:
        _fail("删除后应标记 deleted")
    try:
        _ = e.info.name
        _fail("删除后读取应抛 DeletedNodeError")
    except DeletedNodeError:
        pass
    try:
        await e.update(ExampleWebhook.model_validate({"info": {"name": "x"}}))
        _fail("删除后 update 应抛 DeletedNodeError")
    except DeletedNodeError:
        pass
    _ok("热态删除节点读写守卫")


async def main() -> int:
    tests = [
        test_entry_json_schema_field_hints,
        test_collection_json_schema_field_hints,
        test_fastapi_entry_roundtrip,
        test_fastapi_invalid_body_rejected,
        test_fastapi_collection_export,
        test_cold_validate_populates_groups,
        test_cold_load_activates_all_fields_including_defaults,
        test_hot_reject_invalid_url_rollback,
        test_hot_reject_invalid_literal_rollback,
        test_hot_autocorrect_field,
        test_hot_numeric_bounds,
        test_hot_update_partial_errors,
        test_hot_update_skips_unset_fields,
        test_fastapi_update_from_body,
        test_locked_write_guard,
        test_deleted_node_guard,
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
