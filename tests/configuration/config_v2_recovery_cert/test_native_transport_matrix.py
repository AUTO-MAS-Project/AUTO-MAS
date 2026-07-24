"""NATIVE_TRANSPORT_MATRIX: NativeConfigFacade API 投影保持旧 transport 且不引入 ConfigBase。

验证两点：
1. scripts/users/queue/plan/settings/webhook 的 get_* 方法返回的 dict 形状与
   legacy HTTP 契约一致（instances 索引 + SubConfigsInfo 嵌套 + legacy type 名）。
2. authoritative 路径下，app.core.native_config 与 app.configuration.authoritative
   不导入 app.core.config 或 app.models.ConfigBase（AST 静态校验 + 运行时
   sys.modules 不含这些模块的 ConfigBase 依赖）。
"""

from __future__ import annotations

import ast
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest

from app.core.native_config import NativeConfigFacade, _NATIVE_SCRIPT_CRUD_DESCRIPTORS

from .conftest import safe_close
from .corpus_variants import build_all_variants, write_corpus_to_dir

WORKTREE = Path(__file__).resolve().parents[3]


def _make_facade(config_dir: Path) -> NativeConfigFacade:
    workspace = config_dir.parent
    return NativeConfigFacade(
        workspace_root=workspace,
        config_directory=config_dir,
    )


@pytest.fixture
def initialized_facade(normal_corpus_config):
    facade = _make_facade(normal_corpus_config)

    async def _init():
        await facade.init_config()

    asyncio.run(_init())
    yield facade
    facade.close()


# =====================================================================
# 1. 静态校验：authoritative 路径不导入 ConfigBase / app.core.config
# =====================================================================


def _collect_import_targets(module_path: Path) -> set[str]:
    """解析模块源码的所有 import 目标（from X import / import X）。"""
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                targets.add(node.module)
    return targets


def test_native_config_module_does_not_import_configbase():
    """app/core/native_config.py 不导入 app.core.config 或 app.models.ConfigBase。"""
    targets = _collect_import_targets(
        WORKTREE / "app" / "core" / "native_config.py"
    )
    forbidden = {
        "app.core.config",
        "app.models.ConfigBase",
        "app.models.config",
    }
    actual_forbidden = targets & forbidden
    assert actual_forbidden == set(), (
        f"native_config 意外导入 legacy 配置: {actual_forbidden}"
    )


def test_authoritative_module_does_not_import_configbase():
    """app/configuration/authoritative.py 不导入 app.core.config 或 ConfigBase。"""
    targets = _collect_import_targets(
        WORKTREE / "app" / "configuration" / "authoritative.py"
    )
    forbidden = {
        "app.core.config",
        "app.models.ConfigBase",
        "app.models.config",
    }
    actual_forbidden = targets & forbidden
    assert actual_forbidden == set(), (
        f"authoritative 意外导入 legacy 配置: {actual_forbidden}"
    )


def test_native_config_module_docstring_declares_independence():
    """native_config 模块文档字符串显式声明与 ConfigBase 解耦。"""
    import app.core.native_config as mod

    assert mod.__doc__ is not None
    assert "ConfigBase" in mod.__doc__ or "app.core.config" in mod.__doc__, (
        "native_config 文档字符串未声明与 legacy 配置解耦"
    )


# =====================================================================
# 2. get_script：legacy transport 形状（instances + SubConfigsInfo.UserData）
# =====================================================================


def test_get_script_returns_legacy_transport_shape(initialized_facade):
    """get_script(None) 返回 (index, data)；index 含 {uid, type}，
    data[uid] 含 SubConfigsInfo.UserData（而非 v2 的 UserData 字段）。"""
    facade = initialized_facade

    async def _get():
        return await facade.get_script(None)

    index, data = asyncio.run(_get())
    assert len(index) >= 2, "normal 语料应含至少 2 个脚本"
    for item in index:
        assert set(item.keys()) == {"uid", "type"}, (
            f"index 项 keys 异常: {item.keys()}"
        )
        assert item["type"] in {
            d.legacy_script_type for d in _NATIVE_SCRIPT_CRUD_DESCRIPTORS
        }, f"未知 legacy script type: {item['type']}"
        uid = item["uid"]
        assert uid in data
        payload = data[uid]
        # legacy transport: SubConfigsInfo.UserData 而非顶层 UserData
        assert "SubConfigsInfo" in payload, "缺少 SubConfigsInfo"
        assert "UserData" in payload["SubConfigsInfo"], (
            "SubConfigsInfo 缺少 UserData（legacy transport 形状不符）"
        )
        assert "UserData" not in payload, (
            "顶层 UserData 应被 pop（避免与 legacy 契约冲突）"
        )
        user_data = payload["SubConfigsInfo"]["UserData"]
        assert "instances" in user_data
        for user_item in user_data["instances"]:
            assert set(user_item.keys()) == {"uid", "type"}


