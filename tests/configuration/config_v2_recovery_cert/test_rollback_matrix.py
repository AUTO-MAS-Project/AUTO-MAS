"""ROLLBACK_MATRIX: 锁、级联删除、重排、跨根事务故障注入。

验证 NativeConfigFacade 的 del_script / reorder_script / reorder_queue_item /
跨根事务在故障注入下的原子性与可观察差异。每条用例给预期/实际差异。

关键契约（来自 app/core/native_config.py）：
- del_script 在单个 config_manager.transaction() 内：遍历所有 queue 的
  QueueItem，移除 ScriptId 匹配的项，最后移除 script。任一失败回滚整体。
- is_locked 的 entry 拒绝 del/reorder。
- reorder 校验 order 长度等于 collection 长度。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from app.configuration.v2.manager import config_manager
from app.core.native_config import NativeConfigFacade

from .conftest import safe_close, try_initialize
from .corpus_variants import build_all_variants, write_corpus_to_dir


def _make_facade(config_dir: Path) -> NativeConfigFacade:
    """构造指向 scratch config 的 facade（非单例）。"""
    workspace = config_dir.parent
    return NativeConfigFacade(
        workspace_root=workspace,
        config_directory=config_dir,
    )


@pytest.fixture
def initialized_facade(normal_corpus_config):
    """已初始化的 facade，用例结束后 close 释放 owner。"""
    facade = _make_facade(normal_corpus_config)

    async def _init():
        await facade.init_config()

    asyncio.run(_init())
    yield facade
    facade.close()


# =====================================================================
# 1. del_script 级联删除：跨根（Script + Queue）原子性
# =====================================================================


def test_del_script_removes_matching_queue_items(initialized_facade):
    """del_script 删除脚本时，所有 queue 中 ScriptId 匹配的 QueueItem 被级联删除。

    预期：删除后 script 不存在；匹配的 QueueItem 不存在；不匹配的保留。
    实际：见断言（observed）。
    """
    facade = initialized_facade
    scripts = facade.roots.scripts
    queues = facade.roots.queues

    # 取第一个脚本 UID，把它绑定到一个 QueueItem
    script_uid = next(iter(scripts.keys()))
    queue_uid, queue = next(iter(queues.items()))
    item_uid, item = next(iter(queue.QueueItem.items()))
    # 设置 QueueItem.ScriptId 指向该脚本

    async def _bind():
        async with config_manager.transaction():
            item.Info.ScriptId = str(script_uid)
            await item.commit()

    asyncio.run(_bind())

    # 删除脚本
    async def _del():
        await facade.del_script(str(script_uid))

    asyncio.run(_del())

    # script 已删除
    assert script_uid not in facade.roots.scripts
    # 匹配的 QueueItem 已删除
    assert item_uid not in queue.QueueItem


def test_del_script_dangling_reference_safe(initialized_facade):
    """QueueItem.ScriptId 指向不存在脚本时，del_script 安全跳过（无匹配）。

    预期：不抛异常，script 删除，无 QueueItem 被移除。
    """
    facade = initialized_facade
    scripts = facade.roots.scripts
    queues = facade.roots.queues

    script_uid = next(iter(scripts.keys()))
    queue_uid, queue = next(iter(queues.items()))
    item_uid, item = next(iter(queue.QueueItem.items()))

    # ScriptId 指向不存在的脚本
    async def _bind():
        async with config_manager.transaction():
            item.Info.ScriptId = "ffffffff-ffff-ffff-ffff-ffffffffffff"
            await item.commit()

    asyncio.run(_bind())

    async def _del():
        await facade.del_script(str(script_uid))

    asyncio.run(_del())

    assert script_uid not in facade.roots.scripts
    # 无匹配 → QueueItem 保留
    assert item_uid in queue.QueueItem


def test_del_script_atomic_on_queue_item_removal_failure(initialized_facade):
    """QueueItem.remove 中途失败 → 整个事务回滚，script 与 QueueItem 都保留。

    预期：抛异常；script 仍在；已删除的 QueueItem 恢复。
    实际：config_manager.transaction() 块内异常 → ROLLED_BACK，COW 撤销。
    """
    facade = initialized_facade
    scripts = facade.roots.scripts
    queues = facade.roots.queues

    script_uid = next(iter(scripts.keys()))
    queue_uid, queue = next(iter(queues.items()))
    item_uid, item = next(iter(queue.QueueItem.items()))

    async def _bind():
        async with config_manager.transaction():
            item.Info.ScriptId = str(script_uid)
            await item.commit()

    asyncio.run(_bind())

    # 注入 fault：patch collection.remove 抛异常
    original_remove = type(queue.QueueItem).remove

    def failing_remove(collection, uid):
        if uid == item_uid:
            raise RuntimeError("injected queue item removal failure")
        return original_remove(collection, uid)

    async def _del():
        with patch.object(
            type(queue.QueueItem), "remove", failing_remove
        ):
            await facade.del_script(str(script_uid))

    with pytest.raises(RuntimeError, match="injected"):
        asyncio.run(_del())

    # 事务回滚：script 与 QueueItem 都保留
    assert script_uid in facade.roots.scripts, (
        "del_script 中途失败后 script 不应被删除（事务回滚）"
    )
    assert item_uid in queue.QueueItem, (
        "del_script 中途失败后 QueueItem 不应被删除（事务回滚）"
    )


# =====================================================================
# 2. 锁：is_locked 拒绝 del/reorder
# =====================================================================


def test_del_script_rejected_when_script_locked(initialized_facade):
    """script.is_locked=True → del_script 抛 RuntimeError。"""
    facade = initialized_facade
    script_uid = next(iter(facade.roots.scripts.keys()))
    script = facade.roots.scripts[script_uid]

    with patch.object(type(script), "is_locked", new=True):
        async def _del():
            await facade.del_script(str(script_uid))

        with pytest.raises(RuntimeError, match="正在运行"):
            asyncio.run(_del())

    # script 仍在
    assert script_uid in facade.roots.scripts


def test_del_script_rejected_when_queue_locked(initialized_facade):
    """关联 queue.is_locked=True → del_script 抛 RuntimeError，不删除。"""
    facade = initialized_facade
    scripts = facade.roots.scripts
    queues = facade.roots.queues

    script_uid = next(iter(scripts.keys()))
    queue_uid, queue = next(iter(queues.items()))
    item_uid, item = next(iter(queue.QueueItem.items()))

    async def _bind():
        async with config_manager.transaction():
            item.Info.ScriptId = str(script_uid)
            await item.commit()

    asyncio.run(_bind())

    with patch.object(type(queue), "is_locked", new=True):
        async def _del():
            await facade.del_script(str(script_uid))

        with pytest.raises(RuntimeError, match="队列.*正在运行"):
            asyncio.run(_del())

    assert script_uid in facade.roots.scripts
    assert item_uid in queue.QueueItem


# =====================================================================
# 3. reorder：校验与故障注入
# =====================================================================


def test_reorder_script_valid(initialized_facade):
    """合法 reorder → 顺序更新。"""
    facade = initialized_facade
    original_order = [str(uid) for uid in facade.roots.scripts.keys()]
    reversed_order = list(reversed(original_order))

    async def _reorder():
        await facade.reorder_script(reversed_order)

    asyncio.run(_reorder())
    actual_order = [str(uid) for uid in facade.roots.scripts.keys()]
    assert actual_order == reversed_order


def test_reorder_script_invalid_length(initialized_facade):
    """order 长度 ≠ collection 长度 → 抛异常。"""
    facade = initialized_facade
    original_order = [str(uid) for uid in facade.roots.scripts.keys()]
    bad_order = original_order[:-1]  # 少一个

    async def _reorder():
        await facade.reorder_script(bad_order)

    with pytest.raises(Exception):
        asyncio.run(_reorder())

    # 顺序不变
    actual = [str(uid) for uid in facade.roots.scripts.keys()]
    assert actual == original_order


def test_reorder_queue_item_atomic_on_failure(initialized_facade):
    """reorder 中途 commit 失败 → 顺序不变。"""
    facade = initialized_facade
    queues = facade.roots.queues
    queue_uid, queue = next(iter(queues.items()))
    original_order = [str(uid) for uid in queue.QueueItem.keys()]
    reversed_order = list(reversed(original_order))

    async def _reorder():
        with patch.object(
            type(queue.QueueItem),
            "commit",
            new=AsyncMock(side_effect=RuntimeError("injected commit failure")),
        ):
            await facade.reorder_queue_item(str(queue_uid), reversed_order)

    with pytest.raises(RuntimeError, match="injected"):
        asyncio.run(_reorder())

    actual = [str(uid) for uid in queue.QueueItem.keys()]
    assert actual == original_order, (
        "reorder commit 失败后顺序不应改变（事务回滚）"
    )


# =====================================================================
# 4. 跨根事务：script + queue 在同一 transaction 内
# =====================================================================


def test_cross_root_transaction_commit(initialized_facade):
    """同一 transaction 内修改 script + queue → 两者都提交。"""
    facade = initialized_facade
    scripts = facade.roots.scripts
    queues = facade.roots.queues
    script_uid = next(iter(scripts.keys()))
    script = scripts[script_uid]
    queue_uid, queue = next(iter(queues.items()))
    item_uid, item = next(iter(queue.QueueItem.items()))

    async def _cross_root_set():
        async with config_manager.transaction():
            script.Info.Name = "cross-root-modified"
            item.Info.ScriptId = str(script_uid)
            await script.commit()
            await item.commit()

    asyncio.run(_cross_root_set())

    assert script.Info.Name == "cross-root-modified"
    assert item.Info.ScriptId == str(script_uid)


def test_cross_root_transaction_rollback(initialized_facade):
    """同一 transaction 内：第二个 set 失败 → 第一个也回滚。"""
    facade = initialized_facade
    scripts = facade.roots.scripts
    queues = facade.roots.queues
    script_uid = next(iter(scripts.keys()))
    script = scripts[script_uid]
    queue_uid, queue = next(iter(queues.items()))
    item_uid, item = next(iter(queue.QueueItem.items()))
    original_name = script.Info.Name
    original_script_id = item.Info.ScriptId

    async def _cross_root_with_fault():
        async with config_manager.transaction():
            script.Info.Name = "should-rollback"
            await script.commit()
            # 注入第二个 set 失败
            raise RuntimeError("injected mid-transaction failure")

    with pytest.raises(RuntimeError, match="injected"):
        asyncio.run(_cross_root_with_fault())

    assert script.Info.Name == original_name, (
        "跨根事务回滚后 script.Name 应恢复"
    )
    assert item.Info.ScriptId == original_script_id


# =====================================================================
# 5. r6 rollback bundle 边界
# =====================================================================


def test_rollback_bundle_target_exists_rejected(initialized_facade):
    """已存在的 rollback bundle 目标 → RollbackExportError，不覆盖。"""
    from app.configuration.authoritative import RollbackExportError

    facade = initialized_facade
    # 第一次导出
    bundle_path1 = facade.export_r6_rollback_bundle()
    assert bundle_path1.exists()

    # 第二次导出到同一父目录 → 目标已存在
    with pytest.raises(RollbackExportError):
        facade.export_r6_rollback_bundle(
            export_parent=bundle_path1.parent
        )

    # 原 bundle 未被覆盖
    manifest = json.loads(
        (bundle_path1 / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["kind"] == "auto-mas-r6-config-rollback"


def test_rollback_bundle_eight_roots_sha256_verified(initialized_facade):
    """rollback bundle 含 8 个根，每个 sha256 与文件字节一致。"""
    import hashlib

    facade = initialized_facade
    bundle = facade.export_r6_rollback_bundle()
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))

    assert len(manifest["roots"]) == 8
    for record in manifest["roots"]:
        root_file = bundle / record["name"]
        content = root_file.read_bytes()
        assert len(content) == record["size_bytes"]
        assert hashlib.sha256(content).hexdigest() == record["sha256"]
