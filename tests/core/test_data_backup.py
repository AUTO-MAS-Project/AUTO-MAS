"""备份压缩与实时配置保存之间的文件句柄隔离。"""

import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.core.config import backup as data_backup
from app.models.schema import HistoryBackupSnapshot
from app.utils import io as _utils_io


def test_config_can_be_saved_while_backup_compresses_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """压缩已有配置时仍能原子保存，备份保留压缩前的完整内容。"""
    root = tmp_path / "live"
    config = root / "config"
    config.mkdir(parents=True)
    schedule = config / "GameCalendarSchedule.json"
    schedule.write_bytes(b'{"old": true}')
    exported = tmp_path / "exported"
    exported.mkdir()
    history = tmp_path / "history"
    history.mkdir()
    database = tmp_path / "history.db"
    database.write_bytes(b"isolated history snapshot")
    snapshot = HistoryBackupSnapshot(
        destination=tmp_path, database=database, history=history
    )
    compressing = threading.Event()
    release = threading.Event()
    original_zip = zipfile.ZipFile

    class PausedZipFile(original_zip):
        def open(self, name, mode="r", pwd=None, *, force_zip64=False):
            if (
                mode == "w"
                and getattr(name, "filename", "") == "config/GameCalendarSchedule.json"
            ):
                compressing.set()
                if not release.wait(5):
                    raise TimeoutError("backup compression was not released")
            return super().open(name, mode=mode, pwd=pwd, force_zip64=force_zip64)

    monkeypatch.setattr(data_backup.zipfile, "ZipFile", value=PausedZipFile)
    archive_path = None
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(
                data_backup._create_data_backup,
                root=root,
                config_export=exported,
                history_snapshot=snapshot,
            )
            try:
                assert compressing.wait(5)
                _utils_io.atomic_write(schedule, b'{"new": true}')
            finally:
                release.set()
                archive_path = pending.result(timeout=5)
        with original_zip(archive_path) as archive:
            assert archive.read("config/GameCalendarSchedule.json") == b'{"old": true}'
        assert schedule.read_bytes() == b'{"new": true}'
    finally:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)


def test_backup_preserves_persistent_tmp_files_and_export_priority(
    tmp_path: Path,
) -> None:
    """持久化的 .tmp 文件仍进入备份，已导出的配置仍优先。"""
    root = tmp_path / "live"
    config = root / "config"
    config.mkdir(parents=True)
    (config / "schedule.json").write_bytes(b"complete")
    (config / "schedule.json.tmp").write_bytes(b"persistent content")
    runtime = config / "maafw_agent_venvs" / "environment"
    runtime.mkdir(parents=True)
    (runtime / "python.exe").write_bytes(b"rebuildable environment")
    (config / "settings.yaml").write_bytes(b"disk version")
    exported = tmp_path / "exported"
    exported.mkdir()
    (exported / "settings.yaml").write_bytes(b"memory version")
    history = tmp_path / "history"
    history.mkdir()
    database = tmp_path / "history.db"
    database.write_bytes(b"isolated history snapshot")
    archive_path = data_backup._create_data_backup(
        root=root,
        config_export=exported,
        history_snapshot=HistoryBackupSnapshot(
            destination=tmp_path, database=database, history=history
        ),
    )
    try:
        with zipfile.ZipFile(archive_path) as archive:
            assert archive.read("config/schedule.json.tmp") == b"persistent content"
            assert archive.read("config/schedule.json") == b"complete"
            assert archive.read("config/settings.yaml") == b"memory version"
            assert not any("maafw_agent_venvs" in name for name in archive.namelist())
    finally:
        archive_path.unlink(missing_ok=True)


def test_backup_releases_previous_snapshot_before_copying_next_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """配置逐个复制压缩，已入包副本不再占用临时磁盘。"""
    root = tmp_path / "live"
    config = root / "config"
    config.mkdir(parents=True)
    for name in ("first.json", "second.json"):
        (config / name).write_bytes(name.encode())
    exported = tmp_path / "exported"
    exported.mkdir()
    history = tmp_path / "history"
    history.mkdir()
    database = tmp_path / "history.db"
    database.write_bytes(b"isolated history snapshot")
    copy_snapshot = _utils_io.copy_file_snapshot
    previous: list[Path] = []

    def check_snapshot_space(source: Path, destination: Path) -> bool:
        assert all(not item.exists() for item in previous)
        copied = copy_snapshot(source, destination)
        previous.append(destination)
        return copied

    monkeypatch.setattr(_utils_io, "copy_file_snapshot", value=check_snapshot_space)
    archive_path = data_backup._create_data_backup(
        root=root,
        config_export=exported,
        history_snapshot=HistoryBackupSnapshot(
            destination=tmp_path, database=database, history=history
        ),
    )
    try:
        assert len(previous) == 2
        assert all(not item.exists() for item in previous)
        with zipfile.ZipFile(archive_path) as archive:
            for name in ("first.json", "second.json"):
                assert archive.read(f"config/{name}") == name.encode()
    finally:
        archive_path.unlink(missing_ok=True)