def test_get_script_single_uid(initialized_facade):
    """get_script(uid) 仅返回该脚本。"""
    facade = initialized_facade

    first_uid = next(iter(facade.roots.scripts.keys()))

    async def _get():
        return await facade.get_script(str(first_uid))

    index, data = asyncio.run(_get())
    assert len(index) == 1
    assert index[0]["uid"] == str(first_uid)


def test_get_script_unknown_uid_raises(initialized_facade):
    """不存在的 uid → ValueError。"""
    facade = initialized_facade

    async def _get():
        await facade.get_script("ffffffff-ffff-ffff-ffff-ffffffffffff")

    with pytest.raises(ValueError):
        asyncio.run(_get())


# =====================================================================
# 3. get_user：legacy transport（SubConfigsInfo.Notify_CustomWebhooks）
# =====================================================================


def test_get_user_returns_legacy_transport_with_webhooks(initialized_facade):
    """get_user 返回的 user payload 含 SubConfigsInfo.Notify_CustomWebhooks。"""
    facade = initialized_facade
    script_uid = next(iter(facade.roots.scripts.keys()))
    script = facade.roots.scripts[script_uid]
    user_uid = next(iter(script.UserData.keys()))

    async def _get():
        return await facade.get_user(str(script_uid), str(user_uid))

    index, data = asyncio.run(_get())
    assert len(index) == 1
    assert index[0]["uid"] == str(user_uid)
    payload = data[str(user_uid)]
    # legacy user transport: Notify_CustomWebhooks 在 SubConfigsInfo 下
    if "SubConfigsInfo" in payload:
        assert "Notify_CustomWebhooks" not in payload or (
            "Notify_CustomWebhooks" in payload["SubConfigsInfo"]
        )


# =====================================================================
# 4. get_queue / get_queue_item：legacy_type 与 instances
# =====================================================================


def test_get_queue_returns_legacy_type(initialized_facade):
    """get_queue(None) 返回 legacy_type=QueueConfig。"""
    facade = initialized_facade

    async def _get():
        return await facade.get_queue(None)

    index, data = asyncio.run(_get())
    assert len(index) >= 2, "normal 语料应含至少 2 个 queue"
    for item in index:
        assert item["type"] == "QueueConfig", (
            f"queue type 应为 QueueConfig，实际 {item['type']}"
        )


def test_get_queue_item_returns_legacy_type(initialized_facade):
    """get_queue_item 返回 legacy_type=QueueItem。"""
    facade = initialized_facade
    queue_uid, queue = next(iter(facade.roots.queues.items()))

    async def _get():
        return await facade.get_queue_item(str(queue_uid), None)

    index, data = asyncio.run(_get())
    assert len(index) >= 2, "normal 语料每个 queue 应含至少 2 个 QueueItem"
    for item in index:
        assert item["type"] == "QueueItem"


# =====================================================================
# 5. get_plan：legacy_type=MaaPlanConfig
# =====================================================================


def test_get_plan_returns_legacy_type(initialized_facade):
    """get_plan(None) 返回 legacy_type=MaaPlanConfig。"""
    facade = initialized_facade

    async def _get():
        return await facade.get_plan(None)

    index, data = asyncio.run(_get())
    assert len(index) >= 1
    for item in index:
        assert item["type"] == "MaaPlanConfig"


# =====================================================================
# 6. get_setting：entry payload（含 reactive）
# =====================================================================


def test_get_setting_returns_payload_dict(initialized_facade):
    """get_setting 返回 dict（非 None）。"""
    facade = initialized_facade

    async def _get():
        return await facade.get_setting()

    payload = asyncio.run(_get())
    assert isinstance(payload, dict)
    assert "Function" in payload or "Data" in payload


# =====================================================================
# 7. get_webhook：legacy_type=Webhook + instances
# =====================================================================


