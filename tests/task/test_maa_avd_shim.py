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


@pytest.mark.parametrize(
    "shim,listed,manifest,expected",
    [
        (b"package shim", True, None, b"package shim"),
        (None, True, None, b"auto-mas shim"),
        (b"old copy", False, None, b"auto-mas shim"),
        (b"old copy", None, None, b"auto-mas shim"),
        (b"old copy", None, "{", b"auto-mas shim"),
        (b"old copy", None, "[]", b"auto-mas shim"),
        (b"old copy", None, '{"files": []}', b"auto-mas shim"),
        (b"old copy", None, "\ufeff{}", b"auto-mas shim"),
        (b"package shim", True, "BOM", b"package shim"),
    ],
)
def test_shim_install_respects_package_ownership_and_manifest_readability(
    tmp_path: Path, own_shim: bytes, shim, listed, manifest, expected
):
    """包内自带外壳保持原样，缺失外壳或旧包使用 MAS 的副本。"""
    root = _root(tmp_path, shim=shim, listed=listed)
    path = root / "modavd-manifest.json"
    if manifest == "BOM":
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    elif manifest is not None:
        path.write_text(manifest, encoding="utf-8")
    assert avd.ensure_mumu_shim(root) == avd.shim_dll(root)
    assert avd.shim_dll(root).read_bytes() == expected
