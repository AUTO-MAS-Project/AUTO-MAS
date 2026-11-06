"""重新导入与实际脚本启动互斥，取消等待导入和配置写回完成。"""

import asyncio
import hashlib
import io
import json
import threading
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.config import ConfigCollection
from app.core.task_manager.manager import TaskInfo
from app.models.config import (
    GlobalConfig,
    M9AConfig,
    M9AUserConfig,
    MaaFWConfig,
    MaaFWUserConfig,
)
from app.models.task import ScriptItem
from app.task.MaaFW import embedded_manager
from app.task.MaaFW.api_service import embedded as api
from app.task.MaaFW.registration import build_config_handler
from app.task.MaaFW.tools.core.project_update import transport, updater
from app.task.MaaFW.tools.embedded import embedded_project, project_path
from app.task.MaaFW.tools.embedded.update_credentials import (
    resolve_update_credentials,
)
from tests.config_support import activate_config


@pytest_asyncio.fixture
async def project(tmp_path, monkeypatch, isolated_app_paths):
    install = tmp_path / "mas"
    install.mkdir()
    monkeypatch.chdir(install)

    def interface(repo, version="1.0"):
        return {
            "interface_version": 2,
            "name": "Audit",
            "version": version,
            "github": f"https://github.com/audit/{repo}",
            "resource": [{"name": "Default", "path": ["resource"]}],
            "task": [],
        }

    sources = []
    for repo in ("aaaa", "bbbb"):
        source = tmp_path / repo
        (source / "resource").mkdir(parents=True)
        (source / "interface.json").write_text(json.dumps(interface(repo)))
        (source / "resource/data.json").write_text(json.dumps({"source": repo}))
        sources.append(source)

    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("interface.json", json.dumps(interface("aaaa", "2.0")))
        archive.writestr("resource/data.json", '{"source":"aaaa-v2"}')
    package_bytes = package.getvalue()
    downloading, allow_download = asyncio.Event(), asyncio.Event()
    allow_download.set()
    import_read, allow_import = threading.Event(), threading.Event()
    allow_import.set()

    async def respond(request):
        url = str(request.url)
        if url == "https://example.com/old.zip":
            downloading.set()
            await allow_download.wait()
            return httpx.Response(200, content=package_bytes)
        if "/releases/tags/1.0" in url or "/releases/tags/v1.0" in url:
            if "/audit/bbbb/" in url:
                # 导入核对在真实文件 worker 中请求旧版官方包。
                import_read.set()
                if not allow_import.wait(10):
                    raise TimeoutError("import read was not released")
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
        embedded_project.import_embedded_project, script_id, sources[0]
    )
    configs = ConfigCollection.build([MaaFWConfig, M9AConfig])
    await activate_config(configs)
    configs.add(
        MaaFWConfig,
        uid=uid,
        payload={
            "Info": {"Path": str(sources[0])},
            "Embedded": {
                "Report": json.dumps(first["report"], ensure_ascii=False),
                "SourceVersion": first["sourceVersion"],
                "ImportedAt": first["importedAt"],
            },
            "Update": {"AutoUpdateMode": "BeforeRun", "Source": "GitHub"},
        },
    )
    await configs.commit()
    config = configs[uid]
    user_uid = config.UserData.add(
        MaaFWUserConfig,
        payload={"Info": {"Name": "audit"}},
    )
    await config.UserData.commit()
    setting = GlobalConfig.build(payload={"Update": {"GitHubMirror": "Off"}})
    await activate_config(setting)
    monkeypatch.setattr(isolated_app_paths, "ScriptConfig", configs)
    monkeypatch.setattr(isolated_app_paths, "setting", setting)
    monkeypatch.setattr(isolated_app_paths, "_script_config_handlers", {})
    isolated_app_paths.bind_script_config_handler(MaaFWConfig, build_config_handler())
    assert config.Info.Path == sources[0]
    assert api._source_path_error(config, str(sources[1])) is None

    # 本回归不安装真实的 MaaFramework/agent 依赖或触发运行池后台回收。
    monkeypatch.setattr(
        embedded_manager.MaaFWEmbeddedManager,
        "_resolve_runtime_pool_route",
        staticmethod(lambda: SimpleNamespace(root=tmp_path / "runtime")),
    )
    monkeypatch.setattr(
        embedded_manager.MaaFWEmbeddedManager,
        "_prepare_project_environment_sync",
        lambda *_args, **_kwargs: True,
    )
    from app.task.MaaFW.tools.embedded import pool_reconcile

    monkeypatch.setattr(
        pool_reconcile, "reconcile_in_background", lambda *_a, **_k: None
    )
    monkeypatch.setattr(api.Notify, "push_system_notice", AsyncMock())

    def make_manager():
        item = ScriptItem(script_id, "audit", "等待")
        info = TaskInfo("AutoProxy", "audit", "queue", None, None)
        monkeypatch.setattr(info, "schedule_on_change", lambda: None)
        info.script_list = [item]
        return embedded_manager.MaaFWEmbeddedManager(item)

    worker_done = threading.Event()
    import_project = api.import_embedded_project

    def observed_import(*args, **kwargs):
        try:
            return import_project(*args, **kwargs)
        finally:
            worker_done.set()

    monkeypatch.setattr(api, "import_embedded_project", observed_import)
    return SimpleNamespace(
        config=config,
        current_config=lambda: configs[uid],
        user_uid=user_uid,
        script_id=script_id,
        source=sources[1],
        previous_source=sources[0],
        view=embedded_project.embedded_project_dir(script_id),
        make_manager=make_manager,
        downloading=downloading,
        allow_download=allow_download,
        import_read=import_read,
        allow_import=allow_import,
        worker_done=worker_done,
    )


