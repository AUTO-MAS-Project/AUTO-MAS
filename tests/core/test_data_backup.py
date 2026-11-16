"""备份压缩与实时配置保存之间的文件句柄隔离。"""

import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.core.config import backup as data_backup
from app.models.schema import HistoryBackupSnapshot
from app.utils import io as _utils_io


def test_backup_allows_live_saves_and_preserves_export_priority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """压缩时保存新配置不阻塞；备份仍是旧快照和导出时的内存值。"""
    root = tmp_path / "live"
    config = root / "config"
    config.mkdir(parents=True)
    (config / "schedule.json").write_bytes(b"complete")
    (config / "schedule.json.tmp").write_bytes(b"persistent content")
    calendar = config / "GameCalendarSchedule.json"
    calendar.write_bytes(b'{"old": true}')
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
    compressing, release = threading.Event(), threading.Event()
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

    monkeypatch.setattr(data_backup.zipfile, "ZipFile", PausedZipFile)
    archive_path = None
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(
                data_backup._create_data_backup,
                root=root,
                config_export=exported,
                history_snapshot=HistoryBackupSnapshot(
                    destination=tmp_path, database=database, history=history
                ),
            )
            try:
                assert compressing.wait(5)
                _utils_io.atomic_write(calendar, b'{"new": true}')
            finally:
                release.set()
                archive_path = pending.result(timeout=5)
        with original_zip(archive_path) as archive:
            assert archive.read("config/schedule.json.tmp") == b"persistent content"
            assert archive.read("config/schedule.json") == b"complete"
            assert archive.read("config/GameCalendarSchedule.json") == b'{"old": true}'
            assert archive.read("config/settings.yaml") == b"memory version"
            assert not any("maafw_agent_venvs" in name for name in archive.namelist())
        assert calendar.read_bytes() == b'{"new": true}'
    finally:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)
