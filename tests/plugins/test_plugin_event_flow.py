import asyncio
import unittest
from typing import Any, Callable

from app.core.task_manager import Task, TaskInfo
from app.models.task import ScriptItem
from app.plugins import PluginEventNames, PluginManager


class PluginEventFlowTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.listener_ids: list[tuple[str, str]] = []

    async def asyncTearDown(self) -> None:
        for event, listener_id in self.listener_ids:
            PluginManager.off(event, listener_id=listener_id)

    def _listen_once(
        self,
        event: str,
        handler: Callable[[dict[str, Any]], Any],
    ) -> None:
        listener_id = PluginManager.on(event, handler, once=True)
        self.listener_ids.append((event, listener_id))

    async def test_task_start_reaches_plugin_event_listener(self) -> None:
        received: list[dict[str, Any]] = []
        received_event = asyncio.Event()

        async def handler(payload: dict[str, Any]) -> None:
            received.append(payload)
            received_event.set()

        self._listen_once(PluginEventNames.TASK_START, handler)

        task_info = TaskInfo(
            mode="ScriptConfig",
            task_id="task-1",
            queue_id=None,
            script_id="script-1",
            user_id="user-1",
            script_list=[
                ScriptItem(
                    script_id="script-1",
                    name="Demo Script",
                    status="等待",
                )
            ],
        )

        await Task(task_info)._emit_task_start()
        await asyncio.wait_for(received_event.wait(), timeout=1)

        payload = received[0]
        self.assertEqual(payload["event"], PluginEventNames.TASK_START)
        self.assertEqual(payload["source"], "core.task_manager")
        self.assertEqual(payload["data"]["task_id"], "task-1")
        self.assertEqual(payload["data"]["script_id"], "script-1")
        self.assertEqual(payload["data"]["primary_script_name"], "Demo Script")
        self.assertIn("stop_task", payload["data"]["actions"])


if __name__ == "__main__":
    unittest.main()
