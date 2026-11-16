"""隔离文件系统故障，守住安装切换、恢复与不越界写入的公共契约。"""

import hashlib
import threading
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.services import script_install as install


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


def apply(package, *, validate=lambda root: None, idle=lambda: None):
    root, archive = package
    install.install_package(
        root,
        archive,
        archive.stat().st_size,
        hashlib.sha256(archive.read_bytes()).hexdigest(),
        frozenset({"config"}),
        validate,
        idle,
        threading.Event(),
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
    root, archive = package
    outside = root.parent / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_bytes(b"outside user data")
    entry = zipfile.ZipInfo("link")
    entry.create_system = 3
    entry.external_attr = 0o120777 << 16
    with zipfile.ZipFile(archive, "w") as payload:
        payload.writestr(entry, str(outside))
        payload.writestr("link/keep.txt", b"overwritten")
    with pytest.raises(ValueError):
        apply(package)
    assert sentinel.read_bytes() == b"outside user data"
    assert set(outside.iterdir()) == {sentinel}
    assert (root / "app.exe").read_bytes() == b"old"
    assert (root / "config/user.json").read_bytes() == b"user-owned"


def test_checksum_failure_and_candidate_failure_keep_old_install(package):
    root, archive = package
    with pytest.raises(ValueError):
        install.verify_archive(
            archive, archive.stat().st_size, "0" * 64, threading.Event()
        )
    with pytest.raises(ValueError):
        apply(package, validate=Mock(side_effect=ValueError("wrong architecture")))
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
