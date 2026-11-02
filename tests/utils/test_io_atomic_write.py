"""原子保存的短暂占用重试、失败诊断与原文件保护。"""

import errno
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.utils import io as _utils_io


def _windows_error(code: int) -> OSError:
    error = PermissionError(errno.EACCES, "file is held")
    error.winerror = code
    return error


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_retry_recovers_from_transient_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, winerror: int
) -> None:
    path = tmp_path / "config.json"
    path.write_bytes(b"old")
    replace = Path.replace
    attempts = 0
    delays = []

    def replace_after_release(source: Path, target: Path) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise _windows_error(winerror)
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", value=replace_after_release)
    monkeypatch.setattr(_utils_io, "sleep", value=delays.append)

    _utils_io.atomic_write(path, b"new")

    assert attempts == 3
    assert len(delays) == 2
    assert sum(delays) <= 0.2
    assert path.read_bytes() == b"new"
    assert not path.with_name("config.json.tmp").exists()


def test_exhausted_retry_preserves_original_and_reports_file_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "SyntheticProfileName"
    folder.mkdir()
    path = folder / "config.json"
    path.write_bytes(b"private original payload")
    failure = _windows_error(5)
    replace = Mock(side_effect=failure)
    delays = []
    logger = Mock()
    monkeypatch.setattr(Path, "replace", value=replace)
    monkeypatch.setattr(_utils_io, "sleep", value=delays.append)
    monkeypatch.setattr(_utils_io, "logger", value=logger)

    with pytest.raises(PermissionError) as caught:
        _utils_io.atomic_write(path, b"private replacement payload")

    assert caught.value is failure
    assert replace.call_count == 4
    assert len(delays) == 3
    assert sum(delays) <= 0.2
    assert path.read_bytes() == b"private original payload"
    assert not path.with_name("config.json.tmp").exists()
    diagnostics = "\n".join(getattr(failure, "__notes__", ()))
    for detail in ("attempts=4", "winerror=5", "source=", "target=", "parent="):
        assert detail in diagnostics
    assert "private original payload" not in diagnostics
    assert "private replacement payload" not in diagnostics
    assert logger.info.called
    assert not logger.warning.called
    assert not logger.error.called
    assert str(tmp_path) not in diagnostics
    assert "SyntheticProfileName" not in diagnostics
    assert all(str(tmp_path) not in str(call) for call in logger.info.call_args_list)


def test_other_replace_errors_are_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    path.write_bytes(b"old")
    failure = OSError(errno.ENOSPC, "no space")
    replace = Mock(side_effect=failure)
    sleep = Mock()
    monkeypatch.setattr(Path, "replace", value=replace)
    monkeypatch.setattr(_utils_io, "sleep", value=sleep)

    with pytest.raises(OSError) as caught:
        _utils_io.atomic_write(path, b"new")

    assert caught.value is failure
    assert replace.call_count == 1
    sleep.assert_not_called()
    assert path.read_bytes() == b"old"


@pytest.mark.skipif(os.name != "nt", reason="Windows file sharing semantics")
def test_real_windows_read_handle_can_be_released_during_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    path.write_bytes(b"old")
    with path.open("rb") as reader:
        monkeypatch.setattr(_utils_io, "sleep", value=lambda _delay: reader.close())
        _utils_io.atomic_write(path, b"new")
    assert path.read_bytes() == b"new"


def test_cleanup_failure_does_not_replace_original_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    path.write_bytes(b"old")
    failure = _windows_error(5)
    monkeypatch.setattr(Path, "replace", value=Mock(side_effect=failure))
    monkeypatch.setattr(_utils_io, "sleep", value=lambda _delay: None)
    temporary = path.with_name("config.json.tmp")
    unlink = Path.unlink

    def fail_cleanup(target: Path, *, missing_ok: bool = False) -> None:
        if target == temporary:
            raise _windows_error(32)
        unlink(target, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", value=fail_cleanup)
    try:
        with pytest.raises(PermissionError) as caught:
            _utils_io.atomic_write(path, b"new")
        assert caught.value is failure
        assert path.read_bytes() == b"old"
        assert any("cleanup" in note for note in failure.__notes__)
    finally:
        unlink(temporary, missing_ok=True)


def test_snapshot_skips_staging_file_replaced_while_waiting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """等待写锁时已转正的暂存文件不导致快照失败。"""
    target = tmp_path / "state.json"
    temporary = tmp_path / "state.json.tmp"
    snapshot = tmp_path / "snapshot"
    replacing = threading.Event()
    copying = threading.Event()
    release = threading.Event()
    replace = Path.replace

    def pause_replace(source: Path, destination: Path) -> Path:
        replacing.set()
        if not release.wait(5):
            raise TimeoutError("atomic replacement was not released")
        return replace(source, destination)

    def copy_snapshot() -> bool:
        copying.set()
        return _utils_io.copy_file_snapshot(temporary, snapshot)

    monkeypatch.setattr(Path, "replace", value=pause_replace)
    with ThreadPoolExecutor(max_workers=2) as executor:
        writer = executor.submit(_utils_io.atomic_write, path=target, data=b"complete")
        try:
            assert replacing.wait(5)
            reader = executor.submit(copy_snapshot)
            assert copying.wait(5)
        finally:
            release.set()
        writer.result(timeout=5)
        assert reader.result(timeout=5) is False
    assert target.read_bytes() == b"complete"
    assert not snapshot.exists()
