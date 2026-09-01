import asyncio
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from app.utils.LogMonitor import LogMonitor


class LogMonitorPathTest(unittest.IsolatedAsyncioTestCase):
    async def test_monitor_follows_resolved_path_and_drains_old_file(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_path = root / "old.log"
            new_path = root / "new.log"
            now = datetime.now()
            old_line = now.strftime("%Y-%m-%d %H:%M:%S.%f") + " old"
            old_path.write_text(old_line + "\n")

            old_seen = asyncio.Event()
            new_seen = asyncio.Event()

            async def check_log(log_content: list[str], latest_time: datetime) -> None:
                if any("old" in line for line in log_content):
                    old_seen.set()
                if any("new" in line for line in log_content):
                    new_seen.set()

            monitor = LogMonitor((0, 26), "%Y-%m-%d %H:%M:%S.%f", check_log)
            target = old_path

            def resolve_path() -> Path:
                return target

            task = asyncio.create_task(
                monitor.monitor_file(resolve_path, now - timedelta(minutes=1))
            )

            try:
                await asyncio.wait_for(old_seen.wait(), timeout=3)

                new_line = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f") + " new"
                new_path.write_text(new_line + "\n")
                target = new_path
                await asyncio.wait_for(new_seen.wait(), timeout=3)

                self.assertEqual(
                    monitor.log_contents, [old_line + "\n", new_line + "\n"]
                )
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
