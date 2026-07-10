#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.task.Ok import runtime
from app.task.Ok.common.runtime_lock import get_ok_script_root_lock
from app.task.Ok.providers import detect_ok_script_provider
from app.task.Ok.providers.okef import OKEF_PROVIDER
from app.task.Okww import AutoProxy as okww_runtime


class OkScriptIsolationTest(unittest.IsolatedAsyncioTestCase):
    def test_unknown_pyappify_resource_does_not_fall_back_to_old_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "pyappify.yml").write_text("name: ok-unknown\n", encoding="utf-8")
            (root / OKEF_PROVIDER.exe_name).touch()
            (root / OKEF_PROVIDER.config_dir).mkdir(parents=True)

            self.assertIsNone(detect_ok_script_provider(root, "ok-ef"))

    async def test_same_root_lock_serializes_runtime_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            first_lock = get_ok_script_root_lock(root)
            second_lock = get_ok_script_root_lock(root)
            acquired = asyncio.Event()

            async def wait_for_lock() -> None:
                async with second_lock:
                    acquired.set()

            self.assertIs(first_lock, second_lock)
            await first_lock.acquire()
            waiter = asyncio.create_task(wait_for_lock())
            await asyncio.sleep(0)
            self.assertFalse(acquired.is_set())

            first_lock.release()
            await waiter
            self.assertTrue(acquired.is_set())

    async def test_config_write_back_failure_is_not_silenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            task = object.__new__(runtime.OkScriptAutoProxyTask)
            task.script_config_path = root / "script-config"
            task.mas_config_dir = root / "mas-config"
            task.provider = OKEF_PROVIDER

            with patch(
                "app.task.Ok.runtime._replace_tree",
                side_effect=OSError("write back failed"),
            ):
                with self.assertRaisesRegex(OSError, "write back failed"):
                    await task.update_config()

    async def test_final_task_releases_root_lock_after_cleanup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            lock = get_ok_script_root_lock(Path(tmp_dir))
            await lock.acquire()

            task = object.__new__(runtime.OkScriptAutoProxyTask)
            task.script_root_lock = lock
            task.script_root_lock_acquired = True
            task._finalize_task = AsyncMock(side_effect=OSError("cleanup failed"))

            with self.assertRaisesRegex(OSError, "cleanup failed"):
                await task.final_task()

            self.assertFalse(lock.locked())

    async def test_legacy_okww_final_task_releases_root_lock_after_cleanup_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            lock = get_ok_script_root_lock(Path(tmp_dir))
            await lock.acquire()

            task = object.__new__(okww_runtime.AutoProxyTask)
            task.script_root_lock = lock
            task.script_root_lock_acquired = True
            task._finalize_task = AsyncMock(side_effect=OSError("cleanup failed"))

            with self.assertRaisesRegex(OSError, "cleanup failed"):
                await task.final_task()

            self.assertFalse(lock.locked())