@pytest.mark.asyncio
async def test_reimport_rechecks_busy_after_path_validation(project, monkeypatch):
    """API 通过初检后脚本开始真实下载，API 必须忙碌返回且不能先换视图。"""
    source_check, allow_source_check = threading.Event(), threading.Event()
    real_is_dir = Path.is_dir

    def delayed_is_dir(path):
        if path == project.source and not source_check.is_set():
            source_check.set()
            if not allow_source_check.wait(10):
                raise TimeoutError("source check was not released")
        return real_is_dir(path)

    monkeypatch.setattr(Path, "is_dir", delayed_is_dir)
    importing = asyncio.create_task(
        api.reimport_embedded(project.script_id, str(project.source))
    )
    manager = project.make_manager()
    project.allow_download.clear()
    updating = None

    async def update():
        try:
            assert await manager.check() == "Pass"
            return await manager._invoke_project_update(
                project.view,
                resolve_update_credentials(project.config),
                update_cancel=threading.Event(),
            )
        finally:
            await manager._commit_user_data()

    try:
        assert await asyncio.to_thread(source_check.wait, 5)
        updating = asyncio.create_task(update())
        await asyncio.wait_for(project.downloading.wait(), 5)
        assert project.config.is_locked
        assert project_path.is_project_updating(project.view)
        allow_source_check.set()
        reply = await asyncio.wait_for(importing, 5)
        assert reply.code == 400
        assert json.loads((project.view / "interface.json").read_text())["github"] == (
            "https://github.com/audit/aaaa"
        )
        assert project.config.Info.Path == project.previous_source
        project.allow_download.set()
        assert (await asyncio.wait_for(updating, 5)).updated
    finally:
        allow_source_check.set()
        project.allow_download.set()
        await asyncio.gather(
            *(task for task in (importing, updating) if task is not None),
            return_exceptions=True,
        )


