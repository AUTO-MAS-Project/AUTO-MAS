import json
import shutil
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path

import pytest

from app.core.config import upgrade_backup
from app.core.config.upgrade_backup import UpgradeBackup


def _install(root: Path, version: str | None) -> None:
    (root / "config").mkdir()
    (root / "data").mkdir()
    (root / "history").mkdir()
    if version is not None:
        (root / "config" / "frontend_config.json").write_text(
            json.dumps({"initializedVersion": version}), encoding="utf-8"
        )


def _archives(root: Path) -> list[Path]:
    return sorted((root / "backup").glob("AUTO-MAS-backup-*.zip"))


def _start(root: Path, version: str) -> UpgradeBackup:
    backup = UpgradeBackup(root=root, desktop_version=version)
    assert backup.prepare() is None
    assert backup.begin_migration()
    return backup


def test_snapshot_reads_old_config_and_sqlite_before_migration(tmp_path):
    _install(tmp_path, "5.8.0")
    config = tmp_path / "config" / "Config.json"
    config.write_bytes(b'{"old":true}')
    (tmp_path / "config" / "setting.yaml").write_bytes(b"old_yaml: true\n")
    (tmp_path / "history" / "saved.log").write_bytes(b"old history")
    (tmp_path / "data" / "maafw_update_cache").mkdir()
    (tmp_path / "data" / "maafw_update_cache" / "cached.zip").touch()
    with (
        closing(sqlite3.connect(tmp_path / "data" / "data.db")) as data,
        closing(sqlite3.connect(tmp_path / "data" / "history.db")) as history,
    ):
        data.execute("PRAGMA journal_mode=WAL")
        data.execute("CREATE TABLE marker (value TEXT)")
        data.execute("INSERT INTO marker VALUES ('old')")
        data.commit()
        history.execute("CREATE TABLE pending_files (value TEXT)")
        history.execute("INSERT INTO pending_files VALUES ('old absolute path')")
        history.commit()

        attempt = _start(tmp_path, "v5.9.0-beta.1")
        config.write_bytes(b'{"new":true}')
        data.execute("UPDATE marker SET value = 'migrated'")
        data.commit()
        attempt.finish()

        restored = tmp_path / "restored"
        with zipfile.ZipFile(_archives(tmp_path)[0]) as archive:
            assert archive.read("config/Config.json") == b'{"old":true}'
            assert archive.read("config/setting.yaml") == b"old_yaml: true\n"
            assert archive.read("history/saved.log") == b"old history"
            assert "data/maafw_update_cache/cached.zip" not in archive.namelist()
            assert "data/data.db-wal" not in archive.namelist()
            assert "config/upgrade-backup-state.json" not in archive.namelist()
            archive.extractall(restored)
        with closing(sqlite3.connect(restored / "data" / "data.db")) as restored_data:
            assert restored_data.execute("SELECT value FROM marker").fetchone() == (
                "old",
            )
        with closing(
            sqlite3.connect(restored / "data" / "history.db")
        ) as restored_history:
            assert (
                restored_history.execute("SELECT * FROM pending_files").fetchall() == []
            )
        assert history.execute("SELECT * FROM pending_files").fetchone() == (
            "old absolute path",
        )


def test_old_archives_survive_until_target_business_ready(tmp_path):
    _install(tmp_path, "5.8.0")
    _start(tmp_path, "5.9.0-beta.1").finish()
    stable = _archives(tmp_path)[0]
    manual = stable.parent / "manual.zip"
    manual.write_bytes(b"manual")
    _start(tmp_path, "5.9.0-beta.2").finish()
    first_beta = next(path for path in _archives(tmp_path) if path != stable)
    _start(tmp_path, "5.9.0-beta.10").finish()
    assert first_beta.exists()
    last_beta = next(
        path
        for path in _archives(tmp_path)
        if "-beta.2-to-v5.9.0-beta.10-" in path.name
    )

    _start(tmp_path, "5.9.0")
    # 首次新版未就绪便退出，已有两个回退点和这次生成的 ZIP 均保留。
    pending = _archives(tmp_path)
    assert len(pending) == 4
    assert stable in pending and last_beta in pending
    restarted = _start(tmp_path, "v5.9.0")
    assert _archives(tmp_path) == pending
    restarted.finish()
    assert _archives(tmp_path) == pending
    assert manual.read_bytes() == b"manual"


