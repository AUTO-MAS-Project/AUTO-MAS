"""故障注入：Config v2 事务各阶段失败行为认证。

验证事务在 prepare-commit / commit / rollback / 持久化各阶段注入异常时，
事务结果（COMMITTED / ROLLED_BACK）与错误传播语义符合设计契约：
- post-commit / post-rollback hook 失败不反转已确定的事务结果
- prepare-commit hook 失败导致整个事务回滚
- 去抖持久化失败仅记录日志，不向触发方抛出
- flush() 同步持久化失败时传播 ConfigAggregateError
"""

from __future__ import annotations

import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from app.configuration import (
    ConfigAggregateError,
    config_manager,
)
from app.configuration.v2.manager import TransactionOutcome


class TestTransactionFaults(IsolatedAsyncioTestCase):
    """事务生命周期故障注入。"""

    def setUp(self) -> None:
        """保存当前 hook 以便测试后恢复。"""
        self._old_post_commit = config_manager._post_commit_hook
        self._old_post_rollback = config_manager._post_rollback_hook
        self._old_prepare_commit = config_manager._prepare_commit_hook

    async def asyncTearDown(self) -> None:
        """恢复 hook 并清理可能残留的去抖 task。"""
        config_manager.configure_transaction_hooks(
            post_commit=self._old_post_commit,
            post_rollback=self._old_post_rollback,
        )
        config_manager.configure_prepare_commit_hook(self._old_prepare_commit)

        handle = config_manager._save_handle
        if handle is not None and not handle.done():
            handle.cancel()
            try:
                await handle
            except (asyncio.CancelledError, Exception):
                pass
            if config_manager._save_handle is handle:
                config_manager._save_handle = None

    # ── 1. 块内抛异常 → ROLLED_BACK ──

    async def test_transaction_rollback_on_exception(self) -> None:
        """事务块内 raise ValueError → outcome == ROLLED_BACK。"""
        with self.assertRaises(ValueError):
            async with config_manager.transaction() as context:
                raise ValueError("boom")

        self.assertEqual(context.outcome, TransactionOutcome.ROLLED_BACK)

    # ── 2. 正常退出 → COMMITTED ──

    async def test_transaction_commit_on_normal_exit(self) -> None:
        """事务块正常退出 → outcome == COMMITTED。"""
        async with config_manager.transaction() as context:
            pass

        self.assertEqual(context.outcome, TransactionOutcome.COMMITTED)

    # ── 3. post-commit hook 失败不反转 commit ──

    async def test_post_commit_hook_failure_does_not_reverse_commit(self) -> None:
        """post_commit hook 抛异常 → 事务仍 COMMITTED，异常仅 warning。"""
        hook_called = asyncio.Event()

        async def failing_post_commit(_transaction_id: object) -> None:
            hook_called.set()
            raise RuntimeError("post-commit transport failed")

        config_manager.configure_transaction_hooks(
            post_commit=failing_post_commit,
            post_rollback=None,
        )

        async with config_manager.transaction() as context:
            pass

        self.assertEqual(context.outcome, TransactionOutcome.COMMITTED)
        self.assertTrue(hook_called.is_set())

    # ── 4. post-rollback hook 失败不反转 rollback ──

    async def test_post_rollback_hook_failure_does_not_reverse_rollback(self) -> None:
        """post_rollback hook 抛异常 → 事务仍 ROLLED_BACK，异常仅 warning。"""
        hook_called = asyncio.Event()

        async def failing_post_rollback(_transaction_id: object) -> None:
            hook_called.set()
            raise RuntimeError("post-rollback transport failed")

        config_manager.configure_transaction_hooks(
            post_commit=None,
            post_rollback=failing_post_rollback,
        )

        with self.assertRaises(ValueError):
            async with config_manager.transaction() as context:
                raise ValueError("trigger rollback")

        self.assertEqual(context.outcome, TransactionOutcome.ROLLED_BACK)
        self.assertTrue(hook_called.is_set())

    # ── 5. prepare-commit hook 失败 → 回滚 ──

    async def test_prepare_commit_hook_failure_rolls_back(self) -> None:
        """prepare_commit hook 抛异常 → 事务 ROLLED_BACK。

        prepare hook 仅在 ``_transaction_has_changes`` 返回 True 时执行，
        因此 patch 该方法返回 True 以触发 hook 调用。
        """
        prepare_called = asyncio.Event()

        async def failing_prepare(_transaction_id: object) -> None:
            prepare_called.set()
            raise RuntimeError("prepare-commit durable failure")

        config_manager.configure_prepare_commit_hook(failing_prepare)

        with (
            patch.object(
                config_manager,
                "_transaction_has_changes",
                return_value=True,
            ),
            self.assertRaises(RuntimeError),
        ):
            async with config_manager.transaction() as context:
                pass

        self.assertEqual(context.outcome, TransactionOutcome.ROLLED_BACK)
        self.assertTrue(prepare_called.is_set())

    # ── 6. 去抖持久化失败仅记录日志 ──

    async def test_debounced_save_failure_logged_not_raised(self) -> None:
        """``_write_all_roots`` 抛异常 → debounce task 的 consume_failure 仅 logger.error。

        ``schedule_debounced_save`` 创建后台 task，task 内 ``_debounced_save_impl``
        调用 ``_write_all_roots``。失败时 ``consume_failure`` 回调通过
        ``task.exception()`` 消费异常并 ``logger.error``，不向 ``schedule_debounced_save``
        调用方抛出。
        """
        with (
            patch.object(
                config_manager,
                "_write_all_roots",
                side_effect=RuntimeError("write failed"),
            ),
            patch("app.configuration.v2.manager.logger") as mock_logger,
        ):
            # 触发去抖保存（无需注册 root，直接 patch _write_all_roots）
            config_manager.schedule_debounced_save()
            handle = config_manager._save_handle
            self.assertIsNotNone(handle)

            # 等待 debounce (0.05s) + save 执行完成
            await asyncio.sleep(0.3)

            assert handle is not None
            self.assertTrue(handle.done())
            # consume_failure 已消费异常 → logger.error 被调用
            mock_logger.error.assert_called_once()

        # _save_handle 已被 task finally 清理
        self.assertIsNone(config_manager._save_handle)

    # ── 7. flush() 持久化失败传播 ConfigAggregateError ──

    async def test_flush_raises_on_persistence_failure(self) -> None:
        """patch ``_write_all_roots`` 抛 ConfigAggregateError → flush() 传播。"""
        error = ConfigAggregateError([RuntimeError("root write failed")])

        with patch.object(
            config_manager,
            "_write_all_roots",
            side_effect=error,
        ):
            with self.assertRaises(ConfigAggregateError):
                await config_manager.flush()
