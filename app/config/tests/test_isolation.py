"""事务隔离异常测试：脏读、幻读、不可重复读等（相对数据库隔离术语）。

用法（仓库根目录）::

    python -m app.config.tests.test_isolation

约定（§3.2 / §4）：

- stage 仅记录 op，不改动已提交数据。
- 事务内读写经 ``effective``（ws）；事务外读 ``self``（已提交）。
- ``model_dump``：FastAPI / 冷态响应（默认明文 + 响应式字段）。
- ``to_dict``：已激活导出 / 落盘（默认密文、无响应式；校验 ACTIVE / 软删）。
- 全局外层事务互斥。
"""

from __future__ import annotations

import asyncio
from typing import cast

from blinker import Signal

from app.config import (
    ConfigAggregateError,
    ConfigCollection,
    FieldChangeEvent,
    config_manager,
)
from app.config.examples.reference_config import (
    ExampleQueue,
    ExampleQueueItem,
    ExampleScript,
    ExampleWebhook,
)

# ExampleQueueItem.ref("scripts") 热化需要已登记目标
_scripts = ConfigCollection([ExampleScript], name="scripts")
_scripts_ready = False


async def _ensure_scripts() -> None:
    global _scripts_ready
    if not _scripts_ready:
        await _scripts.activate()
        _scripts_ready = True


def _fail(message: str) -> None:
    raise AssertionError(message)


def _ok(message: str) -> None:
    print(f"OK: {message}")


def _reset_signal(cls: type) -> None:
    cls.signal = Signal()


async def _loaded_webhook(*, name: str = "committed") -> ExampleWebhook:
    entry = ExampleWebhook.build(wire={"info": {"name": name}})
    await entry.activate()
    return entry


# ── stage：非数据面，不构成脏读 ──


async def test_stage_not_visible_before_commit() -> None:
    """stage 后读路径仍见已提交值（非脏读场景：未进入事务）。"""
    entry = await _loaded_webhook(name="before")
    entry.info.name = "staged-only"
    got_name = cast(str, entry.info.name)
    if got_name != "before":
        _fail("stage 后读路径不应变化")
    if not entry._staged_ops:
        _fail("应有 staged op")
    await entry.commit()
    if entry.info.name != "staged-only":
        _fail("commit 后应生效")
    _ok("stage 未 commit 不可见")


# ── 脏读：事务外读者不见未提交 ws ──


async def test_outside_reader_no_dirty_read() -> None:
    """事务未 COMMIT 时，事务外读者仍见已提交值。"""
    entry = await _loaded_webhook(name="committed")
    barrier = asyncio.Barrier(2)
    observed: list[str] = []

    async def writer() -> None:
        async with config_manager.transaction():
            entry._build_workspace()
            ws_info = getattr(entry.effective, "info")
            object.__setattr__(ws_info, "name", "uncommitted")
            await barrier.wait()
            await asyncio.sleep(0.02)

    async def reader() -> None:
        await barrier.wait()
        observed.append(entry.info.name)

    await asyncio.gather(writer(), reader())
    if observed != ["committed"]:
        _fail(f"事务外应无脏读，实际 {observed}")
    if entry.info.name != "uncommitted":
        _fail("COMMIT 后应见新值")
    _ok("脏读：事务外读者不见未提交 ws")


async def test_export_no_dirty_read_during_transaction() -> None:
    """model_dump / to_dict 在事务内仍导出已提交 self。"""
    entry = await _loaded_webhook(name="on-disk")
    async with config_manager.transaction():
        entry._build_workspace()
        ws_info = getattr(entry.effective, "info")
        object.__setattr__(ws_info, "name", "in-ws-only")
        dumped = entry.model_dump()
        as_dict = await entry.to_dict()
    if dumped.get("info", {}).get("name") != "on-disk":
        _fail(f"model_dump 不应读 ws: {dumped}")
    if as_dict.get("info", {}).get("name") != "on-disk":
        _fail(f"to_dict 不应读 ws: {as_dict}")
    if entry.info.name != "in-ws-only":
        _fail("COMMIT 后读路径应见 ws 合并值")
    _ok("脏读：导出路径不读事务 ws")


