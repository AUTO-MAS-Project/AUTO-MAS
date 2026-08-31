"""`automas_maafw_runner.worker_registry` 的关停语义回归。

worker 用假对象替身，**不起任何真实子进程**（测试纪律）。
"""

import asyncio
import unittest

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_runner.worker_registry import (
    GLOBAL_MAAFW_WORKER_REGISTRY,
    MaaFWWorkerRegistry,
    MaaFWWorkerShutdownReport,
)


class FakeWorker:
    """subprocess.Popen 的最小替身：terminate/kill 只改 returncode。"""

    def __init__(
        self, *, ignores_terminate: bool = False, raises: Exception | None = None
    ):
        self.returncode: int | None = None
        self.terminate_calls = 0
        self.kill_calls = 0
        self._ignores_terminate = ignores_terminate
        self._raises = raises

    def terminate(self) -> None:
        self.terminate_calls += 1
        if self._raises is not None:
            raise self._raises
        if not self._ignores_terminate:
            self.returncode = -15

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9

    def wait(self, timeout: float | None = None):
        if self.returncode is None:
            raise TimeoutError("worker still running")
        return self.returncode


class WorkerRegistryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.registry = MaaFWWorkerRegistry()

    def test_register_returns_an_id_and_counts_the_worker(self) -> None:
        worker = FakeWorker()
        worker_id = self.registry.register(worker)
        self.assertIsNotNone(worker_id)
        self.assertEqual(self.registry.active_count, 1)
        self.assertEqual(worker.terminate_calls, 0)

    def test_already_exited_worker_is_not_retained(self) -> None:
        worker = FakeWorker()
        worker.returncode = 0
        self.assertIsNone(self.registry.register(worker))
        self.assertEqual(self.registry.active_count, 0)

    def test_unregister_is_idempotent_and_none_safe(self) -> None:
        worker_id = self.registry.register(FakeWorker())
        self.registry.unregister(worker_id)
        self.registry.unregister(worker_id)
        self.registry.unregister(None)
        self.assertEqual(self.registry.active_count, 0)

    async def test_shutdown_terminates_and_clears(self) -> None:
        workers = [FakeWorker() for _ in range(3)]
        for worker in workers:
            self.registry.register(worker)

        report = await self.registry.shutdown_all()

        self.assertIsInstance(report, MaaFWWorkerShutdownReport)
        self.assertEqual(report.requested, 3)
        self.assertEqual(report.terminated, 3)
        self.assertEqual(report.killed, 0)
        self.assertEqual(report.errors, ())
        self.assertEqual(self.registry.active_count, 0)
        self.assertTrue(all(worker.terminate_calls == 1 for worker in workers))

    async def test_shutdown_escalates_to_kill(self) -> None:
        stubborn = FakeWorker(ignores_terminate=True)
        self.registry.register(stubborn)

        report = await self.registry.shutdown_all(graceful_timeout_seconds=0.01)

        self.assertEqual(report.requested, 1)
        self.assertEqual(report.killed, 1)
        self.assertEqual(report.terminated, 0)
        self.assertEqual(stubborn.kill_calls, 1)

    async def test_shutdown_records_errors_without_aborting_the_sweep(self) -> None:
        # 一个不合作的 worker 不得阻断宿主 teardown
        broken = FakeWorker(raises=RuntimeError("boom"))
        healthy = FakeWorker()
        self.registry.register(broken)
        self.registry.register(healthy)

        report = await self.registry.shutdown_all()

        self.assertEqual(report.requested, 2)
        self.assertEqual(report.terminated, 1)
        self.assertEqual(len(report.errors), 1)
        self.assertIn("boom", report.errors[0])
        self.assertEqual(self.registry.active_count, 0)

    async def test_vanished_worker_counts_as_terminated_without_error(self) -> None:
        # 进程在 terminate 之前就已经没了：ProcessLookupError + returncode 已回填
        vanished = FakeWorker(raises=ProcessLookupError())
        self.registry.register(vanished)
        vanished.returncode = -15

        report = await self.registry.shutdown_all()

        self.assertEqual(report.errors, ())
        self.assertEqual(report.terminated, 1)
        self.assertEqual(vanished.kill_calls, 0)

    async def test_registration_after_shutdown_is_refused_and_terminated(self) -> None:
        await self.registry.shutdown_all()
        self.assertFalse(self.registry.accepting_workers)

        late = FakeWorker()
        # 与 teardown 并发启动的 worker 不得因为快照已取而幸存
        self.assertIsNone(self.registry.register(late))
        self.assertEqual(late.terminate_calls, 1)
        self.assertEqual(self.registry.active_count, 0)

    async def test_reopen_allows_registration_again(self) -> None:
        await self.registry.shutdown_all()
        self.registry.reopen()
        self.assertTrue(self.registry.accepting_workers)
        self.assertIsNotNone(self.registry.register(FakeWorker()))

    async def test_shutdown_on_an_empty_registry_is_a_noop(self) -> None:
        report = await self.registry.shutdown_all()
        self.assertEqual(
            (report.requested, report.terminated, report.killed, report.errors),
            (0, 0, 0, ()),
        )

    async def test_concurrent_registration_is_serialized(self) -> None:
        workers = [FakeWorker() for _ in range(20)]

        await asyncio.gather(
            *(asyncio.to_thread(self.registry.register, worker) for worker in workers)
        )
        self.assertEqual(self.registry.active_count, 20)


class GlobalRegistryTest(unittest.TestCase):
    def test_module_exposes_a_shared_registry(self) -> None:
        self.assertIsInstance(GLOBAL_MAAFW_WORKER_REGISTRY, MaaFWWorkerRegistry)
        # 全局注册表默认接受 worker；本文件不改动它的状态
        self.assertTrue(GLOBAL_MAAFW_WORKER_REGISTRY.accepting_workers)


if __name__ == "__main__":
    unittest.main()
