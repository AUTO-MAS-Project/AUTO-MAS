"""隔离文件系统故障，守住安装切换、恢复与不越界写入的公共契约。"""

import asyncio
import hashlib
import threading
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.services import script_install as install


@pytest.fixture
def package(tmp_path):
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
    )


def test_switch_preserves_user_data_and_confirms_complete_tree(package):
    root, _ = package
    apply(package)
    assert (root / "app.exe").read_bytes() == b"new"
    assert (root / "resource/new.json").read_bytes() == b"resource"
    assert (root / "config/user.json").read_bytes() == b"user-owned"
    assert not (install.workspace(root) / "transaction.json").exists()
    assert not (install.workspace(root) / "previous").exists()


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


def test_failed_second_rename_restores_old_directory(package, monkeypatch):
    root, _ = package
    replace = Path.replace

    def fail_ready(path, target):
        if path.name == "ready":
            raise PermissionError("file occupied")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_ready)
    with pytest.raises(install.InstallUnsafeError):
        apply(package)
    assert (root / "app.exe").read_bytes() == b"old"
    assert not (install.workspace(root) / "transaction.json").exists()


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
