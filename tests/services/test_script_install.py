"""隔离文件系统故障，守住安装切换、恢复与不越界写入的公共契约。"""

import asyncio
import hashlib
import json
import threading
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.services import script_install as install
from app.task.MaaEnd.tools.pipeline_migration import refresh_merged_pipelines


@pytest.fixture
def package(tmp_path, isolated_app_paths):
    root = tmp_path / "installation"
    root.mkdir()
    (root / "app.exe").write_bytes(b"old")
    (root / "config").mkdir()
    (root / "config/user.json").write_bytes(b"user-owned")
    archive = tmp_path / "update.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("app.exe", b"new")
        package.writestr("resource/new.json", b"resource")
    return root, archive


def apply(package, **kwargs):
    root, archive = package
    install.install_package(
        root,
        archive,
        archive.stat().st_size,
        hashlib.sha256(archive.read_bytes()).hexdigest(),
        frozenset({"config"}),
        kwargs.get("validate", lambda root: None),
        kwargs.get("idle", lambda: None),
        kwargs.get("cancelled", threading.Event()),
        prepare_ready=kwargs.get("prepare_ready"),
    )


@pytest.mark.parametrize("receipt_failure", [False, True])
def test_install_commit_and_receipt_recovery_preserve_the_complete_tree(
    package, isolated_app_paths, monkeypatch, receipt_failure
):
    root, _ = package
    directory = install.workspace(root)
    if receipt_failure:
        replace = Path.replace

        def fail_receipt(path, target):
            if Path(target).name == "installed.json":
                raise OSError("receipt disk full")
            return replace(path, target)

        with monkeypatch.context() as filesystem:
            filesystem.setattr(Path, "replace", fail_receipt)
            with pytest.raises(install.InstallUnsafeError):
                apply(package)
        assert (directory / "previous/app.exe").read_bytes() == b"old"
        assert (directory / "transaction.json").is_file()
        assert (root / "app.exe").read_bytes() == b"new"
        install.recover_install(root, lambda: None, threading.Event())
        assert not (directory / "previous").exists()
        assert not (directory / "transaction.json").exists()
    else:
        apply(package)
    assert (root / "app.exe").read_bytes() == b"new"
    assert (root / "resource/new.json").read_bytes() == b"resource"
    assert (root / "config/user.json").read_bytes() == b"user-owned"
    receipts = list(
        (isolated_app_paths.data_path / "script_update").glob("*/installed.json")
    )
    assert len(receipts) == 1
    assert install.verify_installed_files(root, threading.Event())
    if not receipt_failure:
        assert not directory.exists()


@pytest.mark.parametrize("current_receipt", [False, True])
def test_legacy_cleanup_preserves_unknown_files_and_never_imports_or_overwrites_receipts(
    package, current_receipt
):
    root, _ = package
    if current_receipt:
        apply(package)
    receipt = install.record_directory(root) / "installed.json"
    confirmed = receipt.read_bytes() if current_receipt else None
    legacy = install.workspace(root)
    backup = legacy / "retired-pipelines/custom.json"
    note = legacy / "notes.txt"
    for keep_unknown in (True, False):
        legacy.mkdir(exist_ok=True)
        for name in ("installed.json", "program-identity.json", "baah-version.json"):
            (legacy / name).write_bytes(b"old record")
        if keep_unknown:
            backup.parent.mkdir()
            backup.write_bytes(b"user resource")
            note.write_bytes(b"user note")
        else:
            backup.unlink()
            backup.parent.rmdir()
            note.unlink()
            (legacy / "installed.json").write_text(
                json.dumps({"files": {"app.exe": hashlib.sha256(b"old").hexdigest()}})
            )
        if not current_receipt:
            assert not install.verify_installed_files(root, threading.Event())
        install.recover_install(root, lambda: None, threading.Event())
        for name in ("installed.json", "program-identity.json", "baah-version.json"):
            assert not (legacy / name).exists()
        if keep_unknown:
            assert backup.read_bytes() == b"user resource"
            assert note.read_bytes() == b"user note"
        else:
            assert not legacy.exists()
        if current_receipt:
            assert receipt.read_bytes() == confirmed
            assert install.verify_installed_files(root, threading.Event())
        else:
            assert not install.record_directory(root).exists()
            assert not install.verify_installed_files(root, threading.Event())
        assert (root / "app.exe").read_bytes() == (
            b"new" if current_receipt else b"old"
        )


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/absolute",
        "C:/evil",
        "a/../../evil",
        "a\\..\\evil",
        "file:stream",
        "CON.txt",
        "a./file",
        "a /file",
    ],
)
def test_malformed_members_never_modify_installation(package, name):
    root, archive = package
    with zipfile.ZipFile(archive, "w") as payload:
        payload.writestr(name, b"bad")
    with pytest.raises((ValueError, OSError)):
        apply(package)
    assert (root / "app.exe").read_bytes() == b"old"
    assert not (root.parent / "outside").exists()


