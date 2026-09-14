"""脚本原生配置快照的崩溃恢复与用户改动保护

任务中途崩溃后, 上次留下的快照必须在下次任务开始时被处置: 该恢复的恢复,
但用户如果已经手动改过原生配置, 绝不能拿旧快照盖回去。
"""

from pathlib import Path

import pytest

from app.utils.io import (
    clear_native_config_snapshot,
    dir_fingerprint,
    mark_native_config_injected,
    read_native_config_snapshot,
    recover_native_config,
    write_native_config_snapshot,
)


def _write_config(path: Path, marker: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "mxu-MaaEnd.json").write_text(marker, encoding="utf-8")


def _commit_snapshot(
    snapshot: Path, live: Path, *, injected: str | None, script_id: str = "script-1"
) -> None:
    write_native_config_snapshot(
        snapshot,
        script_id=script_id,
        original_exists=True,
        baseline=dir_fingerprint(snapshot),
        injected=injected,
    )
    assert read_native_config_snapshot(snapshot) is not None
    assert live.exists()


def test_restores_when_crashed_after_injection(tmp_path: Path) -> None:
    """崩溃在注入之后且无人改动: 恢复回原始配置。"""

    snapshot = tmp_path / "Temp"
    live = tmp_path / "config"
    _write_config(snapshot, "original")
    _write_config(live, "injected")

    _commit_snapshot(snapshot, live, injected=dir_fingerprint(live))

    assert recover_native_config(snapshot, live, expected_script_id="script-1") == (
        "restored"
    )
    assert (live / "mxu-MaaEnd.json").read_text(encoding="utf-8") == "original"


def test_skips_when_user_edited_after_crash(tmp_path: Path) -> None:
    """崩溃后用户手动改过配置: 只清理快照, 不覆盖用户改动(本次保护重点)。"""

    snapshot = tmp_path / "Temp"
    live = tmp_path / "config"
    _write_config(snapshot, "original")
    _write_config(live, "injected")
    injected = dir_fingerprint(live)

    _commit_snapshot(snapshot, live, injected=injected)
    (live / "mxu-MaaEnd.json").write_text("user-edited", encoding="utf-8")

    assert recover_native_config(snapshot, live, expected_script_id="script-1") == (
        "skipped"
    )
    assert (live / "mxu-MaaEnd.json").read_text(encoding="utf-8") == "user-edited"
    assert not snapshot.exists()


def test_idempotent_when_already_restored(tmp_path: Path) -> None:
    """已经恢复过一遍: 幂等跳过, 不重复写入。"""

    snapshot = tmp_path / "Temp"
    live = tmp_path / "config"
    _write_config(snapshot, "original")
    _write_config(live, "original")

    _commit_snapshot(snapshot, live, injected=None)

    assert recover_native_config(snapshot, live, expected_script_id="script-1") == (
        "intact"
    )
    assert (live / "mxu-MaaEnd.json").read_text(encoding="utf-8") == "original"


def test_clears_snapshot_of_another_script(tmp_path: Path) -> None:
    """快照属于别的脚本: 只清理, 绝不恢复。"""

    snapshot = tmp_path / "Temp"
    live = tmp_path / "config"
    _write_config(snapshot, "original")
    _write_config(live, "injected")

    _commit_snapshot(snapshot, live, injected=dir_fingerprint(live), script_id="other")

    assert recover_native_config(snapshot, live, expected_script_id="script-1") == (
        "cleared"
    )
    assert (live / "mxu-MaaEnd.json").read_text(encoding="utf-8") == "injected"


def test_no_snapshot_is_a_noop(tmp_path: Path) -> None:
    """没有已提交快照时不动现场。"""

    live = tmp_path / "config"
    _write_config(live, "injected")

    assert recover_native_config(tmp_path / "Temp", live) == "cleared"
    assert (live / "mxu-MaaEnd.json").read_text(encoding="utf-8") == "injected"


def test_uncommitted_snapshot_is_discarded(tmp_path: Path) -> None:
    """只有目录没有 .ready 标记: 说明上次没拷完整, 丢弃而非恢复。"""

    snapshot = tmp_path / "Temp"
    live = tmp_path / "config"
    _write_config(snapshot, "half-copied")
    _write_config(live, "injected")

    assert recover_native_config(snapshot, live, expected_script_id="script-1") == (
        "cleared"
    )
    assert (live / "mxu-MaaEnd.json").read_text(encoding="utf-8") == "injected"
    assert not snapshot.exists()


def test_clear_removes_marker(tmp_path: Path) -> None:
    """清理会同时删掉目录和提交标记。"""

    snapshot = tmp_path / "Temp"
    _write_config(snapshot, "original")
    write_native_config_snapshot(
        snapshot, script_id="script-1", original_exists=True, baseline="x"
    )

    clear_native_config_snapshot(snapshot)

    assert not snapshot.exists()
    assert read_native_config_snapshot(snapshot) is None


def test_mark_injected_updates_marker_only_for_own_script(tmp_path: Path) -> None:
    """标记注入后指纹落到提交标记里; 归属不符或无快照时是空操作。"""

    snapshot = tmp_path / "Temp"
    live = tmp_path / "config"
    _write_config(snapshot, "original")
    _write_config(live, "injected")
    write_native_config_snapshot(
        snapshot,
        script_id="script-1",
        original_exists=True,
        baseline=dir_fingerprint(snapshot),
    )

    mark_native_config_injected(snapshot, live, script_id="script-1")

    state = read_native_config_snapshot(snapshot)
    assert state is not None
    assert state.injected == dir_fingerprint(live)

    # 归属不符: 不改写
    mark_native_config_injected(snapshot, live, script_id="other")
    state = read_native_config_snapshot(snapshot)
    assert state is not None
    assert state.script_id == "script-1"

    # 无快照: 空操作不报错
    mark_native_config_injected(tmp_path / "no-snapshot", live, script_id="s")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

