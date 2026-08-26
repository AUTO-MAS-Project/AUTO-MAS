import asyncio
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.task_manager import (
    Task,
    TaskInfo,
    _ScriptTaskReservations,
    _TaskManager,
)
from app.models.task import ScriptItem


class ScriptTaskReservationsTest(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_direct_task_is_rejected_before_execute(self) -> None:
        manager = _TaskManager()
        script_uid = uuid.uuid4()
        script_config = SimpleNamespace(
            is_locked=False,
            get=lambda *_: "测试脚本",
        )

        def close_coroutine(coroutine):
            coroutine.close()
            return SimpleNamespace()

        with (
            patch(
                "app.core.task_manager.Config.ScriptConfig",
                {script_uid: script_config},
            ),
            patch.object(Task, "execute"),
            patch(
                "app.core.task_manager.asyncio.create_task",
                side_effect=close_coroutine,
            ),
        ):
            await manager.add_task("ScriptConfig", str(script_uid))
            with self.assertRaisesRegex(RuntimeError, "已在运行"):
                await manager.add_task("ScriptConfig", str(script_uid))

    async def test_execute_failure_releases_direct_task_reservation(self) -> None:
        manager = _TaskManager()
        script_uid = uuid.uuid4()
        script_config = SimpleNamespace(
            is_locked=False,
            get=lambda *_: "测试脚本",
        )

        with (
            patch(
                "app.core.task_manager.Config.ScriptConfig",
                {script_uid: script_config},
            ),
            patch.object(Task, "execute", side_effect=RuntimeError("start failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "start failed"):
                await manager.add_task("ScriptConfig", str(script_uid))

        self.assertTrue(
            manager._script_reservations.try_acquire(script_uid, "next-owner")
        )

    async def test_cancel_before_first_task_frame_releases_reservation(self) -> None:
        manager = _TaskManager()
        script_uid = uuid.uuid4()
        script_config = SimpleNamespace(
            is_locked=False,
            get=lambda *_: "测试脚本",
        )

        with patch(
            "app.core.task_manager.Config.ScriptConfig",
            {script_uid: script_config},
        ):
            task_uid = await manager.add_task("ScriptConfig", str(script_uid))
            task = manager.task_handler[task_uid]
            self.assertTrue(task.cancel())
            await asyncio.wait_for(task.accomplish.wait(), timeout=1)

            for _ in range(10):
                if manager._script_reservations.try_acquire(script_uid, "next-owner"):
                    break
                await asyncio.sleep(0)
            else:
                self.fail("任务首帧前取消后未释放脚本占用")

    async def test_queue_task_respects_existing_reservation(self) -> None:
        reservations = _ScriptTaskReservations()
        script_uid = uuid.uuid4()
        self.assertTrue(reservations.try_acquire(script_uid, "other-task"))
        task_info = TaskInfo(
            mode="ScriptConfig",
            task_id=str(uuid.uuid4()),
            queue_id=str(uuid.uuid4()),
            script_id=None,
            user_id=None,
            script_list=[
                ScriptItem(
                    script_id=str(script_uid),
                    name="测试脚本",
                    status="等待",
                )
            ],
        )
        task = Task(task_info, reservations)
        task.prepare = AsyncMock()

        with (
            patch(
                "app.core.task_manager.Config.ScriptConfig",
                {script_uid: SimpleNamespace(is_locked=False)},
            ),
            patch(
                "app.core.task_manager.Config.send_websocket_message",
                new_callable=AsyncMock,
            ),
        ):
            await task.main_task()

        self.assertEqual(task_info.script_list[0].status, "跳过")
        self.assertFalse(reservations.release(script_uid, task_info.task_id))
        self.assertTrue(reservations.try_acquire(script_uid, "other-task"))

    async def test_late_release_cannot_clear_new_owner(self) -> None:
        reservations = _ScriptTaskReservations()
        script_uid = uuid.uuid4()

        self.assertTrue(reservations.try_acquire(script_uid, "first"))
        self.assertTrue(reservations.release(script_uid, "first"))
        self.assertTrue(reservations.try_acquire(script_uid, "second"))

        self.assertFalse(reservations.release(script_uid, "first"))
        self.assertTrue(reservations.try_acquire(script_uid, "second"))

    async def test_release_only_clears_the_requested_script(self) -> None:
        reservations = _ScriptTaskReservations()
        first_script_uid = uuid.uuid4()
        second_script_uid = uuid.uuid4()

        self.assertTrue(reservations.try_acquire(first_script_uid, "owner"))
        self.assertTrue(reservations.try_acquire(second_script_uid, "owner"))
        self.assertTrue(reservations.release(first_script_uid, "owner"))

        self.assertTrue(reservations.try_acquire(first_script_uid, "next-owner"))
        self.assertFalse(reservations.try_acquire(second_script_uid, "next-owner"))

    async def test_release_keeps_src_root_shared_by_owner_scripts(self) -> None:
        reservations = _ScriptTaskReservations()
        first_script_uid = uuid.uuid4()
        second_script_uid = uuid.uuid4()
        shared_root = Path("SRC").resolve()

        self.assertTrue(
            reservations.try_acquire(
                first_script_uid,
                "owner",
                src_root_path=shared_root,
            )
        )
        self.assertTrue(
            reservations.try_acquire(
                second_script_uid,
                "owner",
                src_root_path=shared_root,
            )
        )
        self.assertTrue(reservations.release(first_script_uid, "owner"))

        self.assertFalse(
            reservations.try_acquire(
                uuid.uuid4(),
                "next-owner",
                src_root_path=shared_root,
            )
        )
        self.assertTrue(reservations.release(second_script_uid, "owner"))
        self.assertTrue(
            reservations.try_acquire(
                uuid.uuid4(),
                "next-owner",
                src_root_path=shared_root,
            )
        )

    async def test_different_scripts_cannot_share_src_root(self) -> None:
        reservations = _ScriptTaskReservations()
        first_script_uid = uuid.uuid4()
        second_script_uid = uuid.uuid4()
        shared_root = Path("SRC").resolve()

        self.assertTrue(
            reservations.try_acquire(
                first_script_uid,
                "first",
                src_root_path=shared_root,
            )
        )
        self.assertFalse(
            reservations.try_acquire(
                second_script_uid,
                "second",
                src_root_path=shared_root,
            )
        )

        self.assertTrue(reservations.release(first_script_uid, "first"))
        self.assertTrue(
            reservations.try_acquire(
                second_script_uid,
                "second",
                src_root_path=shared_root,
            )
        )

    async def test_nested_src_roots_are_mutually_exclusive(self) -> None:
        reservations = _ScriptTaskReservations()
        parent_script_uid = uuid.uuid4()
        child_script_uid = uuid.uuid4()
        parent_root = Path("SRC-Suite").resolve()
        child_root = parent_root / "OtherSRC"

        self.assertTrue(
            reservations.try_acquire(
                parent_script_uid,
                "parent",
                src_root_path=parent_root,
            )
        )
        self.assertFalse(
            reservations.try_acquire(
                child_script_uid,
                "child",
                src_root_path=child_root,
            )
        )

    async def test_same_owner_retains_old_and_new_src_roots(self) -> None:
        reservations = _ScriptTaskReservations()
        script_uid = uuid.uuid4()
        other_script_uid = uuid.uuid4()
        old_root = Path("OldSRC").resolve()
        new_root = Path("NewSRC").resolve()

        self.assertTrue(
            reservations.try_acquire(
                script_uid,
                "owner",
                src_root_path=old_root,
            )
        )
        self.assertTrue(
            reservations.try_acquire(
                script_uid,
                "owner",
                src_root_path=new_root,
            )
        )
        self.assertFalse(
            reservations.try_acquire(
                other_script_uid,
                "other",
                src_root_path=old_root,
            )
        )
        self.assertFalse(
            reservations.try_acquire(
                other_script_uid,
                "other",
                src_root_path=new_root,
            )
        )

        self.assertTrue(reservations.release(script_uid, "owner"))
        self.assertTrue(
            reservations.try_acquire(
                other_script_uid,
                "other",
                src_root_path=new_root,
            )
        )


if __name__ == "__main__":
    unittest.main()