def test_consecutive_stable_upgrades_keep_both_recent_restore_points(tmp_path):
    _install(tmp_path, "5.8.0")
    _start(tmp_path, "5.9.0").finish()
    stable = _archives(tmp_path)[0]
    _start(tmp_path, "5.9.1").finish()
    recent = _archives(tmp_path)
    assert stable in recent
    assert any("-v5.9.0-to-v5.9.1-" in path.name for path in recent)
    _start(tmp_path, "5.9.1").finish()
    _start(tmp_path, "5.9.0").finish()
    assert _archives(tmp_path) == recent


def test_retention_recognizes_archives_after_replacing_rollback_directories(tmp_path):
    _install(tmp_path, "5.8.0")
    settings = tmp_path / "config" / "setting.yaml"
    history = tmp_path / "history" / "saved.log"
    settings.write_bytes(b"old config")
    history.write_bytes(b"old history")
    _start(tmp_path, "5.9.0-beta.1").finish()
    old_stable = _archives(tmp_path)[0]
    settings.write_bytes(b"migrated config")
    history.write_bytes(b"new history")
    _start(tmp_path, "5.9.0-beta.2").finish()
    beta = next(path for path in _archives(tmp_path) if path != old_stable)

    displaced = tmp_path / "before-rollback"
    displaced.mkdir()
    for name in ("config", "data", "history"):
        (tmp_path / name).rename(displaced / name)
    with zipfile.ZipFile(old_stable) as archive:
        archive.extractall(tmp_path)

    _start(tmp_path, "5.8.0").finish()
    assert settings.read_bytes() == b"old config"
    assert history.read_bytes() == b"old history"
    _start(tmp_path, "5.9.0-beta.3").finish()
    assert old_stable.exists()
    _start(tmp_path, "6.0.0").finish()
    assert not old_stable.exists()
    assert beta in _archives(tmp_path)
    assert len(_archives(tmp_path)) == 3


def test_rotation_removes_older_segments_when_two_newer_archives_exist(tmp_path):
    _install(tmp_path, "5.7.0")
    _start(tmp_path, "5.8.0").finish()
    earliest = _archives(tmp_path)[0]
    _start(tmp_path, "5.9.0").finish()
    assert earliest.exists()
    _start(tmp_path, "6.1.0").finish()
    assert not earliest.exists()
    assert len(_archives(tmp_path)) == 2


@pytest.mark.parametrize("failure", ["corrupt", "unreadable"])
def test_rotation_preserves_valid_previous_segment_when_nearer_archive_fails(
    tmp_path, monkeypatch, failure
):
    _install(tmp_path, "5.7.0")
    _start(tmp_path, "5.8.0").finish()
    _start(tmp_path, "5.9.0").finish()
    earlier, nearer = _archives(tmp_path)
    if failure == "corrupt":
        nearer.write_bytes(b"broken ZIP")

    original_open = zipfile.io.open

    def open_archive(file, *args, **kwargs):
        if isinstance(file, (str, Path)) and Path(file) == nearer:
            raise PermissionError("archive temporarily in use")
        return original_open(file, *args, **kwargs)

    with monkeypatch.context() as patch:
        if failure == "unreadable":
            patch.setattr(zipfile.io, "open", open_archive)
        _start(tmp_path, "5.9.1").finish()
        _start(tmp_path, "5.9.2").finish()
        with zipfile.ZipFile(earlier) as archive:
            assert archive.testzip() is None

    if failure == "unreadable":
        _start(tmp_path, "5.9.2").finish()
        assert nearer.exists()
        assert not earlier.exists()


def test_beta_keeps_latest_stable_fallback_outside_the_rolling_segments(tmp_path):
    _install(tmp_path, "5.7.0")
    _start(tmp_path, "5.8.0-beta.1").finish()
    stable = _archives(tmp_path)[0]
    _start(tmp_path, "5.8.0-beta.2").finish()
    old_beta = next(path for path in _archives(tmp_path) if path != stable)
    _start(tmp_path, "5.9.0-beta.1").finish()
    _start(tmp_path, "6.0.0-beta.1").finish()

    assert stable.exists()
    assert not old_beta.exists()
    assert len(_archives(tmp_path)) == 3


def _preferences(root: Path, *, enabled: bool, directory: Path | None = None) -> None:
    file = root / "config" / "frontend_config.json"
    config = json.loads(file.read_text(encoding="utf-8"))
    config["upgradeBackup"] = {
        "enabled": enabled,
        "directory": str(directory) if directory is not None else None,
    }
    file.write_text(json.dumps(config), encoding="utf-8")