def test_case_collision_and_protected_config_are_rejected(package):
    root, archive = package
    for names in (("App.exe", "app.exe"), ("CONFIG/user.json",)):
        with zipfile.ZipFile(archive, "w") as payload:
            for name in names:
                payload.writestr(name, b"bad")
        with pytest.raises(ValueError):
            apply(package)
    assert (root / "config/user.json").read_bytes() == b"user-owned"


def test_zip_symlink_rejected(package):
    _, archive = package
    entry = zipfile.ZipInfo("link")
    entry.create_system = 3
    entry.external_attr = 0o120777 << 16
    with zipfile.ZipFile(archive, "w") as payload:
        payload.writestr(entry, "../outside")
    with pytest.raises(ValueError):
        apply(package)


def test_checksum_failure_and_candidate_failure_keep_old_install(package):
    root, archive = package
    with pytest.raises(ValueError):
        install.verify_archive(
            archive, archive.stat().st_size, "0" * 64, threading.Event()
        )
    with pytest.raises(ValueError):
        apply(package, validate=Mock(side_effect=ValueError("wrong architecture")))
    assert (root / "app.exe").read_bytes() == b"old"


def test_interrupted_first_rename_recovers_even_with_missing_executable(
    package, monkeypatch
):
    root, _ = package
    replace = Path.replace

    def die_after_move(path, target):
        result = replace(path, target)
        if path == root:
            raise SystemExit("simulated process exit")
        return result

    monkeypatch.setattr(Path, "replace", die_after_move)
    with pytest.raises(install.InstallUnsafeError):
        apply(package)
    assert not root.exists()
    monkeypatch.setattr(Path, "replace", replace)
    install.recover_install(root, lambda: None, threading.Event())
    assert (root / "app.exe").read_bytes() == b"old"


def leave_new_unconfirmed(package):
    count = 0

    def idle():
        nonlocal count
        count += 1
        if count == 3:
            raise install.InstallUnsafeError("process appeared")

    with pytest.raises(install.InstallUnsafeError):
        apply(package, idle=idle)


def test_recovery_verifies_all_files_not_just_version(package):
    root, _ = package
    leave_new_unconfirmed(package)
    assert (install.workspace(root) / "previous/app.exe").read_bytes() == b"old"
    (root / "resource/new.json").write_bytes(b"external modification")
    with pytest.raises(install.InstallUnsafeError):
        install.recover_install(root, lambda: None, threading.Event())
    assert (root / "resource/new.json").read_bytes() == b"external modification"
    assert (install.workspace(root) / "previous/app.exe").read_bytes() == b"old"


def test_verified_recovery_commits_new_tree(package):
    root, _ = package
    leave_new_unconfirmed(package)
    install.recover_install(root, lambda: None, threading.Event())
    assert (root / "app.exe").read_bytes() == b"new"
    assert not (install.workspace(root) / "previous").exists()


def test_corrupt_journal_cannot_be_bypassed(package):
    root, _ = package
    directory = install.workspace(root)
    directory.mkdir()
    (directory / "transaction.json").write_text("broken json")
    with pytest.raises(install.InstallUnsafeError):
        install.recover_install(root, lambda: None, threading.Event())
    assert (root / "app.exe").read_bytes() == b"old"


def test_external_change_during_copy_is_preserved(package, monkeypatch):
    root, _ = package
    copy = install.shutil.copytree

    def change_source(source, target, *args, **kwargs):
        result = copy(source, target, *args, **kwargs)
        if source == root:
            (root / "config/user.json").write_bytes(b"changed outside")
        return result

    monkeypatch.setattr(install.shutil, "copytree", change_source)
    with pytest.raises(install.InstallUnsafeError):
        apply(package)
    assert (root / "config/user.json").read_bytes() == b"changed outside"
    assert (root / "app.exe").read_bytes() == b"old"