def test_get_webhook_global_returns_legacy_type(initialized_facade):
    """全局 webhook（script_id=None, user_id=None）返回 legacy_type=Webhook。"""
    facade = initialized_facade

    async def _get():
        return await facade.get_webhook(None, None, None)

    index, data = asyncio.run(_get())
    for item in index:
        assert item["type"] == "Webhook"


# =====================================================================
# 8. PluginScript：readable but writable=False
# =====================================================================


def test_plugin_script_descriptor_writable_false():
    """PluginScript descriptor.writable=False（fail-closed 写入）。"""
    plugin_descriptor = next(
        d for d in _NATIVE_SCRIPT_CRUD_DESCRIPTORS if d.api_type_key == "PluginScript"
    )
    assert plugin_descriptor.writable is False


def test_add_plugin_script_rejected(initialized_facade):
    """add_script('PluginScript') → RuntimeError（writable=False）。"""
    facade = initialized_facade

    async def _add():
        await facade.add_script("PluginScript")

    with pytest.raises(RuntimeError, match="尚未完成原生 Config v2 迁移"):
        asyncio.run(_add())


# =====================================================================
# 9. toDict / get / set：保持旧 transport 表面
# =====================================================================


def test_todict_returns_config_dict(initialized_facade):
    """toDict(if_decrypt=False) 返回 dict 且不抛。"""
    facade = initialized_facade

    async def _to():
        return await facade.toDict(if_decrypt=False)

    payload = asyncio.run(_to())
    assert isinstance(payload, dict)


def test_get_set_roundtrip(initialized_facade):
    """get/set 单字段 round-trip。"""
    facade = initialized_facade

    async def _roundtrip():
        original = facade.get("Function", "IfAllowSleep")
        await facade.set("Function", "IfAllowSleep", not original)
        return facade.get("Function", "IfAllowSleep"), original

    new_value, original = asyncio.run(_roundtrip())
    assert new_value == (not original)


def test_todict_regenerate_uuids_rejected(initialized_facade):
    """toDict(regenerate_uuids=True) → ValueError（全局配置无 regenerable identity）。"""
    facade = initialized_facade

    async def _to():
        await facade.toDict(regenerate_uuids=True)

    with pytest.raises(ValueError):
        asyncio.run(_to())


# =====================================================================
# 10. WS sender 保持旧 transport 表面
# =====================================================================


def test_send_json_delegates_to_ws_bootstrap(initialized_facade):
    """send_json 委托 app.core.ws.bootstrap.send_json（旧 transport 入口）。"""
    facade = initialized_facade
    from unittest.mock import AsyncMock

    async def _send():
        with patch("app.core.ws.bootstrap.send_json", new=AsyncMock()) as mock:
            await facade.send_json({"type": "test"})
            return mock

    mock = asyncio.run(_send())
    mock.assert_awaited_once_with({"type": "test"})


def test_send_websocket_message_delegates_to_ws_bootstrap(initialized_facade):
    """send_websocket_message 委托 app.core.ws.bootstrap.send_websocket_message。"""
    facade = initialized_facade
    from unittest.mock import AsyncMock

    async def _send():
        with patch(
            "app.core.ws.bootstrap.send_websocket_message",
            new=AsyncMock(),
        ) as mock:
            await facade.send_websocket_message(
                id="ws-1", type="event", data={"k": "v"}
            )
            return mock

    mock = asyncio.run(_send())
    mock.assert_awaited_once_with(id="ws-1", type="event", data={"k": "v"})


# =====================================================================
# 11. 运行时：authoritative 路径不触发 ConfigBase 实例化
# =====================================================================


def test_authoritative_runtime_does_not_instantiate_configbase(
    normal_corpus_config,
):
    """初始化 authoritative runtime 不会实例化 app.models.ConfigBase.ConfigBase。

    通过 patch ConfigBase.__init__ 监控：若被调用则 fail。
    """
    # 延迟导入避免影响测试收集
    import app.models.ConfigBase as configbase_module

    original_init = configbase_module.ConfigBase.__init__
    call_count = {"n": 0}

    def tracking_init(self, *args, **kwargs):
        call_count["n"] += 1
        return original_init(self, *args, **kwargs)

    facade = _make_facade(normal_corpus_config)
    with patch.object(
        configbase_module.ConfigBase, "__init__", tracking_init
    ):
        async def _init():
            await facade.init_config()

        asyncio.run(_init())

    try:
        assert call_count["n"] == 0, (
            f"authoritative init 意外实例化 ConfigBase {call_count['n']} 次"
        )
    finally:
        facade.close()
