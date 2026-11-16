"""M7A package version validation and transaction rollback regression tests."""

from __future__ import annotations

import zipfile

import pytest

from app.task.HSR.tools.update import apply
from app.task.HSR.tools.update.discover import HSRUpdateError


def _install(root, version="v2026.11.8"):
    marker = root / "assets" / "config" / "version.txt"
    marker.parent.mkdir(parents=True)
    marker.write_text(version, encoding="utf-8")
    (root / "March7th Assistant.exe").write_bytes(b"old exe")
    return marker


def _package(path, version=None, exe=b"new exe"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("update/March7th Assistant.exe", exe)
        if version is not None:
            archive.writestr("update/assets/config/version.txt", version)


def _apply(package, root):
    return apply.apply_package(
        package,
        root,
        engine="M7A",
        from_version="v2026.11.8",
        to_version="v2026.11.17",
        seven_zip=None,
    )


@pytest.mark.parametrize("marker", [None, "v2026.11.8"])
def test_m7a_rejects_missing_or_stale_package_marker(tmp_path, marker):
    root = tmp_path / "install"
    old_marker = _install(root)
    package = tmp_path / "update.zip"
    _package(package, marker)
    with pytest.raises(HSRUpdateError, match="版本标记不匹配"):
        _apply(package, root)
    assert old_marker.read_text(encoding="utf-8") == "v2026.11.8"
    assert (root / "March7th Assistant.exe").read_bytes() == b"old exe"


def test_m7a_valid_package_updates_marker(tmp_path):
    root = tmp_path / "install"
    marker = _install(root)
    package = tmp_path / "update.zip"
    _package(package, "v2026.11.17")
    result = _apply(package, root)
    assert result.changed_files == 2
    assert marker.read_text(encoding="utf-8") == "v2026.11.17"
    assert not apply.has_pending_journal(root)


def test_m7a_postcommit_verification_failure_rolls_back(tmp_path, monkeypatch):
    root = tmp_path / "install"
    marker = _install(root)
    package = tmp_path / "update.zip"
    _package(package, "v2026.11.17")
    original = apply.read_installed_version

    def misleading_probe(spec, path):
        if path == root:
            return "v2026.11.8"
        return original(spec, path)

    monkeypatch.setattr(apply, "read_installed_version", misleading_probe)
    with pytest.raises(apply.HSRUpdateApplyError, match="版本校验失败") as exc:
        _apply(package, root)
    assert exc.value.rolled_back
    assert marker.read_text(encoding="utf-8") == "v2026.11.8"
    assert (root / "March7th Assistant.exe").read_bytes() == b"old exe"


def test_m7a_rejects_nested_folder_with_extra_top_level_entry(tmp_path):
    root = tmp_path / "install"
    marker = _install(root)
    package = tmp_path / "update.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("March7thAssistant/March7th Assistant.exe", b"new exe")
        archive.writestr("March7thAssistant/assets/config/version.txt", "v2026.11.17")
        archive.writestr("release-notes.txt", "notes")
    with pytest.raises(HSRUpdateError, match="安装根目录不明确"):
        _apply(package, root)
    assert marker.read_text(encoding="utf-8") == "v2026.11.8"
    assert not (root / "March7thAssistant").exists()


def test_m7a_full_zip_single_root_installs_into_existing_root(tmp_path):
    root = tmp_path / "install"
    marker = _install(root)
    package = tmp_path / "mirror.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("March7thAssistant_full/March7th Assistant.exe", b"new exe")
        archive.writestr(
            "March7thAssistant_full/assets/config/version.txt", "v2026.11.17"
        )
    result = _apply(package, root)
    assert result.changed_files == 2
    assert marker.read_text(encoding="utf-8") == "v2026.11.17"
    assert not (root / "March7thAssistant_full").exists()


def test_m7a_full_zip_with_readme_installs_without_nested_directory(tmp_path):
    root = tmp_path / "install"
    marker = _install(root)
    package = tmp_path / "mirror.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("March7thAssistant_full/March7th Assistant.exe", b"new exe")
        archive.writestr(
            "March7thAssistant_full/assets/config/version.txt", "v2026.11.17"
        )
        archive.writestr("README.md", "release notes")
    result = _apply(package, root)
    assert result.changed_files == 2
    assert marker.read_text(encoding="utf-8") == "v2026.11.17"
    assert not (root / "March7thAssistant_full").exists()
