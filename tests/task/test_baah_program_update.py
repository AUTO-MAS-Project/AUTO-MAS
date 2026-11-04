"""BAAH 下载/安装分离及配置保护；网络与真实程序进程在边界隔离。"""

import hashlib
import json
import shutil
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from packaging.version import Version

from app.services import script_install
from app.task.BAAH.tools import program_update as update


def pe(extra=b""):
    data = bytearray(134)
    data[:2] = b"MZ"
    data[60:64] = (128).to_bytes(4, "little")
    data[128:132] = b"PE\0\0"
    data[132:134] = (0x8664).to_bytes(2, "little")
    return bytes(data) + extra


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "BAAH"
    (root / "DATA/CONFIGS").mkdir(parents=True)
    (root / "DATA/CONFIGS/software_config.json").write_text(
        '{"NOWVERSION":"2.5.6", "custom":true}'
    )
    (root / "BAAH_CONFIGS").mkdir()
    (root / "BAAH_CONFIGS/account.json").write_text('{"opaque": true}')
    (root / "BAAH.exe").write_bytes(pe())
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("BAAH.exe", pe(b"new"))
        package.writestr("DATA/icons/icon.png", b"resource")
    release = {
        "tag_name": "BAAH2.5.7",
        "assets": [
            {
                "name": "BAAH2.5.7_update.zip",
                "size": archive.stat().st_size,
                "digest": "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest(),
            }
        ],
    }
    config = SimpleNamespace(
        Update=SimpleNamespace(Channel="stable", MirrorChyanCDK="")
    )
    monkeypatch.setattr(
        update,
        "Config",
        SimpleNamespace(
            data_path=tmp_path / "cache",
            proxy=None,
            setting=SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK="")),
        ),
    )
    monkeypatch.setattr(update, "assert_idle", lambda root: None)
    monkeypatch.setattr(update, "request_release", AsyncMock(return_value=release))

    async def download(url, destination, **kwargs):
        shutil.copyfile(archive, destination)

    monkeypatch.setattr(
        update, "download_script_package", AsyncMock(side_effect=download)
    )
    return root, config, archive, release


@pytest.mark.asyncio
async def test_prepare_can_run_while_installation_is_reserved_then_apply_preserves_configs(
    installation,
):
    root, config, _, _ = installation
    with script_install.installation_access(root):
        prepared = await update.prepare_update(root, config)
    assert (root / "BAAH.exe").read_bytes() == pe()
    with script_install.installation_access(root):
        await update.apply_update(root, prepared)
    assert (root / "BAAH.exe").read_bytes() == pe(b"new")
    assert (
        json.loads((root / "DATA/CONFIGS/software_config.json").read_text())["custom"]
        is True
    )
    assert (root / "BAAH_CONFIGS/account.json").read_text() == '{"opaque": true}'
    assert update.read_version(root) == Version("2.5.7")
    await update.confirm_current_install(root)
    assert await update.prepare_update(root, config) is None


@pytest.mark.asyncio
async def test_archive_tampering_is_rejected_again_at_apply(installation):
    root, config, _, _ = installation
    prepared = await update.prepare_update(root, config)
    prepared.archive.write_bytes(b"changed after download")
    with pytest.raises(ValueError):
        await update.apply_update(root, prepared)
    assert (root / "BAAH.exe").read_bytes() == pe()


@pytest.mark.asyncio
async def test_changed_executable_invalidates_prefetch(installation):
    root, config, _, _ = installation
    prepared = await update.prepare_update(root, config)
    (root / "BAAH.exe").write_bytes(pe(b"native newer"))
    with pytest.raises(ValueError):
        await update.apply_update(root, prepared)
    assert (root / "BAAH.exe").read_bytes() == pe(b"native newer")


@pytest.mark.asyncio
async def test_package_cannot_replace_user_config(installation):
    root, config, archive, release = installation
    with zipfile.ZipFile(archive, "a") as package:
        package.writestr("DATA/CONFIGS/software_config.json", "{}")
    release["assets"][0]["size"] = archive.stat().st_size
    release["assets"][0]["digest"] = (
        "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
    )
    with pytest.raises(ValueError):
        await update.prepare_update(root, config)
    assert (
        json.loads((root / "DATA/CONFIGS/software_config.json").read_text())["custom"]
        is True
    )


@pytest.mark.asyncio
async def test_download_cancellation_cannot_modify_installation(installation):
    import asyncio

    root, config, _, _ = installation
    update.download_script_package.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await update.prepare_update(root, config)
    assert (root / "BAAH.exe").read_bytes() == pe()