@pytest.mark.asyncio
async def test_reimport_cannot_enter_between_run_preparation_and_config_lock(
    project, monkeypatch
):
    """新账号的默认队列还在读视图时，运行前的项目预约不能先交给重新导入。"""
    from app.task.MaaFW.tools.embedded import default_snapshot

    reading, allow_read = threading.Event(), threading.Event()
    load_interface = default_snapshot.load_interface_model_cached

    def delayed_read(*args, **kwargs):
        reading.set()
        if not allow_read.wait(10):
            raise TimeoutError("default snapshot read was not released")
        return load_interface(*args, **kwargs)

    monkeypatch.setattr(default_snapshot, "load_interface_model_cached", delayed_read)
    new_interface = json.loads((project.source / "interface.json").read_text())
    new_interface["name"] = "M9A"
    (project.source / "interface.json").write_text(json.dumps(new_interface))
    manager = project.make_manager()
    checking = asyncio.create_task(manager.check())
    try:
        assert await asyncio.to_thread(reading.wait, 5)
        reply = await api.reimport_embedded(project.script_id, str(project.source))
        assert reply.code == 400
        assert project.current_config() is project.config
        assert project.config.Info.Path == project.previous_source
        assert json.loads((project.view / "interface.json").read_text())["github"] == (
            "https://github.com/audit/aaaa"
        )
        allow_read.set()
        assert await asyncio.wait_for(checking, 5) == "Pass"
    finally:
        allow_read.set()
        await asyncio.gather(checking, return_exceptions=True)
        await manager._commit_user_data()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage", ["worker", "worker_cancel", "commit_cancel", "flavor_cancel"]
)
async def test_reimport_owns_view_until_worker_and_metadata_finish(
    project, monkeypatch, stage
):
    """真实导入先启动时阻止脚本；两次取消也不能越过文件线程或提交的异步窗口。"""
    committing, allow_commit = asyncio.Event(), asyncio.Event()
    allow_commit.set()
    flavor_read, allow_flavor = threading.Event(), threading.Event()
    allow_flavor.set()
    new_interface = json.loads((project.source / "interface.json").read_text())
    new_interface["name"] = "M9A"
    (project.source / "interface.json").write_text(json.dumps(new_interface))
    load_interface = api.load_interface_model_cached

    def delayed_flavor_read(*args, **kwargs):
        flavor_read.set()
        if not allow_flavor.wait(10):
            raise TimeoutError("flavor read was not released")
        return load_interface(*args, **kwargs)

    monkeypatch.setattr(api, "load_interface_model_cached", delayed_flavor_read)

    async def pause_commit(_sender, _event, **_kwargs):
        committing.set()
        await allow_commit.wait()

    project.config.connect(
        pause_commit, phase="runtime", kind="set", group="Embedded", field="Report"
    )
    if stage == "commit_cancel":
        allow_commit.clear()
    elif stage == "flavor_cancel":
        allow_flavor.clear()
    else:
        project.allow_import.clear()
    importing = asyncio.create_task(
        api.reimport_embedded(project.script_id, str(project.source))
    )
    manager = project.make_manager()
    try:
        if stage == "commit_cancel":
            await asyncio.wait_for(committing.wait(), 5)
        elif stage == "flavor_cancel":
            assert await asyncio.to_thread(flavor_read.wait, 5)
        else:
            assert await asyncio.to_thread(project.import_read.wait, 5)
        assert await manager.check() != "Pass"
        assert not manager._script_locked
        if stage != "flavor_cancel":
            assert project.config.is_locked
        assert await project_path.try_reserve_project_path(project.view) is None
        cancelled = stage.endswith("_cancel")
        if cancelled:
            importing.cancel()
            await asyncio.sleep(0)
            importing.cancel()
            await asyncio.sleep(0)
            assert not importing.done()
            if stage != "flavor_cancel":
                assert project.config.is_locked
            assert await project_path.try_reserve_project_path(project.view) is None
        project.allow_import.set()
        allow_commit.set()
        allow_flavor.set()
        if cancelled:
            with pytest.raises(asyncio.CancelledError):
                await importing
        else:
            assert (await importing).code == 200
        assert project.worker_done.is_set()
        config = project.current_config()
        assert isinstance(config, M9AConfig)
        assert len(config.UserData) == 1
        assert isinstance(config.UserData[project.user_uid], M9AUserConfig)
        assert config.UserData[project.user_uid].Info.Name == "audit"
        assert not config.is_locked
        assert config.Info.Path == project.source
        assert json.loads(config.Embedded.Report)["sourcePath"] == str(project.source)
        assert json.loads((project.view / "interface.json").read_text())["github"] == (
            "https://github.com/audit/bbbb"
        )
        retry = await api.reimport_embedded(project.script_id, str(project.source))
        assert retry.code == 200
    finally:
        project.allow_import.set()
        allow_commit.set()
        allow_flavor.set()
        await asyncio.gather(importing, return_exceptions=True)
        await asyncio.to_thread(project.worker_done.wait, 5)
        await manager._commit_user_data()
        if not project.config.deleted:
            project.config.disconnect(
                pause_commit,
                phase="runtime",
                kind="set",
                group="Embedded",
                field="Report",
            )
