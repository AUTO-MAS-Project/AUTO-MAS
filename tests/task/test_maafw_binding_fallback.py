"""MaaFW binding 兜底（``runtime_pool/binding_fallback``）的纯逻辑回归。

PyPI 缺 ``maafw==X`` 时运行池从 MaaFramework tag 源码包自打 wheel。本文件只覆盖
PEP 440 → tag 映射、uv 缺包文本判据、源码包校验与 wheel 打包这几块纯逻辑；
源码包用一个照真实 tag 包形状（唯一顶层目录 ``MaaFramework-<tag 去 v>/``、
``source/binding/Python/{maa,pyproject.toml}``、根 ``LICENSE.md``）手工造的最小 zip，
不联网、不起子进程。
"""

from __future__ import annotations

import base64
import hashlib
import zipfile
from pathlib import Path

import pytest

from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.binding_fallback import (
    BINDING_SRC_CACHE_RELATIVE_PATH,
    BINDING_WHEEL_CACHE_RELATIVE_PATH,
    NO_BUNDLED_DLL_MARKER_NAME,
    MaaFWBindingFallbackError,
    build_binding_wheel,
    ensure_binding_wheel,
    local_wheel_requirement,
    maafw_version_missing_from_index,
    pep440_to_maafw_tag,
    source_archive_candidates,
    validate_source_archive,
)

# uv 0.11.26 对 ``uv pip install maafw==5.14.0b1`` 的 stderr 原文（含 60 列折行）。
UV_MISSING_VERSION_STDERR = (
    "  × No solution found when resolving dependencies:\n"
    "  ╰─▶ Because there is no version of maafw==5.14.0b1 and you require\n"
    "      maafw==5.14.0b1, we can conclude that your requirements are\n"
    "      unsatisfiable.\n"
)
UV_NOT_IN_REGISTRY_STDERR = (
    "  × No solution found when resolving dependencies:\n"
    "  ╰─▶ Because maafw was not found in the package registry and you\n"
    "      require maafw==5.14.0b1, we can conclude that your requirements\n"
    "      are unsatisfiable.\n"
)
UV_OFFLINE_STDERR = (
    "  × No solution found when resolving dependencies:\n"
    "  ╰─▶ Because maafw was not found in the cache and you require\n"
    "      maafw==5.14.0b1, we can conclude that your requirements are\n"
    "      unsatisfiable.\n"
)
UV_NETWORK_STDERR = (
    "error: Failed to fetch: `https://pypi.org/simple/maafw/`\n"
    "  Caused by: Request failed after 3 retries\n"
)

PYPROJECT_TEXT = """[project]
name = "MaaFw"
version = "0"
requires-python = ">=3.9"
dependencies = ["numpy", "strenum", "MaaAgentBinary"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
"""


def _make_source_zip(
    path: Path,
    *,
    top: str = "MaaFramework-5.14.0-beta.1",
    with_license: bool = True,
    with_library: bool = True,
    pyproject: str = PYPROJECT_TEXT,
    extra_top: str | None = None,
) -> Path:
    base = f"{top}/source/binding/Python/"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{top}/", "")
        zf.writestr(f"{top}/README.md", "# MaaFramework\n")
        if with_license:
            zf.writestr(f"{top}/LICENSE.md", "GNU LESSER GENERAL PUBLIC LICENSE\n")
        zf.writestr(f"{base}pyproject.toml", pyproject)
        zf.writestr(f"{base}README.md", "binding readme\n")
        zf.writestr(f"{base}maa/__init__.py", "from .library import Library\n")
        if with_library:
            zf.writestr(f"{base}maa/library.py", "class Library: ...\n")
        zf.writestr(f"{base}maa/agent/__init__.py", "")
        zf.writestr(f"{base}maa/agent/agent_server.py", "AGENT = 1\n")
        zf.writestr(f"{base}maa/__pycache__/library.cpython-312.pyc", b"\x00")
        if extra_top:
            zf.writestr(f"{extra_top}/x.txt", "")
    return path


# ---------------------------------------------------------------------------
# PEP 440 ↔ git tag
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("version", "tag"),
    [
        ("5.14.0b1", "v5.14.0-beta.1"),
        ("5.14.0a2", "v5.14.0-alpha.2"),
        ("5.14.0rc1", "v5.14.0-rc.1"),
        ("5.13.1", "v5.13.1"),
        ("5.13.0", "v5.13.0"),
        # str(Version()) 规范化：beta1 / BETA.1 都是 b1
        ("5.14.0-beta.1", "v5.14.0-beta.1"),
        ("5.14.0.beta1", "v5.14.0-beta.1"),
    ],
)
def test_pep440_to_tag_maps_release_and_prerelease(version: str, tag: str) -> None:
    assert pep440_to_maafw_tag(version) == tag