@pytest.mark.parametrize(
    "fault,expected_user",
    [("late_edit", b"modified after last check"), ("publish", b"user-owned")],
)
def test_install_switch_failure_restores_old_program_without_overwriting_user_data(
    package, monkeypatch, fault, expected_user
):
    root, _ = package
    calls = 0

    def idle():
        nonlocal calls
        calls += 1
        if fault == "late_edit" and calls == 2:
            (root / "config/user.json").write_bytes(b"modified after last check")

    replace = Path.replace

    def fail_ready(path, target):
        if fault == "publish" and path.name == "ready":
            raise PermissionError("file occupied")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_ready)
    with pytest.raises(install.InstallUnsafeError):
        apply(package, idle=idle)
    assert (root / "app.exe").read_bytes() == b"old"
    assert (root / "config/user.json").read_bytes() == expected_user
    assert not (install.workspace(root) / "previous").exists()
    if fault == "publish":
        assert not (install.workspace(root) / "transaction.json").exists()


def test_modified_previous_survives_recovery(package):
    root, _ = package
    calls = 0

    def idle():
        nonlocal calls
        calls += 1
        if calls == 3:
            (install.workspace(root) / "previous/config/user.json").write_bytes(
                b"changed during commit"
            )

    with pytest.raises(install.InstallUnsafeError):
        apply(package, idle=idle)
    backup = install.workspace(root) / "previous/config/user.json"
    assert backup.read_bytes() == b"changed during commit"
    with pytest.raises(install.InstallUnsafeError):
        install.recover_install(root, lambda: None, threading.Event())
    assert backup.read_bytes() == b"changed during commit"


def test_same_installation_access_is_exclusive(package):
    root, _ = package
    with install.installation_access(root):
        with pytest.raises(install.InstallUnsafeError):
            with install.installation_access(root):
                pytest.fail("lock not exclusive")
    with install.installation_access(root):
        pass


def test_installed_receipt_checks_resources_and_ignores_user_configuration(package):
    root, _ = package
    apply(package)
    assert install.verify_installed_files(root, threading.Event())
    (root / "config/user.json").write_bytes(b"updated by user")
    assert install.verify_installed_files(root, threading.Event())
    (root / "resource/new.json").write_bytes(b"damaged")
    assert not install.verify_installed_files(root, threading.Event())


def test_new_release_removes_only_previously_managed_obsolete_files(package):
    root, archive = package
    apply(package)
    (root / "user-notes.txt").write_bytes(b"keep")
    with zipfile.ZipFile(archive, "w") as payload:
        payload.writestr("app.exe", b"newer")
        payload.writestr("resource/next.json", b"next")
    apply(package)
    assert not (root / "resource/new.json").exists()
    assert (root / "resource/next.json").read_bytes() == b"next"
    assert (root / "user-notes.txt").read_bytes() == b"keep"


