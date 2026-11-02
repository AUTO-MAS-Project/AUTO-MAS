import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.task.MAA.tools import resource_update as resource
from app.task.MAA.tools import software_update as software


@pytest.mark.asyncio
async def test_resource_new_version_allowed_same_day(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    old = now - timedelta(hours=2)
    target = now - timedelta(hours=1)
    key = hashlib.sha256(b"key").hexdigest()[:16]
    state = {
        f"last_download_attempt_at/{key}": now.isoformat(),
        f"last_download_attempt_version/{key}": old.isoformat(),
    }
    monkeypatch.setattr(resource, "_STATE_FILE", tmp_path / "state.json")
    request = AsyncMock(
        return_value={
            "data": {
                "url": "https://example.invalid",
                "update_type": "full",
                "version_name": resource._format_clock(target),
            }
        }
    )
    monkeypatch.setattr(resource, "request_mirror_resource", request)
    refresh = AsyncMock()
    monkeypatch.setattr(resource, "_refresh_stage", refresh)
    monkeypatch.setattr(resource, "_load_manifest", lambda: None)
    await resource._refresh_resource_stage(
        clocks={tmp_path: old},
        stage=None,
        target=target,
        state=state,
        progress=None,
        cdk="key",
    )
    assert refresh.await_count == 1
    assert request.await_count == 1
    await resource._refresh_resource_stage(
        clocks={tmp_path: old},
        stage=None,
        target=target,
        state=state,
        progress=None,
        cdk="key",
    )
    assert request.await_count == 1


@pytest.mark.asyncio
async def test_software_new_version_and_same_version_budget(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    monkeypatch.setattr(software, "_STATE_FILE", state)
    monkeypatch.setattr(software, "read_installed_release", lambda _: ("v6.0.0", "x64"))
    monkeypatch.setattr(
        software, "software_cache_dir", lambda *a, **k: tmp_path / "cache"
    )
    monkeypatch.setattr(software, "load_cache_manifest", lambda _: None)
    replies = ["v6.1.0", "v6.1.0", "v6.2.0"]
    requests = []

    async def request(_resource, *, params, **kwargs):
        requests.append(params)
        version = replies[0]
        if "cdk" in params:
            return {
                "data": {
                    "version_name": version,
                    "url": "https://example.invalid",
                    "update_type": "full",
                }
            }
        return {"data": {"version_name": version}}

    monkeypatch.setattr(software, "request_mirror_resource", request)
    cache = AsyncMock()
    monkeypatch.setattr(software, "_ensure_cache", cache)
    await software._precheck_inner(tmp_path, "stable", "x64", "key")
    replies.pop(0)
    await software._precheck_inner(tmp_path, "stable", "x64", "key")
    replies.pop(0)
    await software._precheck_inner(tmp_path, "stable", "x64", "key")
    assert cache.await_count == 2
    assert sum("cdk" in params for params in requests) == 2


@pytest.fixture
def software_case(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    path = tmp_path / "state.json"
    monkeypatch.setattr(software, "_STATE_FILE", path)
    monkeypatch.setattr(software, "read_installed_release", lambda _: ("v6.0.0", "x64"))
    monkeypatch.setattr(
        software, "software_cache_dir", lambda *args: tmp_path / "cache"
    )
    monkeypatch.setattr(software, "load_cache_manifest", lambda _: None)
    versions = SimpleNamespace(target="v6.1.0", actual="v6.1.0")
    requests = []

    async def request(_resource, *, params, **kwargs):
        requests.append(params)
        if "cdk" in params:
            return {
                "data": {
                    "version_name": versions.actual,
                    "url": "https://example.invalid",
                    "update_type": "full",
                }
            }
        return {"data": {"version_name": versions.target}}

    monkeypatch.setattr(software, "request_mirror_resource", request)
    download = AsyncMock()
    monkeypatch.setattr(software, "_ensure_cache", download)

    def save(state):
        path.write_text(json.dumps(state), encoding="utf-8")

    def load():
        return json.loads(path.read_text(encoding="utf-8"))

    return SimpleNamespace(
        root=tmp_path,
        versions=versions,
        requests=requests,
        download=download,
        save=save,
        load=load,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("actual", ["v6.0.5", "invalid"])
async def test_software_stale_response_is_recorded_without_download(
    software_case, actual
):
    c = software_case
    c.versions.actual = actual
    with pytest.raises(software._UpdateError):
        await software._precheck_inner(c.root, "stable", "x64", "key")
    assert c.load()["last_download_attempt_version/win/x64/stable"] == "v6.1.0"
    await software._precheck_inner(c.root, "stable", "x64", "key")
    assert sum("cdk" in params for params in c.requests) == 1
    c.download.assert_not_awaited()


@pytest.mark.asyncio
async def test_software_newer_response_blocks_duplicate(software_case):
    c = software_case
    c.versions.actual = "v6.2.0"
    await software._precheck_inner(c.root, "stable", "x64", "key")
    assert c.load()["last_download_attempt_version/win/x64/stable"] == "v6.2.0"
    c.versions.target = "v6.2.0"
    await software._precheck_inner(c.root, "stable", "x64", "key")
    assert c.download.await_count == 1
    assert sum("cdk" in params for params in c.requests) == 1


@pytest.mark.asyncio
async def test_software_legacy_state_and_cancel_keep_budget(software_case):
    import asyncio

    c = software_case
    c.save(
        {
            "last_download_attempt_at/win/x64/stable": datetime.now(
                timezone.utc
            ).isoformat()
        }
    )
    c.download.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await software._precheck_inner(c.root, "stable", "x64", "key")
    assert c.load()["last_download_attempt_version/win/x64/stable"] == "v6.1.0"
    await software._precheck_inner(c.root, "stable", "x64", "key")
    assert sum("cdk" in params for params in c.requests) == 1


@pytest.mark.asyncio
async def test_software_shared_newer_cache_skips_authorized_request(
    software_case, monkeypatch
):
    c = software_case
    monkeypatch.setattr(
        software, "load_cache_manifest", lambda _: {"version": "v6.2.0"}
    )
    monkeypatch.setattr(software, "cache_zip_matches", lambda *args: True)
    await software._precheck_inner(c.root, "stable", "x64", "key")
    assert len(c.requests) == 1 and "cdk" not in c.requests[0]
    c.download.assert_not_awaited()


@pytest.mark.asyncio
async def test_software_download_backoff_skips_authorized_request(software_case):
    c = software_case
    c.save(
        {
            "download_fail_until/win/x64/stable": (
                datetime.now(timezone.utc) + timedelta(hours=1)
            ).isoformat()
        }
    )
    await software._precheck_inner(c.root, "stable", "x64", "key")
    assert len(c.requests) == 1 and "cdk" not in c.requests[0]
    c.download.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("response_offset", [-1, None, 1])
async def test_resource_response_version_is_accounted(
    tmp_path, monkeypatch, response_offset
):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    old = now - timedelta(hours=2)
    target = now - timedelta(hours=1)
    actual = (
        None if response_offset is None else target + timedelta(minutes=response_offset)
    )
    response = {"url": "https://example.invalid", "update_type": "full"}
    if actual is not None:
        response["version_name"] = resource._format_clock(actual)
    request = AsyncMock(return_value={"data": response})
    refresh = AsyncMock()
    monkeypatch.setattr(resource, "request_mirror_resource", request)
    monkeypatch.setattr(resource, "_refresh_stage", refresh)
    monkeypatch.setattr(resource, "_load_manifest", lambda: None)
    monkeypatch.setattr(resource, "_STATE_FILE", tmp_path / "state.json")
    state = {}
    await resource._refresh_resource_stage(
        clocks={tmp_path: old},
        stage=None,
        target=target,
        state=state,
        progress=None,
        cdk="key",
    )
    key = hashlib.sha256(b"key").hexdigest()[:16]
    assert datetime.fromisoformat(state[f"last_download_attempt_version/{key}"]) == max(
        target, actual or target
    )
    if response_offset == 1:
        assert refresh.await_args.kwargs["target"] == actual
    else:
        refresh.assert_not_awaited()
        assert f"download_fail_until/{key}" in state


@pytest.mark.asyncio
async def test_resource_legacy_state_cancel_keeps_budget(tmp_path, monkeypatch):
    import asyncio

    now = datetime.now(timezone.utc).replace(microsecond=0)
    old = now - timedelta(hours=2)
    target = now - timedelta(hours=1)
    key = hashlib.sha256(b"key").hexdigest()[:16]
    state = {f"last_download_attempt_at/{key}": now.isoformat()}
    request = AsyncMock(
        return_value={
            "data": {
                "url": "https://example.invalid",
                "update_type": "full",
                "version_name": resource._format_clock(target),
            }
        }
    )
    monkeypatch.setattr(resource, "request_mirror_resource", request)
    monkeypatch.setattr(
        resource, "_refresh_stage", AsyncMock(side_effect=asyncio.CancelledError)
    )
    monkeypatch.setattr(resource, "_STATE_FILE", tmp_path / "state.json")
    with pytest.raises(asyncio.CancelledError):
        await resource._refresh_resource_stage(
            clocks={tmp_path: old},
            stage=None,
            target=target,
            state=state,
            progress=None,
            cdk="key",
        )
    await resource._refresh_resource_stage(
        clocks={tmp_path: old},
        stage=None,
        target=target,
        state=state,
        progress=None,
        cdk="key",
    )
    assert request.await_count == 1