# ── 不可重复读：事务外两次读在并发未提交写期间一致 ──


async def test_repeatable_read_outside_open_transaction() -> None:
    """并发事务未结束期间，事务外连续两次读结果一致（已提交快照）。"""
    entry = await _loaded_webhook(name="v1")
    barrier = asyncio.Barrier(2)
    reads: list[str] = []

    async def writer() -> None:
        async with config_manager.transaction():
            entry._build_workspace()
            ws_info = getattr(entry.effective, "info")
            object.__setattr__(ws_info, "name", "v2")
            await barrier.wait()
            await asyncio.sleep(0.02)

    async def reader() -> None:
        await barrier.wait()
        reads.append(entry.info.name)
        reads.append(entry.info.name)

    await asyncio.gather(writer(), reader())
    if reads != ["v1", "v1"]:
        _fail(f"事务外不可重复读应稳定，实际 {reads}")
    _ok("不可重复读：事务外连续读一致")


async def test_intra_transaction_sees_own_writes() -> None:
    """同事务内读 effective 可见本事务写入（非脏读，是读己之写）。"""
    entry = await _loaded_webhook(name="old")
    async with config_manager.transaction():
        entry._build_workspace()
        ws_info = getattr(entry.effective, "info")
        object.__setattr__(ws_info, "name", "in-txn")
        if entry.info.name != "in-txn":
            _fail("事务内应读到 ws 写入")
    if entry.info.name != "in-txn":
        _fail("COMMIT 后应持久化")
    _ok("同事务内读己之写")


# ── 幻读：结构变更 staged / 未提交 ws 不可见 ──


async def test_phantom_read_staged_collection_add() -> None:
    """staged add 未 commit：枚举/成员不可见。"""
    await _ensure_scripts()
    queue = ExampleQueue.build(
        wire={"info": {"name": "q"}, "items": {"order": [], "data": {}}}
    )
    await queue.activate()
    items = queue.items
    n0 = len(items)
    uid = items.add(ExampleQueueItem, wire={"info": {"script_id": "-"}})
    if len(items) != n0:
        _fail("staged add 不应改变 len")
    if uid in items:
        _fail("staged add 不应出现在 col[uid]")
    await items.commit()
    if len(items) != n0 + 1 or uid not in items:
        _fail("commit 后应可见新成员")
    _ok("幻读：staged add 不可见")


async def test_phantom_read_uncommitted_collection_remove() -> None:
    """事务内 ws 删除未 COMMIT：事务外仍可见成员。"""
    await _ensure_scripts()
    root = ConfigCollection([ExampleQueue])
    await root.activate()
    q_uid = root.add(ExampleQueue, wire={"info": {"name": "q"}, "items": {"order": [], "data": {}}})
    await root.commit()
    queue = root[q_uid]
    item_uid = queue.items.add(ExampleQueueItem)
    await queue.items.commit()
    if len(queue.items) != 1:
        _fail("setup 应有 1 项")

    barrier = asyncio.Barrier(2)
    outside_len: list[int] = []

    async def remover() -> None:
        async with config_manager.transaction():
            queue.items._build_workspace()
            ws = queue.items.effective
            entry = ws.data[item_uid]
            await entry._delete()
            del ws.data[item_uid]
            ws.order = [x for x in ws.order if x.uid != item_uid]
            await barrier.wait()
            await asyncio.sleep(0.02)

    async def observer() -> None:
        await barrier.wait()
        outside_len.append(len(queue.items))
        outside_len.append(item_uid in queue.items)

    await asyncio.gather(remover(), observer())
    if outside_len != [1, True]:
        _fail(f"未 COMMIT 删除不应被事务外看见: len/member={outside_len}")
    if len(queue.items) != 0:
        _fail("COMMIT 后应已删除")
    _ok("幻读：未提交删除不可见")


