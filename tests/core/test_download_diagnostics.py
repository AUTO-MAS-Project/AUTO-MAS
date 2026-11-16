"""Regression tests for bounded cross-script download diagnostics."""

import zipfile

from app.core.download_diagnostics import describe_package, safe_origin


def test_signed_urls_are_reduced_to_origin():
    assert (
        safe_origin(
            "https://person:secret@example.com/updates/file.zip?cdk=secret&token=123"
        )
        == "https://example.com"
    )
    assert safe_origin("invalid") == "(hidden)"


def test_m7a_nested_root_and_version_marker(tmp_path):
    package = tmp_path / "m7a.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("March7thAssistant/assets/config/version.txt", "v2026.11.17")
        archive.writestr("release-notes.txt", "not secret")
    data = describe_package(package)
    assert data["format"] == "zip"
    assert data["root_count"] == 2
    assert data["known_roots"] == ["March7thAssistant"]
    assert data["version_markers"] == [
        {"name": "version.txt", "version": "v2026.11.17"}
    ]
    assert "release-notes.txt" not in str(data)


def test_opaque_executable_does_not_claim_invalid_zip(tmp_path):
    package = tmp_path / "setup.exe"
    package.write_bytes(b"MZ" + b"0" * 20)
    assert describe_package(package)["format"] == "opaque"


def test_invalid_zip_signature_is_reported_without_extraction(tmp_path):
    package = tmp_path / "broken.zip"
    package.write_bytes(b"PK" + b"broken")
    assert describe_package(package)["format"] == "zip-invalid"