def test_disabling_backup_preserves_archives_and_tracks_the_data_version(tmp_path):
    _install(tmp_path, "5.7.0")
    _start(tmp_path, "5.8.0").finish()
    previous = _archives(tmp_path)
    _preferences(tmp_path, enabled=False)
    _start(tmp_path, "5.9.0").finish()
    assert _archives(tmp_path) == previous
    _preferences(tmp_path, enabled=True)
    _start(tmp_path, "5.9.1").finish()
    assert any("-v5.9.0-to-v5.9.1-" in path.name for path in _archives(tmp_path))


def test_shared_custom_directory_never_rotates_other_installations_archives(tmp_path):
    left, right, shared = (tmp_path / name for name in ("left", "right", "shared"))
    for directory in (left, right, shared):
        directory.mkdir()
    for installation in (left, right):
        _install(installation, "5.7.0")
        _preferences(installation, enabled=True, directory=shared)
    _start(right, "5.8.0").finish()
    foreign = next(shared.glob("*.zip"))
    for version in ("5.8.0", "5.9.0", "6.0.0"):
        _start(left, version).finish()
    assert foreign.exists()
    assert len(list(shared.glob("*.zip"))) == 3

    _preferences(left, enabled=True)
    _start(left, "6.1.0").finish()
    assert len(_archives(left)) == 1
    assert len(list(shared.glob("*.zip"))) == 3


def test_backup_directory_cannot_be_inside_a_snapshotted_directory(tmp_path):
    _install(tmp_path, "5.8.0")
    directory = tmp_path / "config" / "backup"
    _preferences(tmp_path, enabled=True, directory=directory)
    backup = UpgradeBackup(root=tmp_path, desktop_version="5.9.0")
    assert backup.prepare() == "backup_failed"
    assert backup.begin_migration()
    backup.finish()
    assert not directory.exists()


def test_move_directory_keeps_restore_points_and_leaves_manual_exports(tmp_path):
    _install(tmp_path, "5.8.0")
    old = _start(tmp_path, "5.9.0")
    old.finish()
    source = tmp_path / "backup"
    (source / "manual.zip").write_bytes(b"manual archive")
    zip_path = _archives(tmp_path)[0]
    target = tmp_path / "new"

    assert old.move_directory(str(target), expected=str(source))
    assert not zip_path.exists()
    assert (source / "manual.zip").read_bytes() == b"manual archive"
    with zipfile.ZipFile(target / zip_path.name) as archive:
        assert archive.testzip() is None

    restarted = _start(tmp_path, "5.9.1")
    restarted.finish()
    assert restarted.directory_info()["directory"] == str(target)
    assert len(list(target.glob("AUTO-MAS-backup-*.zip"))) == 2


def test_move_directory_rejects_target_inside_residual_snapshot(tmp_path, monkeypatch):
    _install(tmp_path, "5.8.0")
    with monkeypatch.context() as patch:

        def fail_to_remove(_path: Path) -> None:
            raise PermissionError("snapshot in use")

        patch.setattr(upgrade_backup, "force_rmtree", fail_to_remove)
        backup = _start(tmp_path, "5.9.0")
    backup.finish()
    source = tmp_path / "backup"
    original = _archives(tmp_path)[0]
    target = next(source.glob(".*.snapshot")) / "data"

    with pytest.raises(ValueError):
        backup.move_directory(str(target), expected=str(source))
    assert backup.directory_info()["resolvedDirectory"] == str(source)
    assert not list(target.glob("*.zip"))
    with zipfile.ZipFile(original) as archive:
        assert archive.testzip() is None


