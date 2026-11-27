"""Mirror 酱版本查询与下载授权分离的回归测试。"""

import hashlib
from importlib import import_module
from types import SimpleNamespace

import pytest
from packaging.version import Version

from app.services.common.update.transport import MirrorResourceError
from app.task.HSR.tools import update as hsr_update
from app.task.HSR.tools.update import check_engine_update
from app.task.HSR.tools.update.guards import GuardFailure
from app.task.MaaEnd.manager import MaaEndManager
from app.task.MaaEnd.tools import script_update

hsr_discovery = import_module("app.task.HSR.tools.update.discover")


@pytest.mark.asyncio
async def test_hsr_version_check_ignores_download_quota(monkeypatch, tmp_path):
    async def mirror(_resource, *, params, **_):
        if "cdk" in params:
            raise MirrorResourceError(7003, "额度用尽", {"version_name": "v2026.11.27"})
        return {"data": {"version_name": "v2026.11.27"}}

    monkeypatch.setattr(hsr_discovery, "request_mirror_resource", mirror)
    result = await check_engine_update(
        "M7A", tmp_path, source="MirrorChyan", cdk="fixture-cdk"
    )
    assert result.latest_version == "v2026.11.27"
    assert result.update_available and result.installable
    assert result.candidate is None and result.blocked_reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize("current", ["v2026.11.25", "v2026.11.27"])
async def test_hsr_download_only_authorizes_a_newer_version(
    monkeypatch, tmp_path, current
):
    version_file = tmp_path / "assets/config/version.txt"
    version_file.parent.mkdir(parents=True)
    version_file.write_text(current, encoding="utf-8")
    requests = []

    async def mirror(_resource, *, params, **_):
        requests.append(params)
        data = {"version_name": "v2026.11.27"}
        if params.get("cdk") == "fixture-cdk":
            data["url"] = "https://mirror.example/hsr.zip"
        return {"data": data}

    monkeypatch.setattr(hsr_discovery, "request_mirror_resource", mirror)
    result = await check_engine_update(
        "M7A", tmp_path, source="MirrorChyan", cdk="fixture-cdk", for_download=True
    )
    assert "cdk" not in requests[0]
    if current == "v2026.11.27":
        assert not result.update_available and not result.installable
        assert len(requests) == 1
    else:
        assert result.candidate is not None
        assert result.candidate.download_url == "https://mirror.example/hsr.zip"
        assert sum("cdk" in request for request in requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_by", ["process", "writable", None])
async def test_hsr_apply_authorizes_only_after_local_checks(
    monkeypatch, tmp_path, blocked_by
):
    root = tmp_path / "install"
    root.mkdir()
    events = []

    async def mirror(_resource, *, params, **_):
        data = {"version_name": "v2026.11.27"}
        if "cdk" in params:
            events.append("authorized")
            data["url"] = "https://mirror.example/hsr.zip"
        else:
            events.append("version")
        return {"data": data}

    async def download(candidate, _path, **_):
        events.append(candidate.download_url)
        return None

    monkeypatch.setattr(hsr_discovery, "request_mirror_resource", mirror)
    monkeypatch.setattr(hsr_update, "_download_with_space_check", download)
    monkeypatch.setattr(
        hsr_update,
        "check_no_process_running",
        lambda _: GuardFailure("脚本正在运行") if blocked_by == "process" else None,
    )
    monkeypatch.setattr(
        hsr_update,
        "check_writable",
        lambda _: GuardFailure("目录不可写") if blocked_by == "writable" else None,
    )
    outcome = await hsr_update.update_engine_if_needed(
        "M7A",
        root,
        source="MirrorChyan",
        cdk="fixture-cdk",
        download_dir=tmp_path / "downloads",
    )
    assert outcome.update_available and not outcome.updated
    if blocked_by:
        assert (
            outcome.message
            == {"process": "脚本正在运行", "writable": "目录不可写"}[blocked_by]
        )
        assert events == ["version"]
    else:
        assert events == ["version", "authorized", "https://mirror.example/hsr.zip"]


@pytest.mark.asyncio
async def test_maaend_only_authorizes_during_download(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config = SimpleNamespace(
        Info=SimpleNamespace(Path=tmp_path),
        Update=SimpleNamespace(
            TakeoverEnabled=True,
            Channel="stable",
            PackageMode="full",
            MirrorChyanCDK="fixture-cdk",
        ),
    )
    package = b"fixture release bytes"
    url = "https://mirror.example/maaend.zip"
    authorizations = []
    downloads = []

    async def release(_channel):
        return {
            "tag_name": "v3.2.0",
            "assets": [
                {
                    "name": "MaaEnd-win-x86_64-v3.2.0.zip",
                    "size": len(package),
                    "digest": f"sha256:{hashlib.sha256(package).hexdigest()}",
                }
            ],
        }

    async def mirror(_resource, *, params, **_):
        authorizations.append(params["cdk"])
        return {"data": {"update_type": "full", "version_name": "v3.2.0", "url": url}}

    async def download(address, destination, **_):
        downloads.append(address)
        destination.write_bytes(package)

    monkeypatch.setattr(
        script_update, "read_install", lambda _: (Version("3.1.0"), "x86_64")
    )
    monkeypatch.setattr(script_update, "request_release", release)
    monkeypatch.setattr(script_update, "request_mirror_resource", mirror)
    monkeypatch.setattr(script_update, "download_file", download)

    for _ in range(2):
        assert not await MaaEndManager.check_prefetch(config)
    assert not authorizations and not downloads

    result = await script_update.prepare_update(tmp_path, config)
    assert isinstance(result, script_update.PreparedUpdate)
    assert result.destination.read_bytes() == package
    assert authorizations == ["fixture-cdk"]
    assert downloads == [url]
