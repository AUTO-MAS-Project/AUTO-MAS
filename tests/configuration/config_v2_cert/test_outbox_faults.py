"""故障注入：Config v2 outbox 各阶段失败行为认证。

验证 transport 层 outbox hook（enqueue / flush / discard）失败时，
配置事务状态（COMMITTED / ROLLED_BACK）不被反转，异常仅记录 warning。
同时验证 ``configure_outbox_hooks(None, None, None)`` 可完全清除 hook。
"""

from __future__ import annotations

from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock
from uuid import uuid4

from app.configuration import (
    FieldChangeEvent,
    config_manager,
)
from app.configuration.v2.manager import TransactionOutcome
from app.configuration.runtime import (
    configure_outbox_hooks,
    enqueue_field_change,
)
import app.configuration.runtime as runtime_module


def _make_field_change_event(encrypted: bool = False) -> FieldChangeEvent:
    """构造最小可测的 FieldChangeEvent，node 使用 Mock。"""
    node = Mock()
    node.root.uid = uuid4()
    node.uid = uuid4()
    return FieldChangeEvent(
        kind="set",
        node=node,
        group="settings",
        field="first",
        changed=True,
        encrypted=encrypted,
        value=None if encrypted else 10,
        old_value=None if encrypted else 1,
    )


class TestOutboxFaults(IsolatedAsyncioTestCase):
    """outbox hook 故障注入。"""

    def setUp(self) -> None:
        """保存模块级 outbox hook 与 manager hook 以便测试后恢复。"""
        self._old_enqueue = runtime_module._enqueue_outbox
        self._old_flush = runtime_module._flush_outbox
        self._old_discard = runtime_module._discard_outbox
        self._old_post_commit = config_manager._post_commit_hook
        self._old_post_rollback = config_manager._post_rollback_hook

    async def asyncTearDown(self) -> None:
        """直接恢复模块级变量与 manager hook，避免 configure_outbox_hooks 副作用。"""
        runtime_module._enqueue_outbox = self._old_enqueue
        runtime_module._flush_outbox = self._old_flush
        runtime_module._discard_outbox = self._old_discard
        config_manager.configure_transaction_hooks(
            post_commit=self._old_post_commit,
            post_rollback=self._old_post_rollback,
        )

    # ── 1. enqueue hook 失败 → 返回 False ──

    async def test_enqueue_failure_returns_false(self) -> None:
        """enqueue hook 抛异常 → ``enqueue_field_change`` 返回 False 且不抛出。"""

        async def raising_enqueue(
            _id: str,
            _type: str,
            _data: dict,
            *,
            transaction_id: str | None = None,
        ) -> None:
            raise RuntimeError("WS publisher unavailable")

        configure_outbox_hooks(
            enqueue=raising_enqueue,
            flush=None,
            discard=None,
        )

        event = _make_field_change_event()

        async with config_manager.transaction():
            result = await enqueue_field_change(event)

        self.assertFalse(result)

    # ── 2. flush outbox 失败不反转 commit ──

    async def test_flush_outbox_failure_does_not_reverse_commit(self) -> None:
        """flush hook 抛异常 → 事务仍 COMMITTED，异常仅 warning。"""
        flush_called = False

        async def raising_flush(_transaction_id: str) -> None:
            nonlocal flush_called
            flush_called = True
            raise RuntimeError("outbox flush failed")

        configure_outbox_hooks(
            enqueue=None,
            flush=raising_flush,
            discard=None,
        )

        async with config_manager.transaction() as context:
            pass

        self.assertEqual(context.outcome, TransactionOutcome.COMMITTED)
        self.assertTrue(flush_called)

    # ── 3. discard outbox 失败不反转 rollback ──

    async def test_discard_outbox_failure_does_not_reverse_rollback(self) -> None:
        """discard hook 抛异常 → 事务仍 ROLLED_BACK，异常仅 warning。"""
        discard_called = False

        async def raising_discard(_transaction_id: str) -> None:
            nonlocal discard_called
            discard_called = True
            raise RuntimeError("outbox discard failed")

        configure_outbox_hooks(
            enqueue=None,
            flush=None,
            discard=raising_discard,
        )

        with self.assertRaises(ValueError):
            async with config_manager.transaction() as context:
                raise ValueError("trigger rollback")

        self.assertEqual(context.outcome, TransactionOutcome.ROLLED_BACK)
        self.assertTrue(discard_called)

    # ── 4. 清除 hook 后不调任何 hook ──

    async def test_outbox_hooks_can_be_cleared(self) -> None:
        """``configure_outbox_hooks(None, None, None)`` → manager hook 为 None。"""
        configure_outbox_hooks(
            enqueue=None,
            flush=None,
            discard=None,
        )

        self.assertIsNone(config_manager._post_commit_hook)
        self.assertIsNone(config_manager._post_rollback_hook)
        self.assertIsNone(runtime_module._enqueue_outbox)
        self.assertIsNone(runtime_module._flush_outbox)
        self.assertIsNone(runtime_module._discard_outbox)

        # 事务正常完成，不调任何 hook
        async with config_manager.transaction() as context:
            pass

        self.assertEqual(context.outcome, TransactionOutcome.COMMITTED)