@pytest.mark.parametrize("already_changed", [False, True])
def test_directory_change_packs_completed_snapshot_from_original_location(
    tmp_path, monkeypatch, already_changed
):
    _install(tmp_path, "5.8.0")
    config = tmp_path / "config" / "setting.yaml"
    config.write_bytes(b"old config")
    source = tmp_path / "backup"
    target = tmp_path / "new"
    target.mkdir()
    attempted_archives: list[Path] = []

    def fail_to_pack(_snapshot: Path, archive: Path) -> None:
        attempted_archives.append(archive)
        raise OSError("old drive has no space")

    with monkeypatch.context() as patch:
        patch.setattr(upgrade_backup, "_pack_snapshot", fail_to_pack)
        startup = UpgradeBackup(root=tmp_path, desktop_version="5.9.0")
        assert startup.prepare() == "backup_failed"
        assert startup.begin_migration()
        startup.finish()
    config.write_bytes(b"already migrated")
    assert list(source.glob(".*.snapshot"))
    assert not _archives(tmp_path)

    if already_changed:
        # 旧客户端曾只保存了新路径。确认同一路径仍能找回原处的快照。
        _preferences(tmp_path, enabled=True, directory=target)
        startup = _start(tmp_path, "5.9.0")
    existing_part = target / attempted_archives[0].with_suffix(".part").name
    existing_part.write_bytes(b"user partial download")
    _, _, archive_id = attempted_archives[0].stem.rpartition("-")
    existing_tmp = target / f".{archive_id}.archive.json.tmp"
    existing_tmp.write_bytes(b"user temporary file")
    assert startup.move_directory(
        str(target), expected=str(target if already_changed else source)
    )
    with zipfile.ZipFile(next(target.glob("*.zip"))) as archive:
        assert archive.read("config/setting.yaml") == b"old config"
    assert existing_part.read_bytes() == b"user partial download"
    assert existing_tmp.read_bytes() == b"user temporary file"
    assert not list(source.glob(".*.snapshot"))
    _start(tmp_path, "5.9.0").finish()
    assert len(list(target.glob("*.zip"))) == 1


def test_move_directory_conflict_leaves_old_location_and_archive_untouched(tmp_path):
    _install(tmp_path, "5.7.0")
    _start(tmp_path, "5.8.0").finish()
    backup = _start(tmp_path, "5.9.0")
    backup.finish()
    source = tmp_path / "backup"
    originals = _archives(tmp_path)
    target = tmp_path / "new"
    target.mkdir()
    conflict = target / originals[1].name
    conflict.write_bytes(b"user file with the same name")

    with pytest.raises(FileExistsError):
        backup.move_directory(str(target), expected=str(source))
    assert _archives(tmp_path) == originals
    assert list(target.iterdir()) == [conflict]
    assert conflict.read_bytes() == b"user file with the same name"
    assert _start(tmp_path, "5.9.0").directory_info()["resolvedDirectory"] == str(
        source
    )


@pytest.mark.parametrize("move_back", [False, True])
def test_move_directory_recovers_locked_source_after_switch(
    tmp_path, monkeypatch, move_back
):
    _install(tmp_path, "5.8.0")
    backup = _start(tmp_path, "5.9.0")
    backup.finish()
    source = tmp_path / "backup"
    original = _archives(tmp_path)[0]
    target = tmp_path / "new"
    unlink = Path.unlink

    def lock_source(file: Path, *, missing_ok: bool = False) -> None:
        if file == original:
            raise PermissionError("old archive in use")
        unlink(file, missing_ok=missing_ok)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", lock_source)
        assert not backup.move_directory(str(target), expected=str(source))
        assert original.exists()
        assert (target / original.name).exists()
        if move_back:
            assert backup.move_directory(None, expected=str(target))

    restarted = _start(tmp_path, "5.9.0")
    restarted.finish()
    active = source if move_back else target
    inactive = target if move_back else source
    assert restarted.directory_info()["resolvedDirectory"] == str(active)
    assert not (inactive / original.name).exists()
    with zipfile.ZipFile(active / original.name) as archive:
        assert archive.testzip() is None


def test_disconnected_old_directory_does_not_block_rotation_or_more_moves(
    tmp_path, monkeypatch
):
    _install(tmp_path, "5.7.0")
    _start(tmp_path, "5.8.0").finish()
    backup = _start(tmp_path, "5.9.0")
    backup.finish()
    source = tmp_path / "backup"
    earliest, newer = _archives(tmp_path)
    target = tmp_path / "new"
    third = tmp_path / "third"
    unlink = Path.unlink

    def lock_old_archives(file: Path, *, missing_ok: bool = False) -> None:
        if file in {earliest, newer}:
            raise PermissionError("old archive in use")
        unlink(file, missing_ok=missing_ok)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", lock_old_archives)
        assert not backup.move_directory(str(target), expected=str(source))

    disconnected = source.rename(tmp_path / "disconnected")
    upgraded = _start(tmp_path, "6.1.0")
    upgraded.finish()
    assert not (target / earliest.name).exists()
    assert len(list(target.glob("*.zip"))) == 2
    assert not upgraded.move_directory(str(third), expected=str(target))
    assert upgraded.directory_info()["resolvedDirectory"] == str(third)
    assert not list(target.glob("*.zip"))
    assert len(list(third.glob("*.zip"))) == 2

    disconnected.rename(source)
    _start(tmp_path, "6.1.0").finish()
    assert not newer.exists()
    assert earliest.exists()  # The matching active archive has already rotated out.
    with zipfile.ZipFile(third / newer.name) as archive:
        assert archive.testzip() is None


