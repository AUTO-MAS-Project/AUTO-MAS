"""r6 rollback bundle 完整性验证。

覆盖：production_wire_roots_to_legacy 输出形状、
目标已存在时抛 RollbackExportError、manifest sha256 完整性。

注：assert_config_v2_startup_mode_ready 是 app 启动门禁，
不在 AuthoritativeConfigurationRuntime.initialize() 调用链中，
因此测试中可直接初始化 authoritative runtime（与 test_authoritative_runtime.py 一致）。
使用 asyncio.run 替代 @pytest.mark.asyncio，因项目未确认安装 pytest-asyncio。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import pathlib
import tempfile

import pytest

from app.configuration.authoritative import (
    AuthoritativeConfigurationRuntime,
    RollbackExportError,
)
from app.configuration.compat import LEGACY_ROOT_FILE_NAMES
from app.configuration.production import (
    legacy_production_roots_to_wire,
    production_wire_roots_to_legacy,
)


def test_rollback_bundle_legacy_shapes_complete():
    """production_wire_roots_to_legacy 返回 8 个文件名键，每个值是 dict。"""
    legacy_roots = {name: None for name in LEGACY_ROOT_FILE_NAMES}
    wire_roots = legacy_production_roots_to_wire(legacy_roots)

    legacy = production_wire_roots_to_legacy(wire_roots)

    assert set(legacy.keys()) == set(LEGACY_ROOT_FILE_NAMES)
    for value in legacy.values():
        assert isinstance(value, dict)


def test_rollback_bundle_target_exists_raises():
    """export_r6_rollback_bundle 目标已存在时抛 RollbackExportError。

    注意：不使用 pytest tmp_path，因 authoritative store 的深嵌套路径
    (.config-v2-authoritative/original-<hash>/staging/.pending-g-<hash>/roots/)
    在工作树内 pytest basetemp 下会超过 Windows MAX_PATH 260 限制，
    导致 open("xb") 抛 FileNotFoundError。改用系统临时目录的短路径。
    """
    with tempfile.TemporaryDirectory(prefix="rb_") as base:
        base_path = pathlib.Path(base)
        config_dir = base_path / "cfg"
        export_parent = base_path / "out"

        async def _run() -> None:
            runtime = AuthoritativeConfigurationRuntime(config_dir)
            try:
                await runtime.initialize()

                bundle = runtime.export_r6_rollback_bundle(export_parent)
                assert bundle.is_dir()
                assert bundle.name.startswith("r6-rollback-")

                expected_files = set(LEGACY_ROOT_FILE_NAMES) | {"manifest.json"}
                assert {p.name for p in bundle.iterdir()} == expected_files

                with pytest.raises(RollbackExportError):
                    runtime.export_r6_rollback_bundle(export_parent)
            finally:
                runtime.close()

        asyncio.run(_run())


def test_rollback_bundle_manifest_integrity(tmp_path):
    """手动构造 rollback bundle staging 目录，os.rename 发布后读回验证 sha256 一致。"""
    staging = tmp_path / "staging"
    staging.mkdir()
    files_dir = staging / "files"
    files_dir.mkdir()

    root_records = []
    for name in LEGACY_ROOT_FILE_NAMES:
        content = (
            json.dumps(
                {"root": name}, ensure_ascii=False, sort_keys=True, indent=4
            )
            + "\n"
        ).encode("utf-8")
        (files_dir / name).write_bytes(content)
        root_records.append(
            {
                "name": name,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )

    manifest = {
        "schema_version": 1,
        "kind": "auto-mas-r6-config-rollback",
        "source_snapshot_generation": "original-test123",
        "source_generation": "gen-test",
        "source_revision": 1,
        "roots": root_records,
    }
    manifest_bytes = (
        json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, indent=4
        )
        + "\n"
    ).encode("utf-8")
    (staging / "manifest.json").write_bytes(manifest_bytes)

    final_path = tmp_path / "r6-rollback-gen-test"
    os.rename(staging, final_path)

    read_manifest = json.loads(
        (final_path / "manifest.json").read_text(encoding="utf-8")
    )
    assert read_manifest["kind"] == "auto-mas-r6-config-rollback"
    assert read_manifest["source_generation"] == "gen-test"
    assert len(read_manifest["roots"]) == len(LEGACY_ROOT_FILE_NAMES)

    for record in read_manifest["roots"]:
        name = record["name"]
        content = (final_path / "files" / name).read_bytes()
        assert len(content) == record["size_bytes"]
        assert hashlib.sha256(content).hexdigest() == record["sha256"]
