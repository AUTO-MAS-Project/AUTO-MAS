"""脚本原生配置快照的崩溃恢复与用户改动保护

任务中途崩溃后, 上次留下的快照必须在下次任务开始时被处置: 该恢复的恢复,
但用户如果已经手动改过原生配置, 绝不能拿旧快照盖回去。
"""

import json
from pathlib import Path

import pytest

from app.utils import io as _utils_io


def _write_config(path: Path, marker: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "mxu-MaaEnd.json").write_text(marker, encoding="utf-8")


def _commit_snapshot(snapshot: Path, *, injected: str | None) -> None:
    _utils_io.write_native_config_snapshot(
        snapshot,
        script_id="script-1",
        original_exists=True,
        baseline=_utils_io.dir_fingerprint(snapshot),
        injected=injected,
    )


def test_restores_when_crashed_after_injection(tmp_path: Path) -> None:
    """崩溃在注入之后且无人改动: 恢复回原始配置。"""

    snapshot = tmp_path / "Temp"
    live = tmp_path / "config"
    _write_config(snapshot, "original")
    _write_config(live, "injected")

    _commit_snapshot(snapshot, injected=_utils_io.dir_fingerprint(live))

    assert _utils_io.recover_native_config(
        snapshot, live, expected_script_id="script-1"
    ) == ("restored")
    assert (live / "mxu-MaaEnd.json").read_text(encoding="utf-8") == "original"


def test_failed_restore_keeps_original_snapshot_for_successful_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """恢复换入失败时保留快照, 供下次任务重试。"""

    snapshot = tmp_path / "Temp"
    live = tmp_path / "config"
    _write_config(snapshot, "original")
    _write_config(live, "injected")
    _commit_snapshot(snapshot, injected=_utils_io.dir_fingerprint(live))

    def fail_swap(*_args: Path, **_kwargs: object) -> None:
        raise PermissionError("配置目录仍被占用")

    with monkeypatch.context() as filesystem:
        filesystem.setattr("app.utils.common.io.swap_in_dir", fail_swap)
        with pytest.raises(PermissionError, match="配置目录仍被占用"):
            _utils_io.recover_native_config(
                snapshot, live, expected_script_id="script-1"
            )

    assert snapshot.exists()
    assert snapshot.with_name(snapshot.name + ".ready.json").exists()
    assert (snapshot / "mxu-MaaEnd.json").read_text(encoding="utf-8") == "original"
    assert (
        _utils_io.recover_native_config(snapshot, live, expected_script_id="script-1")
        == "restored"
    )
    assert (live / "mxu-MaaEnd.json").read_text(encoding="utf-8") == "original"


def test_skips_when_user_edited_after_crash(tmp_path: Path) -> None:
    """崩溃后用户手动改过配置: 只清理快照, 不覆盖用户改动(本次保护重点)。"""

    snapshot = tmp_path / "Temp"
    live = tmp_path / "config"
    _write_config(snapshot, "original")
    _write_config(live, "injected")
    injected = _utils_io.dir_fingerprint(live)

    _commit_snapshot(snapshot, injected=injected)
    # 与注入内容等长, 确认指纹确实比较内容而非仅比较大小。
    (live / "mxu-MaaEnd.json").write_text("changed", encoding="utf-8")

    assert _utils_io.recover_native_config(
        snapshot, live, expected_script_id="script-1"
    ) == ("skipped")
    assert (live / "mxu-MaaEnd.json").read_text(encoding="utf-8") == "changed"
    assert not snapshot.exists()


def test_legacy_fingerprint_snapshot_is_preserved_aside(tmp_path: Path) -> None:
    """旧算法写下的快照比不了指纹: 不恢复也不删除, 改名留存用户的原始配置。"""

    snapshot = tmp_path / "Temp"
    live = tmp_path / "config"
    _write_config(snapshot, "original")
    _write_config(live, "injected")
    # 旧版本写下的标记没有 fingerprint_version
    snapshot.with_name("Temp.ready.json").write_text(
        json.dumps(
            {
                "script_id": "script-1",
                "original_exists": True,
                "baseline": "old-algorithm",
                "injected": None,
            }
        ),
        encoding="utf-8",
    )

    assert _utils_io.recover_native_config(
        snapshot, live, expected_script_id="script-1"
    ) == ("legacy")
    assert (live / "mxu-MaaEnd.json").read_text(encoding="utf-8") == "injected"
    preserved = tmp_path / "Temp.legacy"
    assert (preserved / "mxu-MaaEnd.json").read_text(encoding="utf-8") == "original"
    assert preserved.with_name("Temp.legacy.ready.json").exists()
    assert not snapshot.exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