def test_reset_to_default_creates_directory_and_survives_install_move(tmp_path):
    installation = tmp_path / "installation"
    installation.mkdir()
    _install(installation, "5.7.0")
    custom = tmp_path / "custom"
    _preferences(installation, enabled=True, directory=custom)
    _start(installation, "5.8.0").finish()
    earliest = next(custom.glob("*.zip"))
    backup = _start(installation, "5.9.0")
    backup.finish()
    default = installation / "backup"
    original = next(path for path in custom.glob("*.zip") if path != earliest)
    assert not default.exists()

    assert backup.move_directory(None, expected=str(custom))
    assert not original.exists()
    assert (default / original.name).exists()
    restarted = _start(installation, "5.9.0")
    assert restarted.directory_info()["directory"] is None

    foreign = tmp_path / "foreign"
    foreign.mkdir()
    _install(foreign, "5.8.0")
    _start(foreign, "5.9.0").finish()
    foreign_archive = _archives(foreign)[0]
    for file in (foreign / "backup").iterdir():
        shutil.copy2(file, default / file.name)

    relocated = installation.rename(tmp_path / "relocated")
    restarted = _start(relocated, "6.1.0")
    restarted.finish()
    previous_directory = relocated / "backup"
    assert restarted.directory_info()["resolvedDirectory"] == str(previous_directory)
    assert not (previous_directory / earliest.name).exists()
    owned_backups = {archive.name for archive in _archives(relocated)} - {
        foreign_archive.name
    }
    assert original.name in owned_backups
    assert len(owned_backups) == 2

    assert restarted.move_directory(str(custom), expected=str(previous_directory))
    assert {archive.name for archive in custom.glob("*.zip")} == owned_backups
    assert _archives(relocated) == [previous_directory / foreign_archive.name]


