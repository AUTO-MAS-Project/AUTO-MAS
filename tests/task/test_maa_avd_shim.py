"""MAA 截图外壳的放置：ModAVD 包自带外壳时不覆盖。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.task.MAA.tools import avd


@pytest.fixture
def own_shim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> bytes:
    src = tmp_path / "res" / "external_renderer_ipc.dll"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"auto-mas shim")
    monkeypatch.setattr(avd, "SHIM_SOURCE", src)
    return b"auto-mas shim"


def _root(tmp_path: Path, *, shim: bytes | None, listed: bool | None) -> Path:
    root = tmp_path / "root"
    root.mkdir()
    if shim is not None:
        avd.shim_dll(root).parent.mkdir(parents=True)
        avd.shim_dll(root).write_bytes(shim)
    if listed is not None:
        files = {"tools/modavd.exe": {"size": 1, "sha256": "0" * 64}}
        if listed:
            files[avd.PACKAGE_SHIM_PATH] = {"size": 12, "sha256": "1" * 64}
        (root / "modavd-manifest.json").write_text(
            json.dumps({"schema": 1, "version": "v0.40.1", "files": files}),
            encoding="utf-8",
        )
    return root


def test_package_shim_is_left_alone(tmp_path: Path, own_shim: bytes) -> None:
    root = _root(tmp_path, shim=b"package shim", listed=True)
    assert avd.ensure_mumu_shim(root) == avd.shim_dll(root)
    assert avd.shim_dll(root).read_bytes() == b"package shim"


def test_package_shim_missing_gets_ours(tmp_path: Path, own_shim: bytes) -> None:
    root = _root(tmp_path, shim=None, listed=True)
    avd.ensure_mumu_shim(root)
    assert avd.shim_dll(root).read_bytes() == own_shim


@pytest.mark.parametrize("listed", [False, None])
def test_older_package_gets_ours(
    tmp_path: Path, own_shim: bytes, listed: bool | None
) -> None:
    """0.40.1 以前的包不带外壳（清单里没有，或者没有清单）：照旧换成本体的那份。"""
    root = _root(tmp_path, shim=b"old copy", listed=listed)
    avd.ensure_mumu_shim(root)
    assert avd.shim_dll(root).read_bytes() == own_shim


@pytest.mark.parametrize("text", ["{", "[]", '{"files": []}', "﻿{}"])
def test_unreadable_manifest_counts_as_older(
    tmp_path: Path, own_shim: bytes, text: str
) -> None:
    root = _root(tmp_path, shim=b"old copy", listed=None)
    (root / "modavd-manifest.json").write_text(text, encoding="utf-8")
    avd.ensure_mumu_shim(root)
    assert avd.shim_dll(root).read_bytes() == own_shim


def test_bom_manifest_is_read(tmp_path: Path, own_shim: bytes) -> None:
    root = _root(tmp_path, shim=b"package shim", listed=True)
    path = root / "modavd-manifest.json"
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    avd.ensure_mumu_shim(root)
    assert avd.shim_dll(root).read_bytes() == b"package shim"