def test_pipeline_adoption_preserves_live_files_on_backup_failure_then_retries(
    package, monkeypatch
):
    root, archive = package
    old_pipeline = root / "resource/pipeline"
    old_pipeline.mkdir(parents=True)
    old_split = b'{"AutoCollectSchedule": {"action": "Custom"}}'
    (old_pipeline / "AutoCollect.json").write_bytes(old_split)
    (old_pipeline / "Custom.json").write_text('{"UserNode": {}}')
    (old_pipeline / "Old.json").write_text('{"Original": {}}')
    (root / "resource_extra/pipeline").mkdir(parents=True)
    (root / "resource_extra/pipeline/Old.json").write_text('{"Other": {}}')
    with zipfile.ZipFile(archive, "w") as payload:
        payload.writestr("app.exe", b"new")
        payload.writestr("resource/pipeline/nodes.json", old_split)
        payload.writestr("resource_extra/pipeline/nodes.json", '{"Other": {}}')
    original_copytree = install.shutil.copytree

    def fail_when_saving_pipeline(source, target, *args, **kwargs):
        # 递归来源可能是 DirEntry；只打断隔离备份，不影响前面的安装暂存复制。
        if Path(source).name == "pipeline" and Path(target).is_relative_to(
            install.workspace(root) / "retired-pipelines"
        ):
            raise OSError("quarantine unavailable")
        return original_copytree(source, target, *args, **kwargs)

    with monkeypatch.context() as filesystem:
        filesystem.setattr(install.shutil, "copytree", fail_when_saving_pipeline)
        with pytest.raises(OSError, match="quarantine unavailable"):
            apply(package, prepare_ready=refresh_merged_pipelines)
    assert (root / "app.exe").read_bytes() == b"old"
    assert (old_pipeline / "Old.json").read_text() == '{"Original": {}}'
    assert (old_pipeline / "AutoCollect.json").read_bytes() == old_split
    apply(package, prepare_ready=refresh_merged_pipelines)
    assert (root / "resource/pipeline/nodes.json").read_bytes() == old_split
    assert not (root / "resource/pipeline/AutoCollect.json").exists()
    assert not (root / "resource/pipeline/Custom.json").exists()
    assert not (root / "resource_extra/pipeline/Old.json").exists()
    backup_root = install.workspace(root) / "retired-pipelines"
    backups = list(backup_root.glob("pipeline-*/resource/pipeline/AutoCollect.json"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == old_split
    assert list(backup_root.glob("pipeline-*/resource/pipeline/Custom.json"))
    assert list(backup_root.glob("pipeline-*/resource/pipeline/Old.json"))
    assert (
        next(backup_root.glob("pipeline-*/resource/pipeline/Custom.json")).read_text()
        == '{"UserNode": {}}'
    )
    assert (
        next(backup_root.glob("pipeline-*/resource/pipeline/Old.json")).read_text()
        == '{"Original": {}}'
    )
    assert list(backup_root.glob("pipeline-*/resource_extra/pipeline/Old.json"))
    assert install.verify_installed_files(root, threading.Event())
    assert not (install.workspace(root) / "previous").exists()


def test_low_disk_space_stops_before_original_is_changed(package, monkeypatch):
    root, _ = package
    monkeypatch.setattr(
        install.shutil, "disk_usage", lambda path: type("Usage", (), {"free": 0})()
    )
    with pytest.raises(OSError):
        apply(package)
    assert (root / "app.exe").read_bytes() == b"old"


@pytest.mark.asyncio
async def test_cancel_waits_for_worker_to_stop():
    started, stopped = threading.Event(), threading.Event()

    def worker(cancelled):
        started.set()
        cancelled.wait(timeout=5)
        stopped.set()
        raise InterruptedError()

    task = asyncio.create_task(install.run_worker(worker))
    await asyncio.to_thread(started.wait, 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()


def test_missing_install_root_rejects_damaged_previous_backup(package, monkeypatch):
    root, _ = package
    replace = Path.replace

    def fail_after_original_moved(path, target):
        result = replace(path, target)
        if path == root:
            raise SystemExit("simulated interruption")
        return result

    monkeypatch.setattr(Path, "replace", fail_after_original_moved)
    with pytest.raises(install.InstallUnsafeError):
        apply(package)
    monkeypatch.setattr(Path, "replace", replace)
    previous = install.workspace(root) / "previous"
    assert previous.exists() and not root.exists()
    (previous / "app.exe").write_bytes(b"externally changed")
    with pytest.raises(install.InstallUnsafeError, match="备份不完整"):
        install.recover_install(root, lambda: None, threading.Event())
    assert (previous / "app.exe").read_bytes() == b"externally changed"
    assert (install.workspace(root) / "transaction.json").exists()


@pytest.mark.parametrize("legacy_receipt", [False, True])
def test_interrupted_backup_cleanup_can_safely_finish_on_next_run(
    package, monkeypatch, legacy_receipt
):
    root, _ = package
    old_rmtree = install.shutil.rmtree
    previous = install.workspace(root) / "previous"

    def fail_cleanup(path, *args, **kwargs):
        if Path(path) == previous:
            (previous / "app.exe").unlink()
            raise OSError("simulated interrupted backup cleanup")
        return old_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(install.shutil, "rmtree", fail_cleanup)
    with pytest.raises(install.InstallUnsafeError):
        apply(package)
    monkeypatch.setattr(install.shutil, "rmtree", old_rmtree)
    assert (root / "app.exe").read_bytes() == b"new"
    assert previous.exists()
    if legacy_receipt:
        (install.record_directory(root) / "installed.json").replace(
            install.workspace(root) / "installed.json"
        )
    install.recover_install(root, lambda: None, threading.Event())
    assert install.record_path(root, "installed.json").is_file()
    assert install.verify_installed_files(root, threading.Event())
    assert not (install.workspace(root) / "installed.json").exists()
    assert (root / "app.exe").read_bytes() == b"new"
    assert not previous.exists()
    assert not (install.workspace(root) / "transaction.json").exists()


def test_interrupted_backup_cleanup_keeps_external_modifications(package, monkeypatch):
    root, _ = package
    old_rmtree = install.shutil.rmtree
    previous = install.workspace(root) / "previous"

    def fail_cleanup(path, *args, **kwargs):
        if Path(path) == previous:
            (previous / "app.exe").unlink()
            raise OSError("simulated interrupted cleanup")
        return old_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(install.shutil, "rmtree", fail_cleanup)
    with pytest.raises(install.InstallUnsafeError):
        apply(package)
    monkeypatch.setattr(install.shutil, "rmtree", old_rmtree)
    (previous / "config/user.json").write_bytes(b"external modification")
    with pytest.raises(install.InstallUnsafeError, match="备份发生外部修改"):
        install.recover_install(root, lambda: None, threading.Event())
    assert (previous / "config/user.json").read_bytes() == b"external modification"
