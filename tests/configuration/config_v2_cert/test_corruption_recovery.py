"""损坏文件与未知字段不会静默丢配置的验证。

覆盖：损坏 JSON 快照捕获与解析拒绝、损坏 TOML 读取抛异常、
未知键保留、中断写入恢复、备份保留与恢复失败。
"""

from __future__ import annotations

import os
import shutil
import tomllib

import pytest

from app.configuration import read_wire_toml, write_wire_toml
from app.configuration.authoritative import (
    LegacySnapshotDecodeError,
    load_legacy_original_roots,
)
from app.configuration.compat.legacy_original_snapshot import (
    ensure_legacy_original_snapshot,
)


def test_corrupted_json_rejected_by_snapshot(tmp_path):
    """损坏 JSON 字节被快照捕获，但 load_legacy_original_roots 解析时抛 LegacySnapshotDecodeError。

    快照捕获阶段（_capture_legacy_roots）只读字节不解析 JSON，
    所以损坏 JSON 字节会被成功捕获。解析发生在 load_legacy_original_roots
    的 json.loads 调用中，损坏 JSON 在此抛 LegacySnapshotDecodeError。
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "Config.json").write_bytes(b'{"broken": ')

    # 快照成功创建——捕获阶段只读字节不解析
    snapshot = ensure_legacy_original_snapshot(config_dir)
    assert snapshot.created

    # 解析阶段抛 LegacySnapshotDecodeError
    with pytest.raises(LegacySnapshotDecodeError):
        load_legacy_original_roots(snapshot)


def test_corrupted_toml_read_returns_empty_or_raises(tmp_path):
    """损坏 TOML 文件被 read_wire_toml 读取时抛异常而非静默返回空。"""
    path = tmp_path / "broken.toml"
    path.write_text("[unclosed", encoding="utf-8")

    # tomllib.load 不捕获异常，直接抛 TOMLDecodeError
    with pytest.raises(tomllib.TOMLDecodeError):
        read_wire_toml(path)


def test_unknown_field_in_wire_does_not_silently_drop(tmp_path):
    """未知键被 write_wire_toml 保留——_tomlable 不过滤未知键。"""
    path = tmp_path / "wire.toml"
    payload = {
        "known": "value",
        "unknown_field": "preserved",
        "nested": {"mystery": True},
    }

    write_wire_toml(path, payload)
    restored = read_wire_toml(path)

    assert restored["known"] == "value"
    assert restored["unknown_field"] == "preserved"
    assert restored["nested"]["mystery"] is True


def test_interrupted_write_preserves_original(tmp_path, monkeypatch):
    """os.replace 失败时，原文件从 .bak 恢复，内容不变。"""
    path = tmp_path / "wire.toml"
    write_wire_toml(path, {"value": "original"})
    original_content = path.read_text(encoding="utf-8")

    def failing_replace(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", failing_replace)

    # os.replace 失败后 .bak 恢复成功，原异常（OSError）被重新抛出
    with pytest.raises(OSError):
        write_wire_toml(path, {"value": "corrupted"})

    # 原文件内容未变
    assert path.read_text(encoding="utf-8") == original_content


def test_backup_retained_on_restore_failure(tmp_path, monkeypatch):
    """os.replace 和 shutil.copy2 恢复均失败时，抛 RuntimeError 且 .bak 保留。"""
    path = tmp_path / "wire.toml"
    write_wire_toml(path, {"value": "original"})

    real_copy2 = shutil.copy2
    call_count = [0]

    def selective_copy2(src, dst):
        call_count[0] += 1
        if call_count[0] == 1:
            # 第一次调用：创建备份——成功
            return real_copy2(src, dst)
        # 第二次调用：从备份恢复——失败
        raise OSError("restore failed")

    def failing_replace(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", failing_replace)
    monkeypatch.setattr(shutil, "copy2", selective_copy2)

    with pytest.raises(RuntimeError, match="backup"):
        write_wire_toml(path, {"value": "corrupted"})

    backup_path = path.with_name(f"{path.name}.bak")
    assert backup_path.exists()