@pytest.mark.parametrize(
    "version",
    [
        "5.13.1.post6",  # nightly：v5.13.1-post.6-ci.<id>，tag 与 PyPI 都没有
        "5.14.0.dev3",
        "5.13.1+local",
        "5.14.0b1.post1",
        "not-a-version",
        "",
    ],
)
def test_pep440_to_tag_rejects_post_dev_local_and_garbage(version: str) -> None:
    assert pep440_to_maafw_tag(version) is None


def test_source_archive_candidates_prefer_codeload_then_github_archive() -> None:
    assert source_archive_candidates("v5.14.0-beta.1") == (
        "https://codeload.github.com/MaaXYZ/MaaFramework/zip/refs/tags/v5.14.0-beta.1",
        "https://github.com/MaaXYZ/MaaFramework/archive/refs/tags/v5.14.0-beta.1.zip",
    )


# ---------------------------------------------------------------------------
# uv 缺包文本判据
# ---------------------------------------------------------------------------


def test_missing_version_matches_uv_no_version_text_across_line_wrap() -> None:
    assert maafw_version_missing_from_index(UV_MISSING_VERSION_STDERR)


def test_missing_version_matches_uv_not_in_registry_text() -> None:
    assert maafw_version_missing_from_index(UV_NOT_IN_REGISTRY_STDERR)


@pytest.mark.parametrize(
    "text",
    [UV_OFFLINE_STDERR, UV_NETWORK_STDERR, "", None, "connection reset"],
)
def test_missing_version_does_not_match_offline_or_network_failures(text) -> None:
    assert not maafw_version_missing_from_index(text)


# ---------------------------------------------------------------------------
# 源码包校验
# ---------------------------------------------------------------------------


def test_validate_source_archive_reads_dependencies_verbatim(tmp_path: Path) -> None:
    info = validate_source_archive(_make_source_zip(tmp_path / "src.zip"))
    assert info.top_level == "MaaFramework-5.14.0-beta.1"
    assert info.dependencies == ("numpy", "strenum", "MaaAgentBinary")
    assert info.requires_python == ">=3.9"


def test_validate_source_archive_rejects_multiple_top_levels(tmp_path: Path) -> None:
    archive = _make_source_zip(tmp_path / "src.zip", extra_top="other")
    with pytest.raises(MaaFWBindingFallbackError, match="顶层目录不唯一"):
        validate_source_archive(archive)


def test_validate_source_archive_rejects_missing_license(tmp_path: Path) -> None:
    archive = _make_source_zip(tmp_path / "src.zip", with_license=False)
    with pytest.raises(MaaFWBindingFallbackError, match="LICENSE.md"):
        validate_source_archive(archive)


def test_validate_source_archive_rejects_missing_library_module(tmp_path: Path) -> None:
    archive = _make_source_zip(tmp_path / "src.zip", with_library=False)
    with pytest.raises(MaaFWBindingFallbackError, match="maa/library.py"):
        validate_source_archive(archive)


def test_validate_source_archive_rejects_non_zip(tmp_path: Path) -> None:
    bogus = tmp_path / "src.zip"
    bogus.write_bytes(b"<html>not a zip</html>")
    with pytest.raises(MaaFWBindingFallbackError, match="不是合法 zip"):
        validate_source_archive(bogus)


# ---------------------------------------------------------------------------
# wheel 打包
# ---------------------------------------------------------------------------


def _record_digest(data: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def test_build_wheel_layout_metadata_and_record(tmp_path: Path) -> None:
    archive = _make_source_zip(tmp_path / "src.zip")
    wheel = build_binding_wheel(
        archive, "5.14.0b1", tmp_path / "wheels", tag="v5.14.0-beta.1"
    )
    assert wheel.name == "maafw-5.14.0b1-py3-none-any.whl"

    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        # 包内容：maa/** 剔 __pycache__，占位文件在 maa/bin/
        assert "maa/__init__.py" in names
        assert "maa/library.py" in names
        assert "maa/agent/agent_server.py" in names
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)
        assert f"maa/bin/{NO_BUNDLED_DLL_MARKER_NAME}" in names
        assert not any(name.endswith(".dll") for name in names)
        # 不带源码包里 binding 目录以外的东西
        assert not any(name.startswith("MaaFramework-") for name in names)
        assert "README.md" not in names

        dist_info = "maafw-5.14.0b1.dist-info"
        assert f"{dist_info}/licenses/LICENSE.md" in names
        metadata = zf.read(f"{dist_info}/METADATA").decode("utf-8")
        lines = metadata.splitlines()
        assert "Metadata-Version: 2.1" in lines
        assert "Name: maafw" in lines
        assert "Version: 5.14.0b1" in lines
        assert "Requires-Python: >=3.9" in lines
        assert "Requires-Dist: numpy" in lines
        assert "Requires-Dist: strenum" in lines
        # D7：MaaAgentBinary 必须保留
        assert "Requires-Dist: MaaAgentBinary" in lines
        assert "License-File: LICENSE.md" in lines
        assert any(
            line.startswith("Summary: ") and "v5.14.0-beta.1" in line for line in lines
        )

        wheel_meta = zf.read(f"{dist_info}/WHEEL").decode("utf-8").splitlines()
        assert "Wheel-Version: 1.0" in wheel_meta
        assert "Root-Is-Purelib: true" in wheel_meta
        assert "Tag: py3-none-any" in wheel_meta

        # RECORD 逐行哈希与大小正确，覆盖 zip 里每个成员，自身行留空
        record_lines = zf.read(f"{dist_info}/RECORD").decode("utf-8").splitlines()
        record = {}
        for line in record_lines:
            path, digest, size = line.rsplit(",", 2)
            record[path] = (digest, size)
        assert set(record) == set(names)
        assert record[f"{dist_info}/RECORD"] == ("", "")
        for name in names:
            if name == f"{dist_info}/RECORD":
                continue
            data = zf.read(name)
            assert record[name] == (f"sha256={_record_digest(data)}", str(len(data))), (
                name
            )


