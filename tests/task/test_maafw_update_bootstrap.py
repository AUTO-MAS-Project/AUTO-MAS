import json
import tempfile
import unittest
from pathlib import Path

import app.core  # noqa: F401

from app.task.MaaFW.tools.core.automas_maafw_project_update.apply import (
    MANIFEST_NAME,
    _project_state_dir,
    has_trusted_update_baseline,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update.state import (
    UpdateOperationStore,
)


class TrustedBaselineProbeTest(unittest.TestCase):
    """「有没有可信更新基线」的只读探测。

    差量包在 _validate_plan_base 里必须能对上 projectFingerprint；从未经 MAS
    更新过的项目没有这份 manifest，差量包一定被拒——即「首次更新永远装不上」
    的自举死锁。探测为 False 时，发现阶段改为请求全量包。
    """

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.operation_root = self.root / "ops"
        self.operation_root.mkdir()

    def _state_dir(self) -> Path:
        store = UpdateOperationStore.create(root=self.operation_root)
        return _project_state_dir(self.project.resolve(), store, create=True)

    def test_missing_manifest_has_no_baseline(self) -> None:
        self.assertFalse(
            has_trusted_update_baseline(
                self.project, operation_root=self.operation_root
            )
        )

    def test_probe_does_not_create_directories(self) -> None:
        before = sorted(p.name for p in self.operation_root.iterdir())
        has_trusted_update_baseline(self.project, operation_root=self.operation_root)
        # 只读：探测本身不得在项目状态根下留下目录。
        state_root = self.operation_root.parent / "maafw_project_state"
        self.assertFalse(state_root.exists())
        self.assertEqual(sorted(p.name for p in self.operation_root.iterdir()), before)

    def test_manifest_with_fingerprint_is_a_baseline(self) -> None:
        state_dir = self._state_dir()
        (state_dir / MANIFEST_NAME).write_text(
            json.dumps({"schemaVersion": 1, "projectFingerprint": "abc123"}),
            encoding="utf-8",
        )
        self.assertTrue(
            has_trusted_update_baseline(
                self.project, operation_root=self.operation_root
            )
        )

    def test_manifest_without_fingerprint_is_not_a_baseline(self) -> None:
        state_dir = self._state_dir()
        for payload in ({"schemaVersion": 1}, {"projectFingerprint": "   "}):
            with self.subTest(payload=payload):
                (state_dir / MANIFEST_NAME).write_text(
                    json.dumps(payload), encoding="utf-8"
                )
                self.assertFalse(
                    has_trusted_update_baseline(
                        self.project, operation_root=self.operation_root
                    )
                )

    def test_corrupt_manifest_falls_back_to_no_baseline(self) -> None:
        # 探测失败一律按「没有基线」：要全量包最多多下点数据，
        # 要差量包却没有基线则是必然失败。
        state_dir = self._state_dir()
        (state_dir / MANIFEST_NAME).write_text("{ not json", encoding="utf-8")
        self.assertFalse(
            has_trusted_update_baseline(
                self.project, operation_root=self.operation_root
            )
        )


if __name__ == "__main__":
    unittest.main()