# ── 回滚：失败事务不污染已提交态 ──


async def test_rollback_no_dirty_write() -> None:
    """commit 内 signal 失败 → ROLLBACK，读路径仍为旧值。"""
    _reset_signal(ExampleWebhook)
    entry = await _loaded_webhook(name="stable")

    @ExampleWebhook.connect(phase="runtime", group="info", field="name")
    async def abort(sender: object, event: FieldChangeEvent) -> None:
        raise RuntimeError("force rollback")

    _ = (abort,)

    entry.info.name = "must-not-stick"
    try:
        await entry.commit()
        _fail("应返回 commit 错误")
    except ConfigAggregateError:
        pass
    if entry.info.name == "must-not-stick":
        _fail("ROLLBACK 后不应保留新值")
    got_name = cast(str, entry.info.name)
    if got_name != "stable":
        _fail(f"ROLLBACK 后应恢复 stable，实际 {entry.info.name!r}")
    _ok("回滚：失败事务不脏写")


# ── 外层事务互斥 ──


async def test_outer_transaction_mutex() -> None:
    """全局仅一外层事务：两 Task 不得交错执行。"""
    events: list[str] = []

    async def run_txn(label: str, hold: float) -> None:
        async with config_manager.transaction():
            events.append(f"{label}:start")
            await asyncio.sleep(hold)
            events.append(f"{label}:end")

    await asyncio.gather(run_txn("A", 0.04), run_txn("B", 0.01))

    def fully_before(a: str, b: str) -> bool:
        return events.index(f"{a}:end") < events.index(f"{b}:start")

    if not (fully_before("A", "B") or fully_before("B", "A")):
        _fail(f"外层事务应串行，实际顺序 {events}")
    _ok("外层事务互斥")


async def test_nested_transaction_shares_context() -> None:
    """同 Task 嵌套 transaction 共用 ctx，内层不单独 COMMIT。"""
    entry = await _loaded_webhook(name="nested")
    merged = False

    async def inner() -> None:
        nonlocal merged
        async with config_manager.transaction():
            entry._build_workspace()
            ws_info = getattr(entry.effective, "info")
            object.__setattr__(ws_info, "name", "inner")

    async with config_manager.transaction():
        entry._build_workspace()
        ws_info = getattr(entry.effective, "info")
        object.__setattr__(ws_info, "name", "outer")
        await inner()
        if entry.info.name != "inner":
            _fail("嵌套事务写入应在外层事务内可见")
        merged = entry.info.name == "inner"

    if not merged or entry.info.name != "inner":
        _fail("嵌套事务应随外层一并 COMMIT")
    _ok("嵌套事务与外层同一 ctx")


async def test_workspace_cannot_rebuild_workspace() -> None:
    """工作区壳 _is_workspace=True，不可再 _build_workspace。"""
    entry = await _loaded_webhook(name="ws-guard")
    async with config_manager.transaction():
        entry._build_workspace()
        ws = entry.effective
        if not getattr(ws, "_is_workspace", False):
            _fail("effective 应为工作区壳")
        try:
            ws._build_workspace()
            _fail("工作区再创建应失败")
        except RuntimeError as exc:
            if "工作区" not in str(exc):
                _fail(f"错误信息应提示工作区: {exc}")
    _ok("工作区不可再次创建工作区")


async def main() -> int:
    tests = [
        test_stage_not_visible_before_commit,
        test_outside_reader_no_dirty_read,
        test_export_no_dirty_read_during_transaction,
        test_repeatable_read_outside_open_transaction,
        test_intra_transaction_sees_own_writes,
        test_phantom_read_staged_collection_add,
        test_phantom_read_uncommitted_collection_remove,
        test_rollback_no_dirty_write,
        test_outer_transaction_mutex,
        test_nested_transaction_shares_context,
        test_workspace_cannot_rebuild_workspace,
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