def test_build_wheel_normalizes_version_in_all_three_places(tmp_path: Path) -> None:
    archive = _make_source_zip(tmp_path / "src.zip")
    wheel = build_binding_wheel(
        archive, "5.14.0-beta.1", tmp_path / "wheels", tag="v5.14.0-beta.1"
    )
    assert wheel.name == "maafw-5.14.0b1-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as zf:
        assert "maafw-5.14.0b1.dist-info/METADATA" in zf.namelist()
        assert (
            "Version: 5.14.0b1" in zf.read("maafw-5.14.0b1.dist-info/METADATA").decode()
        )


def test_build_wheel_reuses_cached_wheel(tmp_path: Path) -> None:
    archive = _make_source_zip(tmp_path / "src.zip")
    first = build_binding_wheel(
        archive, "5.14.0b1", tmp_path / "wheels", tag="v5.14.0-beta.1"
    )
    stamp = first.stat().st_mtime_ns
    payload = first.read_bytes()
    second = build_binding_wheel(
        archive, "5.14.0b1", tmp_path / "wheels", tag="v5.14.0-beta.1"
    )
    assert second == first
    assert second.stat().st_mtime_ns == stamp
    assert second.read_bytes() == payload


def test_build_wheel_rejects_invalid_version(tmp_path: Path) -> None:
    archive = _make_source_zip(tmp_path / "src.zip")
    with pytest.raises(MaaFWBindingFallbackError, match="版本不合法"):
        build_binding_wheel(archive, "v5.14.0-beta.x", tmp_path / "wheels", tag="x")


def test_local_wheel_requirement_is_file_uri_with_forward_slashes(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "maafw-5.14.0b1-py3-none-any.whl"
    wheel.write_bytes(b"")
    requirement = local_wheel_requirement(wheel)
    assert requirement.startswith("maafw @ file:///")
    assert "\\" not in requirement
    assert requirement.endswith("/maafw-5.14.0b1-py3-none-any.whl")


# ---------------------------------------------------------------------------
# ensure_binding_wheel：缓存命中不下载、不重打
# ---------------------------------------------------------------------------


def test_ensure_binding_wheel_uses_cached_source_and_wheel(
    tmp_path: Path, monkeypatch
) -> None:
    pool_root = tmp_path / "pool"
    src_dir = pool_root / BINDING_SRC_CACHE_RELATIVE_PATH
    src_dir.mkdir(parents=True)
    _make_source_zip(src_dir / "v5.14.0-beta.1.zip")

    def _no_network(*_args, **_kwargs):
        raise AssertionError("缓存命中时不得联网")

    monkeypatch.setattr(
        "app.task.MaaFW.tools.core.automas_maafw_runtime_pool.binding_fallback._download_to_file",
        _no_network,
    )
    logs: list[str] = []
    wheel, tag = ensure_binding_wheel("5.14.0b1", pool_root, log=logs.append)
    assert tag == "v5.14.0-beta.1"
    assert (
        wheel
        == pool_root
        / BINDING_WHEEL_CACHE_RELATIVE_PATH
        / "maafw-5.14.0b1-py3-none-any.whl"
    )
    assert wheel.is_file()

    # wheel 缓存命中：源码包与 build 都不再碰
    src_zip = src_dir / "v5.14.0-beta.1.zip"
    src_zip.unlink()
    again, _ = ensure_binding_wheel("5.14.0b1", pool_root)
    assert again == wheel


def test_ensure_binding_wheel_refuses_versions_without_tag(tmp_path: Path) -> None:
    with pytest.raises(MaaFWBindingFallbackError, match="映射不到"):
        ensure_binding_wheel("5.13.1.post6", tmp_path / "pool")
