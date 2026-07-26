"""MergeableStateCache 淘汰机制测试。

覆盖三类行为:
1. 语义终结事件（task.completed）清除对应 id 的可合并状态条目；
2. 每 type 的 id 数软上限，超限按最旧修订号淘汰；
3. 快照输出不包含已清除/已淘汰条目。
"""

from __future__ import annotations

from unittest import IsolatedAsyncioTestCase, TestCase

from app.core.ws import protocol
from app.core.ws.publisher import (
    MAX_CACHE_IDS_PER_TYPE,
    TERMINAL_EVENT_DISCARDS,
    MergeableStateCache,
    WSPublisher,
)


class MergeableStateCacheDiscardTest(TestCase):
    def test_discard_removes_entry_and_bumps_revision(self) -> None:
        cache = MergeableStateCache()
        cache.update("task-1", protocol.TASK_INFO_UPDATED, {"status": "运行"})
        revision_before = cache.revision

        removed = cache.discard("task-1", protocol.TASK_INFO_UPDATED)

        self.assertTrue(removed)
        self.assertIsNone(cache.get("task-1", protocol.TASK_INFO_UPDATED))
        self.assertGreater(cache.revision, revision_before)
        self.assertNotIn(protocol.TASK_INFO_UPDATED, cache.snapshot())

    def test_discard_unknown_id_is_noop(self) -> None:
        cache = MergeableStateCache()
        cache.update("task-1", protocol.TASK_INFO_UPDATED, {"status": "运行"})
        revision_before = cache.revision

        removed = cache.discard("task-missing", protocol.TASK_INFO_UPDATED)

        self.assertFalse(removed)
        self.assertEqual(cache.revision, revision_before)
        self.assertIsNotNone(cache.get("task-1", protocol.TASK_INFO_UPDATED))


class MergeableStateCacheSoftLimitTest(TestCase):
    def test_overflow_evicts_oldest_ids_of_same_type(self) -> None:
        cache = MergeableStateCache(max_ids_per_type=3)
        for index in range(5):
            cache.update(
                f"task-{index}",
                protocol.TASK_INFO_UPDATED,
                {"seq": index},
            )

        snapshot = cache.snapshot()
        remaining = snapshot.get(protocol.TASK_INFO_UPDATED, {})
        self.assertEqual(set(remaining), {"task-2", "task-3", "task-4"})
        self.assertIsNone(cache.get("task-0", protocol.TASK_INFO_UPDATED))
        self.assertIsNone(cache.get("task-1", protocol.TASK_INFO_UPDATED))

    def test_overflow_never_evicts_other_types(self) -> None:
        cache = MergeableStateCache(max_ids_per_type=2)
        cache.update("Main", protocol.POWER_SIGN_UPDATED, {"signal": "NoAction"})
        for index in range(4):
            cache.update(
                f"task-{index}",
                protocol.TASK_INFO_UPDATED,
                {"seq": index},
            )

        snapshot = cache.snapshot()
        self.assertEqual(
            snapshot.get(protocol.POWER_SIGN_UPDATED),
            {"Main": {"signal": "NoAction"}},
        )
        self.assertEqual(
            set(snapshot.get(protocol.TASK_INFO_UPDATED, {})),
            {"task-2", "task-3"},
        )

    def test_recent_update_refreshes_eviction_order(self) -> None:
        cache = MergeableStateCache(max_ids_per_type=2)
        cache.update("task-a", protocol.TASK_INFO_UPDATED, {"seq": 0})
        cache.update("task-b", protocol.TASK_INFO_UPDATED, {"seq": 1})
        # 再次更新 task-a，使 task-b 成为最旧条目。
        cache.update("task-a", protocol.TASK_INFO_UPDATED, {"seq": 2})
        cache.update("task-c", protocol.TASK_INFO_UPDATED, {"seq": 3})

        remaining = cache.snapshot().get(protocol.TASK_INFO_UPDATED, {})
        self.assertEqual(set(remaining), {"task-a", "task-c"})

    def test_default_limit_is_positive(self) -> None:
        self.assertGreater(MAX_CACHE_IDS_PER_TYPE, 0)

    def test_non_mergeable_type_never_cached(self) -> None:
        cache = MergeableStateCache(max_ids_per_type=1)
        cache.update("task-1", protocol.TASK_COMPLETED, {"result": "success"})
        self.assertEqual(cache.snapshot(), {})
        self.assertEqual(cache.revision, 0)


class WSPublisherTerminalEventTest(IsolatedAsyncioTestCase):
    async def test_task_completed_clears_cached_task_info(self) -> None:
        publisher = WSPublisher()
        await publisher.send(
            "task-1",
            protocol.TASK_INFO_UPDATED,
            {"status": "运行"},
        )
        self.assertIsNotNone(
            publisher.cache.get("task-1", protocol.TASK_INFO_UPDATED)
        )

        await publisher.send(
            "task-1",
            protocol.TASK_COMPLETED,
            {"result": "success"},
        )

        self.assertIsNone(
            publisher.cache.get("task-1", protocol.TASK_INFO_UPDATED)
        )

    async def test_task_completed_keeps_other_task_entries(self) -> None:
        publisher = WSPublisher()
        await publisher.send("task-1", protocol.TASK_INFO_UPDATED, {"seq": 1})
        await publisher.send("task-2", protocol.TASK_INFO_UPDATED, {"seq": 2})

        await publisher.send("task-1", protocol.TASK_COMPLETED, {"result": "success"})

        states = publisher.snapshot_payload()["states"]
        self.assertEqual(
            set(states.get(protocol.TASK_INFO_UPDATED, {})),
            {"task-2"},
        )

    async def test_snapshot_payload_excludes_cleared_entries(self) -> None:
        publisher = WSPublisher()
        await publisher.send(
            protocol.ID_MAIN,
            protocol.POWER_SIGN_UPDATED,
            {"signal": "NoAction"},
        )
        await publisher.send("task-1", protocol.TASK_INFO_UPDATED, {"seq": 1})
        await publisher.send("task-1", protocol.TASK_COMPLETED, {"result": "success"})

        states = publisher.snapshot_payload()["states"]
        self.assertNotIn(protocol.TASK_INFO_UPDATED, states)
        self.assertEqual(
            states.get(protocol.POWER_SIGN_UPDATED),
            {protocol.ID_MAIN: {"signal": "NoAction"}},
        )

    def test_terminal_mapping_covers_task_completed(self) -> None:
        self.assertEqual(
            TERMINAL_EVENT_DISCARDS.get(protocol.TASK_COMPLETED),
            (protocol.TASK_INFO_UPDATED,),
        )