def test_locked_registration_after_install_move_does_not_block_new_backup(
    tmp_path, monkeypatch
):
    installation = tmp_path / "installation"
    installation.mkdir()
    _install(installation, "5.8.0")
    _start(installation, "5.9.0").finish()
    relocated = installation.rename(tmp_path / "relocated")
    previous = _archives(relocated)[0]
    registration = next(previous.parent.glob(".*.archive.json"))
    replace = Path.replace

    def replace_file(file: Path, target: Path) -> Path:
        if target == registration:
            raise PermissionError("archive registration in use")
        return replace(file, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", replace_file)
        _start(relocated, "5.9.1").finish()
    assert previous.exists()
    assert len(_archives(relocated)) == 2

    destination = tmp_path / "new-backups"
    restarted = _start(relocated, "5.9.1")
    assert restarted.move_directory(str(destination), expected=str(previous.parent))
    assert not previous.exists()
    assert (destination / previous.name).exists()


@pytest.mark.parametrize("temporarily_unavailable", [False, True])
def test_retry_uses_completed_snapshot_after_zip_publication_fails(
    tmp_path, monkeypatch, temporarily_unavailable
):
    _install(tmp_path, "5.8.0")
    config = tmp_path / "config" / "Config.json"
    config.write_bytes(b"old")

    def fail_to_publish(_snapshot: Path, _archive: Path) -> None:
        raise PermissionError("archive unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(upgrade_backup, "_pack_snapshot", fail_to_publish)
        startup = UpgradeBackup(root=tmp_path, desktop_version="5.9.0")
        assert startup.prepare() == "backup_failed"
        assert startup.begin_migration()
        startup.finish()
    assert _archives(tmp_path) == []

    config.write_bytes(b"migrated")
    if temporarily_unavailable:
        directory = tmp_path / "backup"
        disconnected = directory.rename(tmp_path / "disconnected")
        restarted = UpgradeBackup(root=tmp_path, desktop_version="5.9.0")
        assert restarted.prepare() == "snapshot_missing"
        assert restarted.begin_migration()
        restarted.finish()
        directory.rmdir()
        disconnected.rename(directory)
    _start(tmp_path, "5.9.0").finish()
    with zipfile.ZipFile(_archives(tmp_path)[0]) as archive:
        assert archive.read("config/Config.json") == b"old"


def test_failed_snapshot_does_not_relabel_migrated_data_or_remove_existing_zip(
    tmp_path, monkeypatch
):
    _install(tmp_path, "5.8.0")
    _start(tmp_path, "5.9.0-beta.1").finish()
    stable = _archives(tmp_path)[0]
    config = tmp_path / "config" / "Config.json"
    config.write_bytes(b"beta")

    def fail_to_capture(_root: Path, _snapshot: Path) -> None:
        raise PermissionError("old config is locked")

    with monkeypatch.context() as patch:
        patch.setattr(upgrade_backup, "_make_snapshot", fail_to_capture)
        startup = UpgradeBackup(root=tmp_path, desktop_version="5.9.0")
        assert startup.prepare() == "backup_failed"
        assert startup.begin_migration()
        startup.finish()
    config.write_bytes(b"migrated")
    restarted = UpgradeBackup(root=tmp_path, desktop_version="5.9.0")
    assert restarted.prepare() == "snapshot_missing"
    restarted.finish()
    assert _archives(tmp_path) == [stable]


@pytest.mark.parametrize("initialized_version", [None, "5.8.0"])
def test_first_start_establishes_baseline_without_archive(
    tmp_path, initialized_version
):
    _install(tmp_path, initialized_version)
    _start(tmp_path, "5.8.0").finish()
    assert not (tmp_path / "backup").exists()
    (tmp_path / "config" / "frontend_config.json").unlink(missing_ok=True)
    _start(tmp_path, "5.9.0").finish()
    assert len(_archives(tmp_path)) == 1


def test_interruption_before_migration_can_capture_unchanged_old_data(
    tmp_path, monkeypatch
):
    _install(tmp_path, "5.8.0")
    (tmp_path / "config" / "setting.yaml").write_bytes(b"old")

    def interrupt(_root: Path, _snapshot: Path) -> None:
        raise InterruptedError("capture did not complete")

    with monkeypatch.context() as patch:
        patch.setattr(upgrade_backup, "_make_snapshot", interrupt)
        startup = UpgradeBackup(root=tmp_path, desktop_version="5.9.0")
        assert startup.prepare() == "backup_failed"
        # 进程在进入迁移前退出，旧文件仍可用。

    _start(tmp_path, "5.9.0").finish()
    with zipfile.ZipFile(_archives(tmp_path)[0]) as archive:
        assert archive.read("config/setting.yaml") == b"old"


def test_migration_marker_prevents_wrong_backup_after_journal_failure(
    tmp_path, monkeypatch
):
    _install(tmp_path, "5.7.0")
    config = tmp_path / "config" / "setting.yaml"
    config.write_bytes(b"last good")
    _start(tmp_path, "5.8.0").finish()
    retained = _archives(tmp_path)
    config.write_bytes(b"old")
    write = upgrade_backup.atomic_write

    def lock_state(path: Path, data: bytes) -> None:
        if path.name == "upgrade-backup-state.json":
            raise PermissionError("state file is locked")
        write(path, data)

    with monkeypatch.context() as patch:
        patch.setattr(upgrade_backup, "atomic_write", lock_state)
        startup = UpgradeBackup(root=tmp_path, desktop_version="5.9.0")
        with pytest.raises(PermissionError):
            startup.prepare()
        assert not startup.begin_migration()
        config.write_bytes(b"migrated")

    restarted = UpgradeBackup(root=tmp_path, desktop_version="5.9.0")
    assert restarted.prepare() is None
    restarted.begin_migration()
    restarted.finish()
    assert _archives(tmp_path) == retained


def test_upgrading_after_failed_startup_preserves_last_working_backup(tmp_path):
    _install(tmp_path, "5.8.0")
    config = tmp_path / "config" / "setting.yaml"
    config.write_bytes(b"last good")
    _start(tmp_path, "5.9.0")
    retained = _archives(tmp_path)
    config.write_bytes(b"partially migrated")

    startup = UpgradeBackup(root=tmp_path, desktop_version="5.9.1")
    assert startup.prepare() == "source_not_ready"
    assert startup.begin_migration()
    startup.finish()
    assert _archives(tmp_path) == retained
    with zipfile.ZipFile(retained[0]) as archive:
        assert archive.read("config/setting.yaml") == b"last good"
