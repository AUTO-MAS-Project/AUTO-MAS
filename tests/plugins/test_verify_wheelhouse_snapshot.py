#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""verify_wheelhouse_snapshot.py 的回归测试。

覆盖：
- snapshot 与实际 wheelhouse 一致时通过
- snapshot 缺失、manifest 缺失、runtime-lock 缺失时抛出
- wheel_count 漂移、plugin_distribution_count 漂移、entry_point_count 漂移时抛出
- manifest_sha256 漂移、runtime_lock_sha256 漂移时抛出
- schema_version、Core distribution 版本漂移时抛出
- 非法 SHA-256 字段时抛出
- 可显式校验仓库外的构建/冻结 wheelhouse
"""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from verify_wheelhouse_snapshot import (  # noqa: E402
    SnapshotDriftError,
    _count_wheels,
    _sha256_file,
    verify_wheelhouse_snapshot,
)


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_wheel(wheels_dir: Path, name: str) -> None:
    wheels_dir.mkdir(parents=True, exist_ok=True)
    (wheels_dir / name).write_bytes(b"fake wheel content")


def _build_minimal_repo(tmp_root: Path, *, wheel_count: int = 2) -> dict[str, Path]:
    """构造一个最小可用的宿主根目录用于测试。"""
    tmp_root.mkdir(parents=True, exist_ok=True)
    (tmp_root / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")

    wheels_dir = tmp_root / "plugins" / "wheels"
    wheels_dir.mkdir(parents=True, exist_ok=True)
    for index in range(wheel_count):
        _make_wheel(wheels_dir, f"fake-{index}-1.0.0-py3-none-any.whl")

    manifest = {
        "schema_version": 3,
        "artifact_scope": "complete-windows-x64-runtime-wheelhouse",
        "wheels": [],
        "plugins": [],
        "runtime_lock": {
            "filename": "runtime-lock.json",
            "size_bytes": 0,
            "sha256": "0" * 64,
        },
    }
    manifest_path = wheels_dir / "manifest.json"
    _write_json(manifest_path, manifest)

    runtime_lock = {
        "schema_version": 1,
        "plugins": [
            {"scope": "plugin", "distribution": "auto-mas-core", "version": "6.0.0a1"},
            {"scope": "plugin", "distribution": "plugin-1", "version": "1.0.0"},
            {"scope": "plugin", "distribution": "plugin-2", "version": "1.0.0"},
        ],
        "host_runtime": [],
        "install_contract": {"protected_host_distributions": []},
        "expected_plugin_entry_points": [
            {"group": "auto_mas.plugins", "name": f"plugin_{i}"}
            for i in range(2)
        ],
    }
    runtime_lock_path = wheels_dir / "runtime-lock.json"
    _write_json(runtime_lock_path, runtime_lock)

    manifest_sha = _sha256_file(manifest_path)
    runtime_lock_sha = _sha256_file(runtime_lock_path)

    snapshot = {
        "schema_version": 1,
        "snapshot_id": "test-snapshot",
        "version": "v6.0.0-test",
        "generated_at": "2026-07-23T00:00:00.000Z",
        "deployment_mode": "bundled-snapshot",
        "required_paths": ["app"],
        "wheel_manifest": "plugins/wheels/manifest.json",
        "wheelhouse_contract": {
            "manifest_schema_version": 3,
            "runtime_lock_schema_version": 1,
            "wheel_count": wheel_count,
            "plugin_distribution_count": 3,
            "plugin_entry_point_count": 2,
            "core_distribution_version": "6.0.0a1",
            "manifest_sha256": manifest_sha,
            "runtime_lock_sha256": runtime_lock_sha,
        },
        "update_policy": "test",
    }
    snapshot_path = tmp_root / "res" / "integration-snapshot.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(snapshot_path, snapshot)

    return {
        "root": tmp_root,
        "snapshot": snapshot_path,
        "wheels": wheels_dir,
        "manifest": manifest_path,
        "runtime_lock": runtime_lock_path,
    }


class VerifyWheelhouseSnapshotTest(unittest.TestCase):
    def test_consistent_snapshot_passes(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = _build_minimal_repo(Path(tmp), wheel_count=2)
            result = verify_wheelhouse_snapshot(paths["root"])
            self.assertEqual(result["wheel_count"], 2)
            self.assertEqual(result["plugin_distribution_count"], 3)
            self.assertEqual(result["entry_point_count"], 2)
            self.assertEqual(result["core_distribution_version"], "6.0.0a1")

    def test_missing_snapshot_raises(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            (tmp_root / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
            with self.assertRaisesRegex(SnapshotDriftError, "integration-snapshot.json 缺失"):
                verify_wheelhouse_snapshot(tmp_root)

    def test_missing_manifest_raises(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = _build_minimal_repo(Path(tmp))
            paths["manifest"].unlink()
            with self.assertRaisesRegex(SnapshotDriftError, "manifest.json 缺失"):
                verify_wheelhouse_snapshot(paths["root"])

    def test_missing_runtime_lock_raises(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = _build_minimal_repo(Path(tmp))
            paths["runtime_lock"].unlink()
            with self.assertRaisesRegex(SnapshotDriftError, "runtime-lock.json 缺失"):
                verify_wheelhouse_snapshot(paths["root"])

    def test_wheel_count_drift_detected(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = _build_minimal_repo(Path(tmp), wheel_count=2)
            _make_wheel(paths["wheels"], "extra-1.0.0-py3-none-any.whl")
            with self.assertRaisesRegex(SnapshotDriftError, "wheel_count 期望 2, 实际 3"):
                verify_wheelhouse_snapshot(paths["root"])

    def test_plugin_distribution_count_drift_detected(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = _build_minimal_repo(Path(tmp))
            snapshot = json.loads(paths["snapshot"].read_text(encoding="utf-8"))
            snapshot["wheelhouse_contract"]["plugin_distribution_count"] = 99
            _write_json(paths["snapshot"], snapshot)
            with self.assertRaisesRegex(SnapshotDriftError, "plugin_distribution_count 期望 99"):
                verify_wheelhouse_snapshot(paths["root"])

    def test_entry_point_count_drift_detected(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = _build_minimal_repo(Path(tmp))
            snapshot = json.loads(paths["snapshot"].read_text(encoding="utf-8"))
            snapshot["wheelhouse_contract"]["plugin_entry_point_count"] = 99
            _write_json(paths["snapshot"], snapshot)
            with self.assertRaisesRegex(SnapshotDriftError, "plugin_entry_point_count 期望 99"):
                verify_wheelhouse_snapshot(paths["root"])

    def test_manifest_sha256_drift_detected(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = _build_minimal_repo(Path(tmp))
            snapshot = json.loads(paths["snapshot"].read_text(encoding="utf-8"))
            snapshot["wheelhouse_contract"]["manifest_sha256"] = "a" * 64
            _write_json(paths["snapshot"], snapshot)
            with self.assertRaisesRegex(SnapshotDriftError, "manifest_sha256 期望"):
                verify_wheelhouse_snapshot(paths["root"])

    def test_runtime_lock_sha256_drift_detected(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = _build_minimal_repo(Path(tmp))
            snapshot = json.loads(paths["snapshot"].read_text(encoding="utf-8"))
            snapshot["wheelhouse_contract"]["runtime_lock_sha256"] = "b" * 64
            _write_json(paths["snapshot"], snapshot)
            with self.assertRaisesRegex(SnapshotDriftError, "runtime_lock_sha256 期望"):
                verify_wheelhouse_snapshot(paths["root"])

    def test_invalid_sha256_field_rejected(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = _build_minimal_repo(Path(tmp))
            snapshot = json.loads(paths["snapshot"].read_text(encoding="utf-8"))
            snapshot["wheelhouse_contract"]["manifest_sha256"] = "not-a-hash"
            _write_json(paths["snapshot"], snapshot)
            with self.assertRaisesRegex(SnapshotDriftError, "manifest_sha256 非法"):
                verify_wheelhouse_snapshot(paths["root"])

    def test_manifest_schema_drift_detected(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = _build_minimal_repo(Path(tmp))
            snapshot = json.loads(paths["snapshot"].read_text(encoding="utf-8"))
            snapshot["wheelhouse_contract"]["manifest_schema_version"] = 99
            _write_json(paths["snapshot"], snapshot)
            with self.assertRaisesRegex(SnapshotDriftError, "manifest.schema_version 期望 99"):
                verify_wheelhouse_snapshot(paths["root"])

    def test_core_distribution_version_drift_detected(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = _build_minimal_repo(Path(tmp))
            runtime_lock = json.loads(paths["runtime_lock"].read_text(encoding="utf-8"))
            runtime_lock["plugins"][0]["version"] = "5.4.0b1"
            _write_json(paths["runtime_lock"], runtime_lock)

            snapshot = json.loads(paths["snapshot"].read_text(encoding="utf-8"))
            snapshot["wheelhouse_contract"]["runtime_lock_sha256"] = _sha256_file(
                paths["runtime_lock"]
            )
            _write_json(paths["snapshot"], snapshot)

            with self.assertRaisesRegex(
                SnapshotDriftError,
                "core_distribution_version 期望 6.0.0a1, 实际 5.4.0b1",
            ):
                verify_wheelhouse_snapshot(paths["root"])

    def test_explicit_external_wheelhouse_is_supported(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            paths = _build_minimal_repo(tmp_root / "repo")
            external = tmp_root / "frozen" / "wheels"
            external.parent.mkdir(parents=True, exist_ok=True)
            paths["wheels"].replace(external)

            result = verify_wheelhouse_snapshot(
                paths["root"],
                wheelhouse=external,
            )
            self.assertEqual(result["wheels_dir"], str(external.resolve()))

    def test_missing_wheelhouse_contract_raises(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = _build_minimal_repo(Path(tmp))
            snapshot = json.loads(paths["snapshot"].read_text(encoding="utf-8"))
            snapshot.pop("wheelhouse_contract")
            _write_json(paths["snapshot"], snapshot)
            with self.assertRaisesRegex(SnapshotDriftError, "缺少 wheelhouse_contract"):
                verify_wheelhouse_snapshot(paths["root"])

    def test_count_wheels_ignores_non_wheel_files(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            wheels_dir = Path(tmp) / "wheels"
            wheels_dir.mkdir()
            (wheels_dir / "a.whl").write_bytes(b"x")
            (wheels_dir / "b.whl").write_bytes(b"x")
            (wheels_dir / "README.md").write_text("not a wheel", encoding="utf-8")
            (wheels_dir / "manifest.json").write_text("{}", encoding="utf-8")
            self.assertEqual(_count_wheels(wheels_dir), 2)

    def test_count_wheels_missing_dir_returns_zero(self) -> None:
        self.assertEqual(_count_wheels(Path("/nonexistent/path/that/should/not/exist")), 0)


class VerifyWheelhouseSnapshotPyprojectPinTest(unittest.TestCase):
    """Lane 13: pyproject plugin-bootstrap pin ↔ runtime-lock plugin version 一致性。"""

    def _build_repo_with_bootstrap_section(
        self, tmp_root: Path, *, bootstrap_packages_toml: str
    ) -> dict[str, Path]:
        """构造一个含 [tool.auto-mas.plugin-bootstrap] 的最小宿主根目录。"""
        tmp_root.mkdir(parents=True, exist_ok=True)
        pyproject_content = (
            "[project]\n"
            'name = "test"\n'
            'version = "0.1.0"\n'
            "\n"
            "[tool.auto-mas.plugin-bootstrap]\n"
            f"packages = [\n{bootstrap_packages_toml}\n]\n"
        )
        (tmp_root / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")

        wheels_dir = tmp_root / "plugins" / "wheels"
        wheels_dir.mkdir(parents=True, exist_ok=True)

        # 写两个 wheel：auto-mas-core 6.0.0a1 + plugin-1 1.0.0
        for filename in [
            "auto_mas_core-6.0.0a1-py3-none-any.whl",
            "plugin_1-1.0.0-py3-none-any.whl",
        ]:
            (wheels_dir / filename).write_bytes(b"fake wheel")

        runtime_lock = {
            "schema_version": 1,
            "plugins": [
                {"scope": "plugin", "distribution": "auto-mas-core", "version": "6.0.0a1"},
                {"scope": "plugin", "distribution": "plugin-1", "version": "1.0.0"},
            ],
            "host_runtime": [],
            "plugin_runtime": [],
            "install_contract": {"protected_host_distributions": []},
            "expected_plugin_entry_points": [
                {"group": "auto_mas.plugins", "name": f"plugin_{i}"}
                for i in range(2)
            ],
        }
        runtime_lock_path = wheels_dir / "runtime-lock.json"
        _write_json(runtime_lock_path, runtime_lock)

        manifest = {
            "schema_version": 3,
            "artifact_scope": "complete-windows-x64-runtime-wheelhouse",
            "expected_plugin_distribution_count": 2,
            "expected_plugin_entry_point_count": 2,
            "runtime_lock": {
                "filename": "runtime-lock.json",
                "size_bytes": (runtime_lock_path).stat().st_size,
                "sha256": _sha256_file(runtime_lock_path),
            },
            "wheels": [
                {
                    "kind": "plugin",
                    "scopes": ["plugin"],
                    "distribution": "auto-mas-core",
                    "version": "6.0.0a1",
                    "entry_points": [],
                    "filename": "auto_mas_core-6.0.0a1-py3-none-any.whl",
                    "size_bytes": 11,
                    "sha256": _sha256_file(wheels_dir / "auto_mas_core-6.0.0a1-py3-none-any.whl"),
                },
                {
                    "kind": "plugin",
                    "scopes": ["plugin"],
                    "distribution": "plugin-1",
                    "version": "1.0.0",
                    "entry_points": [],
                    "filename": "plugin_1-1.0.0-py3-none-any.whl",
                    "size_bytes": 11,
                    "sha256": _sha256_file(wheels_dir / "plugin_1-1.0.0-py3-none-any.whl"),
                },
            ],
        }
        manifest_path = wheels_dir / "manifest.json"
        _write_json(manifest_path, manifest)

        manifest_sha = _sha256_file(manifest_path)
        runtime_lock_sha = _sha256_file(runtime_lock_path)

        snapshot = {
            "schema_version": 1,
            "snapshot_id": "test-snapshot",
            "version": "v6.0.0-test",
            "generated_at": "2026-07-23T00:00:00.000Z",
            "deployment_mode": "bundled-snapshot",
            "required_paths": ["app"],
            "wheel_manifest": "plugins/wheels/manifest.json",
            "wheelhouse_contract": {
                "manifest_schema_version": 3,
                "runtime_lock_schema_version": 1,
                "wheel_count": 2,
                "plugin_distribution_count": 2,
                "plugin_entry_point_count": 2,
                "core_distribution_version": "6.0.0a1",
                "manifest_sha256": manifest_sha,
                "runtime_lock_sha256": runtime_lock_sha,
            },
            "update_policy": "test",
        }
        snapshot_path = tmp_root / "res" / "integration-snapshot.json"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(snapshot_path, snapshot)

        return {
            "root": tmp_root,
            "snapshot": snapshot_path,
            "wheels": wheels_dir,
            "manifest": manifest_path,
            "runtime_lock": runtime_lock_path,
        }

    def test_pyproject_pin_matches_runtime_lock_passes(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = self._build_repo_with_bootstrap_section(
                Path(tmp),
                bootstrap_packages_toml=(
                    '    { name = "auto-mas-core", version = "6.0.0a1" },\n'
                    '    { name = "plugin-1", version = "1.0.0" }'
                ),
            )
            result = verify_wheelhouse_snapshot(paths["root"])
            self.assertEqual(result["wheel_count"], 2)

    def test_pyproject_pin_differs_from_runtime_lock_raises(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = self._build_repo_with_bootstrap_section(
                Path(tmp),
                bootstrap_packages_toml=(
                    '    { name = "auto-mas-core", version = "6.0.0a1" },\n'
                    '    { name = "plugin-1", version = "9.9.9" }'
                ),
            )
            with self.assertRaisesRegex(
                SnapshotDriftError,
                r"pyproject plugin-bootstrap pin 与 runtime-lock 不一致.*plugin[-_]1.*9\.9\.9.*1\.0\.0",
            ):
                verify_wheelhouse_snapshot(paths["root"])

    def test_pyproject_pin_missing_from_runtime_lock_raises(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = self._build_repo_with_bootstrap_section(
                Path(tmp),
                bootstrap_packages_toml=(
                    '    { name = "auto-mas-core", version = "6.0.0a1" },\n'
                    '    { name = "plugin-1", version = "1.0.0" },\n'
                    '    { name = "missing-pkg", version = "0.1.0" }'
                ),
            )
            with self.assertRaisesRegex(
                SnapshotDriftError,
                r"pyproject plugin-bootstrap 声明 missing[-_]pkg==0\.1\.0.*runtime-lock\.plugins 中找不到",
            ):
                verify_wheelhouse_snapshot(paths["root"])

    def test_pyproject_only_package_name_does_not_trigger_strict_match(self) -> None:
        """仅声明包名（无 version/specifier）时不做严格相等匹配。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = self._build_repo_with_bootstrap_section(
                Path(tmp),
                bootstrap_packages_toml=(
                    '    "auto-mas-core",\n'
                    '    "plugin-1"'
                ),
            )
            result = verify_wheelhouse_snapshot(paths["root"])
            self.assertEqual(result["plugin_distribution_count"], 2)

    def test_pyproject_without_bootstrap_section_skips_pin_check(self) -> None:
        """无 [tool.auto-mas.plugin-bootstrap] section 时不报 pin 漂移。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            # 用 _build_minimal_repo 构造不含 bootstrap section 的 pyproject
            paths = _build_minimal_repo(Path(tmp), wheel_count=2)
            result = verify_wheelhouse_snapshot(paths["root"])
            self.assertEqual(result["wheel_count"], 2)

    def test_pyproject_with_specifier_does_not_trigger_strict_match(self) -> None:
        """specifier 形式声明交给运行时范围匹配，此处不强制相等。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = self._build_repo_with_bootstrap_section(
                Path(tmp),
                bootstrap_packages_toml=(
                    '    { name = "auto-mas-core", version = "6.0.0a1" },\n'
                    '    { name = "plugin-1", specifier = ">=1.0.0,<2.0.0" }'
                ),
            )
            result = verify_wheelhouse_snapshot(paths["root"])
            self.assertEqual(result["plugin_distribution_count"], 2)


if __name__ == "__main__":
    unittest.main()
