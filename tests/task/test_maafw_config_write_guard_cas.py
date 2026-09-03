import asyncio
import hashlib
import json
import tempfile
import unittest
import uuid
from pathlib import Path

from app.task.MaaFW.tools.config_write_guard import (
    MaaFWConfigCorruptionError,
    MaaFWConfigSnapshot,
    atomic_write_maafw_config,
    maafw_config_write_scope,
    read_maafw_config_snapshot,
)


def expected_revision(payload: dict) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class MaafwConfigWriteGuardCasTest(unittest.TestCase):
    def test_read_snapshot_requires_json_object_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "config.json"
            with self.assertRaises(MaaFWConfigCorruptionError):
                read_maafw_config_snapshot(missing)

            list_file = Path(temp_dir) / "list.json"
            list_file.write_text("[1, 2, 3]", encoding="utf-8")
            with self.assertRaises(MaaFWConfigCorruptionError):
                read_maafw_config_snapshot(list_file)

    def test_atomic_write_creates_parent_dirs_and_matches_snapshot_revision(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "nested" / "config.json"
            payload = {"b": 2, "a": 1}
            snapshot = atomic_write_maafw_config(target, payload)

            self.assertIsInstance(snapshot, MaaFWConfigSnapshot)
            self.assertEqual(snapshot.revision, expected_revision(payload))
            reread = read_maafw_config_snapshot(target)
            self.assertEqual(reread.revision, snapshot.revision)
            self.assertEqual(reread.payload, payload)

    def test_cas_write_succeeds_on_fresh_revision_and_fails_when_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "config.json"
            first = atomic_write_maafw_config(target, {"value": 1})
            second = atomic_write_maafw_config(
                target,
                {"value": 2},
                expected_revision=first.revision,
            )
            self.assertEqual(second.payload, {"value": 2})

            with self.assertRaises(RuntimeError) as ctx:
                atomic_write_maafw_config(
                    target,
                    {"value": 3},
                    expected_revision=first.revision,
                )
            self.assertIn("版本已变化", str(ctx.exception))
            self.assertEqual(
                read_maafw_config_snapshot(target).payload,
                {"value": 2},
            )

    def test_atomic_write_rejects_non_dict_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "config.json"
            with self.assertRaises(TypeError):
                atomic_write_maafw_config(target, ["not", "a", "dict"])

    def test_journal_records_same_serialized_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "config.json"
            atomic_write_maafw_config(target, {"value": 7}, journal=True)

            journal = Path(f"{target}.journal")
            self.assertTrue(journal.exists())
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                journal.read_text(encoding="utf-8"),
            )

    def test_atomic_write_never_overwrites_corrupted_live_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "config.json"
            target.write_text("{broken-json", encoding="utf-8")

            with self.assertRaises(MaaFWConfigCorruptionError):
                atomic_write_maafw_config(target, {"value": 1})

            self.assertEqual(target.read_text(encoding="utf-8"), "{broken-json")

    def test_write_scope_serializes_concurrent_writers(self) -> None:
        script_id = f"scope-{uuid.uuid4().hex}"

        async def scenario() -> list[str]:
            events: list[str] = []

            async def worker(name: str) -> None:
                async with maafw_config_write_scope(script_id):
                    events.append(f"{name}-in")
                    await asyncio.sleep(0.01)
                    events.append(f"{name}-out")

            await asyncio.gather(worker("a"), worker("b"))
            return events

        events = asyncio.run(scenario())
        for name in ("a", "b"):
            enter = events.index(f"{name}-in")
            leave = events.index(f"{name}-out")
            self.assertEqual(leave - enter, 1)

    def test_write_scope_reentrant_for_same_script_id(self) -> None:
        script_id = f"scope-{uuid.uuid4().hex}"
        entered: list[str] = []

        async def scenario() -> None:
            async with maafw_config_write_scope(script_id):
                async with maafw_config_write_scope(script_id):
                    entered.append("inner")
                entered.append("middle")
            entered.append("outer")

        asyncio.run(scenario())
        self.assertEqual(entered, ["inner", "middle", "outer"])

    def test_fail_if_busy_rejects_second_writer(self) -> None:
        script_id = f"scope-{uuid.uuid4().hex}"
        outcomes: dict[str, object] = {}

        async def scenario() -> None:
            entered = asyncio.Event()
            released = asyncio.Event()

            async def holder() -> None:
                async with maafw_config_write_scope(script_id):
                    entered.set()
                    await released.wait()

            async def contender() -> None:
                await entered.wait()
                try:
                    async with maafw_config_write_scope(script_id, fail_if_busy=True):
                        outcomes["entered"] = True
                except RuntimeError as exc:
                    outcomes["error"] = str(exc)
                finally:
                    released.set()

            await asyncio.gather(holder(), contender())

        asyncio.run(scenario())
        self.assertNotIn("entered", outcomes)
        self.assertIn("error", outcomes)
        self.assertIn("正在被其他操作修改", str(outcomes["error"]))


if __name__ == "__main__":
    unittest.main()
