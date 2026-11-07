"""已下载候选必须经过基线和预检门，不能重签或提前登记。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.task.MaaFW.tools.core.project_update import updater


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed,blocked", [(False, False), (True, False), (False, True)]
)
async def test_prefetched_candidate_consumption_checks_baseline_and_gate(
    tmp_path, monkeypatch, changed, blocked
):
    candidate = updater.MaaFWProjectUpdateCandidate(
        source="github_release",
        version="2.0",
        download_url="https://example.invalid/package.zip",
        package_type="full",
    )
    discovery = updater.MaaFWProjectUpdateDiscovery(
        source="github_release", version="2.0", candidate=candidate
    )
    discover = AsyncMock(return_value=(None, None, "no newer version"))
    apply = AsyncMock(return_value={})
    gate = AsyncMock(return_value="environment unavailable" if blocked else None)
    monkeypatch.setattr(updater, "_discover_project_update_detailed", discover)
    monkeypatch.setattr(updater, "apply_maafw_project_update", apply)
    result = await updater.update_maafw_project_if_needed(
        tmp_path,
        SimpleNamespace(version="1.1" if changed else "1.0"),
        source_config={"project_shell_hint": "MXU"},
        precheck_gate=gate,
        prefetch_full_package=True,
        prefetched=("1.0", discovery),
    )
    if changed:
        discover.assert_awaited_once()
        apply.assert_not_awaited()
    else:
        discover.assert_not_awaited()
        gate.assert_awaited_once_with("2.0")
        if blocked:
            assert not result.updated
            apply.assert_not_awaited()
        else:
            assert result.updated
            apply.assert_awaited_once()
            assert apply.await_args.kwargs["range_delta"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [False, True])
async def test_prefetched_manager_rechecks_source_after_same_version_reimport(
    tmp_path, monkeypatch, isolated_app_paths, changed
):
    """同版重新导入改变来源时，旧下载不能登记到新谱系；未变化的来源继续复用。"""
    import asyncio
    import hashlib
    import io
    import json
    import threading
    import uuid
    import zipfile

    import httpx

    from app.models.config import GlobalConfig, MaaFWConfig
    from app.models.task import TaskItem, TaskScriptItem
    from app.task.MaaFW import embedded_manager
    from app.task.MaaFW.tools.core.project_update import transport
    from app.task.MaaFW.tools.embedded import embedded_project
    from app.task.MaaFW.tools.embedded.update_credentials import (
        resolve_update_credentials,
    )
    from tests.config_support import activate_config

    install = tmp_path / "mas"
    install.mkdir()
    monkeypatch.chdir(install)
    source = tmp_path / "source"
    (source / "resource").mkdir(parents=True)
    (source / "resource/data.json").write_text('{"source":"shared"}')

    def interface(repo, version="1.0"):
        return {
            "interface_version": 2,
            "name": "Audit",
            "version": version,
            "github": f"https://github.com/audit/{repo}",
            "resource": [{"name": "Default", "path": ["resource"]}],
            "task": [],
        }

    previous = interface("aaaa")
    replacement = interface("bbbb" if changed else "aaaa")
    assert len(json.dumps(previous)) == len(json.dumps(replacement))
    (source / "interface.json").write_text(json.dumps(previous))
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("interface.json", json.dumps(interface("aaaa", "2.0")))
        archive.writestr("resource/data.json", '{"source":"aaaa-v2"}')
    package_bytes = package.getvalue()
    requests = []

    def respond(request):
        url = str(request.url)
        requests.append(url)
        if url == "https://example.com/old.zip":
            return httpx.Response(200, content=package_bytes)
        if "/releases/tags/1.0" in url or "/releases/tags/v1.0" in url:
            # 两个项目都已撤下旧版本的发行包，实际导入核对返回同样的报告。
            return httpx.Response(404, json={"message": "Not Found"})
        if "/repos/audit/aaaa/" in url:
            return httpx.Response(
                200,
                json={
                    "tag_name": "2.0",
                    "assets": [
                        {
                            "name": "Audit-win-x86_64-2.0.zip",
                            "browser_download_url": "https://example.com/old.zip",
                            "size": len(package_bytes),
                            "digest": "sha256:"
                            + hashlib.sha256(package_bytes).hexdigest(),
                            "id": 1122,
                        }
                    ],
                },
            )
        if "/repos/audit/bbbb/" in url:
            return httpx.Response(200, json={"tag_name": "1.0", "assets": []})
        raise AssertionError(url)

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(**kwargs, transport=httpx.MockTransport(respond)),
    )
    monkeypatch.setattr(updater, "DEFAULT_CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(transport, "DEFAULT_CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(updater, "DEFAULT_OPERATION_ROOT", tmp_path / "operations")
    uid = uuid.uuid4()
    script_id = str(uid)
    first = await asyncio.to_thread(
        embedded_project.import_embedded_project, script_id, source
    )

    def imported_fields(imported):
        return {
            "Report": json.dumps(imported["report"], ensure_ascii=False),
            "SourceVersion": imported["sourceVersion"],
            "ImportedAt": imported["importedAt"],
        }

    config = MaaFWConfig.build(
        payload={
            "Info": {"Path": str(source)},
            "Embedded": imported_fields(first),
            "Update": {"AutoUpdateMode": "BeforeRun", "Source": "GitHub"},
        }
    )
    await activate_config(config)
    assert config.Info.Path == source
    monkeypatch.setattr(isolated_app_paths, "ScriptConfig", {uid: config})
    monkeypatch.setattr(
        isolated_app_paths,
        "setting",
        GlobalConfig.model_validate({"Update": {"GitHubMirror": "Off"}}),
    )
    view = embedded_project.embedded_project_dir(script_id)
    info = TaskItem(mode="AutoProxy", name="audit")
    await activate_config(info)
    item_uid = info.scripts.add(
        TaskScriptItem, payload={"info": {"script_id": script_id, "name": "audit"}}
    )
    await info.scripts.commit()
    manager = embedded_manager.MaaFWEmbeddedManager(info.scripts[item_uid])
    # 基础候选能力独立验证；新调度按确认仍不创建 ScriptUpdateSession。
    await manager.prefetch_script_update()
    (source / "interface.json").write_text(json.dumps(replacement))
    second = await asyncio.to_thread(
        embedded_project.import_embedded_project, script_id, source
    )
    await config.update(
        MaaFWConfig.model_validate({"Embedded": imported_fields(second)})
    )
    assert first["report"] == second["report"]
    assert json.loads((view / "interface.json").read_text()) == replacement
    marker_before = embedded_project.read_view_marker(view)
    before_consume = list(requests)

    # 只隔离真实运行池/agent 环境准备；发现、缓存、预检门、登记和视图切换照常执行。
    manager.script_config = config
    monkeypatch.setattr(
        manager,
        "_resolve_runtime_pool_route",
        lambda: SimpleNamespace(root=tmp_path / "runtime"),
    )
    monkeypatch.setattr(
        embedded_manager.MaaFWEmbeddedManager,
        "_prepare_project_environment_sync",
        lambda *_args, **_kwargs: True,
    )
    outcome = await manager._invoke_project_update(
        view,
        resolve_update_credentials(config),
        update_cancel=threading.Event(),
    )
    installed = json.loads((view / "interface.json").read_text())
    assert installed["github"] == replacement["github"]
    assert installed["version"] == ("1.0" if changed else "2.0")
    assert json.loads((view / "resource/data.json").read_text()) == {
        "source": "shared" if changed else "aaaa-v2"
    }
    assert outcome.updated is not changed
    assert (
        embedded_project.read_view_marker(view)["lineage"] == marker_before["lineage"]
    )
    if changed:
        assert any(
            "/repos/audit/bbbb/" in url for url in requests[len(before_consume) :]
        )
    else:
        assert requests == before_consume


@pytest.mark.asyncio
async def test_shared_artifact_cache_serializes_coroutines(tmp_path):
    """Prefetch and regular updating the same asset must not write concurrently."""
    import asyncio

    from app.task.MaaFW.tools.core.project_update import transport

    stable_id = transport.artifact_id_for(
        "github", "2", "https://example.com/asset.zip", explicit="asset"
    )
    active = 0
    maximum = 0
    first_started, release_first = asyncio.Event(), asyncio.Event()

    async def writer(name):
        nonlocal active, maximum
        async with transport._artifact_download_access(tmp_path, stable_id):
            active += 1
            maximum = max(maximum, active)
            try:
                if name == "first":
                    first_started.set()
                    await release_first.wait()
            finally:
                active -= 1

    first = asyncio.create_task(writer("first"))
    await asyncio.wait_for(first_started.wait(), 1)
    second = asyncio.create_task(writer("second"))
    await asyncio.sleep(0)
    assert active == 1
    assert not second.done()
    release_first.set()
    await asyncio.wait_for(asyncio.gather(first, second), 1)
    assert maximum == 1


@pytest.mark.asyncio
async def test_prefetch_discovery_forwards_precheck_gate_before_url(monkeypatch):
    """Public discovery must pass the failed-version gate to the URL resolver."""
    from app.task.MaaFW.tools.core.project_update import updater

    discovered = updater.MaaFWProjectUpdateDiscovery(
        source="mirrorchyan",
        version="2.0",
        unavailable_reason="previous runtime precheck failed",
    )
    detailed = AsyncMock(return_value=(discovered, None, None))
    monkeypatch.setattr(updater, "_discover_project_update_detailed", detailed)
    gate = AsyncMock(return_value="previous runtime precheck failed")
    result = await updater.discover_maafw_project_update(
        SimpleNamespace(),
        source_config={"package_source": "mirrorchyan"},
        precheck_gate=gate,
    )
    assert result is discovered
    assert detailed.await_args.kwargs["precheck_gate"] is gate


@pytest.mark.asyncio
@pytest.mark.parametrize("hash_failure", [False, True])
async def test_cancelled_cache_hash_keeps_artifact_locked_until_worker_stops(
    tmp_path, monkeypatch, hash_failure
):
    import asyncio
    import json
    import threading

    from app.task.MaaFW.tools.core.project_update import transport

    stable_id = transport.artifact_id_for(
        "github", "2", "https://example.com/asset.zip", explicit="asset"
    )
    directory = tmp_path / stable_id
    directory.mkdir()
    archive = directory / "complete.zip"
    archive.write_bytes(b"cached package")
    (directory / "artifact.json").write_text(
        json.dumps(
            {
                "complete": True,
                "completePath": str(archive),
                "sha256": "a" * 64,
            }
        )
    )
    started, release = threading.Event(), threading.Event()

    def hash_with_open_file(path):
        with path.open("rb") as handle:
            started.set()
            assert release.wait(5)
            assert handle.read() == b"cached package"
        if hash_failure:
            raise OSError("disk read failed during cancellation")
        return "a" * 64

    monkeypatch.setattr(transport, "_calculate_sha256", hash_with_open_file)
    task = asyncio.create_task(
        transport.download_resumable(
            source="github",
            version="2",
            download_url="https://example.com/asset.zip",
            artifact_id="asset",
            cache_root=tmp_path,
        )
    )
    successor = None
    entered = asyncio.Event()

    async def next_owner():
        async with transport._artifact_download_access(tmp_path, stable_id):
            entered.set()

    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        successor = asyncio.create_task(next_owner())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not task.done()
        assert not entered.is_set()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        if successor is not None:
            await asyncio.wait_for(successor, 2)
    assert entered.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("close_failure", [False, True])
async def test_cancelled_download_waits_for_file_write_before_unlocking(
    tmp_path, monkeypatch, close_failure
):
    """重复停止不能让后继下载在前一写线程结束前取得同一个缓存。"""
    import asyncio
    import io
    import threading
    from pathlib import Path

    import aiofiles.threadpool
    import httpx

    from app.task.MaaFW.tools.core.project_update import transport

    started, release, finished = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    original_open = io.open

    class SlowWriter(io.BufferedWriter):
        def write(self, data):
            started.set()
            try:
                assert release.wait(5)
                return super().write(data)
            finally:
                finished.set()

        def close(self):
            if self.closed:
                return
            super().close()
            if close_failure:
                raise OSError("disk full while closing buffered download")

    def open_file(path, mode="r", *args, **kwargs):
        if Path(path).name == "payload.part" and mode in {"wb", "ab"}:
            return SlowWriter(original_open(path, mode, buffering=0))
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(io, "open", open_file)
    monkeypatch.setattr(aiofiles.threadpool, "sync_open", open_file)
    monkeypatch.setattr(transport, "RETRY_COUNT", 2)
    monkeypatch.setattr(transport, "RETRY_DELAYS", (0,))
    client = httpx.AsyncClient
    request_count = 0

    def response(_request):
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, content=b"package data")

    monkeypatch.setattr(
        transport.httpx,
        "AsyncClient",
        lambda **kwargs: client(**kwargs, transport=httpx.MockTransport(response)),
    )
    task = asyncio.create_task(
        transport.download_resumable(
            source="github",
            version="2",
            download_url="https://example.com/asset.zip",
            artifact_id="asset",
            cache_root=tmp_path,
        )
    )
    successor = None
    entered = asyncio.Event()
    stable_id = transport.artifact_id_for(
        "github", "2", "https://example.com/asset.zip", explicit="asset"
    )

    async def next_owner():
        async with transport._artifact_download_access(tmp_path, stable_id):
            entered.set()

    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        successor = asyncio.create_task(next_owner())
        done, _ = await asyncio.wait({task, successor}, timeout=0.05)
        assert not done
        assert not entered.is_set()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        if successor is not None:
            await asyncio.wait_for(successor, 3)
        assert await asyncio.to_thread(finished.wait, 3)
    assert task.cancelled()
    assert entered.is_set()
    assert request_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_kind", ["thread", "coroutine"])
@pytest.mark.parametrize("cancel_method", ["task", "token"])
async def test_waiting_for_busy_artifact_cache_observes_stop(
    tmp_path, owner_kind, cancel_method
):
    """另一线程或进程占着缓存时，下载等锁仍须能够接收停止。"""
    import asyncio
    import hashlib
    import json
    import threading

    from app.task.MaaFW.tools.core.project_update import transport

    locked, release, expired = threading.Event(), threading.Event(), threading.Event()
    stable_id = transport.artifact_id_for(
        "github", "2", "https://example.com/asset.zip", explicit="asset"
    )
    directory = tmp_path / stable_id
    directory.mkdir()
    package = directory / "complete.zip"
    package.write_bytes(b"cached package")
    (directory / "artifact.json").write_text(
        json.dumps(
            {
                "complete": True,
                "completePath": str(package),
                "sha256": hashlib.sha256(b"cached package").hexdigest(),
            }
        )
    )

    def other_owner():
        with transport.artifact_lock(tmp_path, stable_id):
            locked.set()
            if not release.wait(3):
                expired.set()

    async def coroutine_owner():
        async with transport._artifact_download_access(tmp_path, stable_id):
            locked.set()
            if not await asyncio.to_thread(release.wait, 3):
                expired.set()

    owner = asyncio.create_task(
        asyncio.to_thread(other_owner) if owner_kind == "thread" else coroutine_owner()
    )
    cancel_event = threading.Event()
    download = None
    try:
        assert await asyncio.to_thread(locked.wait, 3)
        download = asyncio.create_task(
            transport.download_resumable(
                source="github",
                version="2",
                download_url="https://example.com/asset.zip",
                artifact_id="asset",
                cache_root=tmp_path,
                cancel_event=cancel_event,
            )
        )
        await asyncio.sleep(0)
        if cancel_method == "task":
            download.cancel()
        else:
            cancel_event.set()
        with pytest.raises(
            asyncio.CancelledError
            if cancel_method == "task"
            else transport.UpdateDownloadCancelled
        ):
            await asyncio.wait_for(download, 1)
        assert not expired.is_set(), "同步等文件锁阻塞了事件循环，停止无法处理"
    finally:
        release.set()
        await owner
        if download is not None:
            download.cancel()
            await asyncio.gather(download, return_exceptions=True)
