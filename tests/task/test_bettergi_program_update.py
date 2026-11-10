"""BetterGI 官方安装边界、任务回退及运行期配置恢复。"""

import asyncio
import hashlib
import json
import shutil
import uuid
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from packaging.version import Version

from app.services import script_install
from app.task.BetterGI import manager
from app.task.BetterGI.tools import program_update as update
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed


def pe():
    data = bytearray(134)
    data[:2] = b"MZ"
    data[60:64] = (128).to_bytes(4, "little")
    data[128:132] = b"PE\0\0"
    data[132:134] = (0x8664).to_bytes(2, "little")
    return bytes(data)


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "BetterGI"
    (root / "User").mkdir(parents=True)
    (root / "BetterGI.exe").write_bytes(pe())
    (root / "User/config.json").write_text('{"custom": true}')
    source = tmp_path / "installer.exe"
    source.write_bytes(pe())
    release = {
        "tag_name": "0.56.0",
        "assets": [
            {
                "name": "BetterGI.Install.0.56.0.exe",
                "size": source.stat().st_size,
                "digest": "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        ],
    }
    monkeypatch.setattr(update, "assert_idle", lambda root: None)
    version = [Version("0.55.0")]
    monkeypatch.setattr(update, "read_version", lambda root: version[0])
    monkeypatch.setattr(update, "request_release", AsyncMock(return_value=release))
    monkeypatch.setattr(
        update, "check_stable_distribution", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        update,
        "Config",
        SimpleNamespace(
            proxy=None,
            setting=SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK="")),
        ),
    )

    async def download(url, destination, **kwargs):
        shutil.copyfile(source, destination)

    monkeypatch.setattr(
        update, "download_script_package", AsyncMock(side_effect=download)
    )

    async def install(installer, path):
        assert json.loads((path / "User/config.json").read_text()) == {"custom": True}
        version[0] = Version("0.56.0")

    monkeypatch.setattr(update, "run_installer", AsyncMock(side_effect=install))
    config = SimpleNamespace(
        Update=SimpleNamespace(
            TakeoverEnabled=True, Channel="stable", MirrorChyanCDK=""
        )
    )
    return root, config, release


@pytest.mark.asyncio
async def test_install_preserves_user_data_and_confirms_version(installation):
    root, config, _ = installation
    await update.update_before_run(root, config)
    await update.confirm_current_install(root)
    assert update.read_version(root) == Version("0.56.0")
    assert json.loads((root / "User/config.json").read_text()) == {"custom": True}
    assert update.download_script_package.await_args.kwargs["source"] == "GitHub"
    assert not list(script_install.workspace(root).glob("download-*"))


@pytest.mark.asyncio
async def test_bad_hash_cannot_start_installer(installation):
    root, config, release = installation
    release["assets"][0]["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError):
        await update.update_before_run(root, config)
    update.run_installer.assert_not_awaited()
    await update.confirm_current_install(root)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [RuntimeError("installer failed"), asyncio.CancelledError()]
)
async def test_interrupted_install_blocks_old_version_fallback(installation, error):
    root, config, _ = installation
    update.run_installer.side_effect = error
    with pytest.raises(type(error)):
        await update.update_before_run(root, config)
    with pytest.raises(script_install.InstallUnsafeError):
        await update.confirm_current_install(root)


@pytest.mark.asyncio
async def test_mirror_uses_its_archive_digest_and_keeps_cdk_out_of_download(
    installation, monkeypatch, tmp_path
):
    root, config, _ = installation
    config.Update.MirrorChyanCDK = "private-cdk"
    archive = tmp_path / "mirror.zip"
    # 上游在 Mirror 安装器后追加 VC 运行库，包内 exe 与 GitHub 哈希不同。
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("BetterGI.Install.0.56.0.exe", pe() + b"VC runtime")
    monkeypatch.setattr(
        update,
        "request_mirror_resource",
        AsyncMock(
            return_value={
                "data": {
                    "update_type": "full",
                    "version_name": "0.56.0",
                    "url": "https://mirror.example/installer.zip",
                    "filesize": archive.stat().st_size,
                    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                }
            }
        ),
    )

    async def download(url, destination, **kwargs):
        assert "private-cdk" not in url
        shutil.copyfile(archive, destination)

    update.download_script_package.side_effect = download
    await update.update_before_run(root, config)
    assert update.download_script_package.await_args.kwargs["source"] == "MirrorChyan"
    assert "os" not in update.request_mirror_resource.await_args.kwargs["params"]
    assert update.read_version(root) == Version("0.56.0")


def test_notice_restore_after_restart_preserves_other_changes(tmp_path, monkeypatch):
    root = tmp_path / "BetterGI"
    (root / "User").mkdir(parents=True)
    path = root / "User/config.json"
    path.write_text(json.dumps({update.NOTICE_KEY: "0.54.0", "custom": 1}))
    monkeypatch.setattr(update, "assert_idle", lambda root: None)
    update.suppress_update_notice(root)
    injected = json.loads(path.read_text())
    assert injected[update.NOTICE_KEY] == update.IGNORED_VERSION
    injected["custom"] = 2
    path.write_text(json.dumps(injected))
    update.recover_update_notice(root)
    assert json.loads(path.read_text()) == {update.NOTICE_KEY: "0.54.0", "custom": 2}
    # 用户在托管期间改了该项时保留新值，不盲目覆盖。
    update.suppress_update_notice(root)
    path.write_text(json.dumps({update.NOTICE_KEY: "0.57.0", "custom": 3}))
    update.recover_update_notice(root)
    assert json.loads(path.read_text())[update.NOTICE_KEY] == "0.57.0"


@pytest.mark.asyncio
async def test_batch_download_failure_continues_without_rechecking(
    installation, monkeypatch
):
    root, config, _ = installation
    instance = object.__new__(manager.BetterGIManager)
    instance._update_root = root
    instance._program_update_prepared = False
    instance.script_config = config
    instance.script_info = SimpleNamespace(script_id=str(uuid.uuid4()), log="")
    instance.task_info = SimpleNamespace(task_id=str(uuid.uuid4()))
    monkeypatch.setattr(manager.Publisher, "send", AsyncMock())
    update.download_script_package.side_effect = OSError("network unavailable")
    await instance._prepare_program_update()
    await instance._prepare_program_update()
    assert update.request_release.await_count == 1
    assert (
        json.loads((root / "User/config.json").read_text())[update.NOTICE_KEY]
        == update.IGNORED_VERSION
    )
    update.recover_update_notice(root)
    assert json.loads((root / "User/config.json").read_text()) == {"custom": True}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        script_install.InstallUnsafeError("busy"),
        FluxdownCancelUnconfirmed("cancel"),
        asyncio.CancelledError(),
    ],
)
async def test_unsafe_and_cancelled_preparation_never_runs_users(
    installation, monkeypatch, error
):
    root, config, _ = installation
    instance = object.__new__(manager.BetterGIManager)
    instance._update_root = root
    instance._program_update_prepared = False
    instance.script_config = config
    instance.script_info = SimpleNamespace(script_id=str(uuid.uuid4()), log="")
    instance.task_info = SimpleNamespace(task_id=str(uuid.uuid4()))
    monkeypatch.setattr(update, "update_before_run", AsyncMock(side_effect=error))
    with pytest.raises(type(error)):
        await instance._prepare_program_update()
    assert not instance._program_update_prepared
    assert json.loads((root / "User/config.json").read_text()) == {"custom": True}


@pytest.mark.asyncio
async def test_disabled_takeover_does_not_query_and_blocks_unfinished_install(
    installation,
):
    root, config, _ = installation
    config.Update.TakeoverEnabled = False
    instance = object.__new__(manager.BetterGIManager)
    instance._update_root = root
    instance._program_update_prepared = False
    instance.script_config = config
    await instance._prepare_program_update()
    update.request_release.assert_not_awaited()
    assert json.loads((root / "User/config.json").read_text()) == {"custom": True}
    marker = script_install.workspace(root) / "bgi-install.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}")
    instance._program_update_prepared = False
    with pytest.raises(script_install.InstallUnsafeError):
        await instance._prepare_program_update()


@pytest.mark.asyncio
async def test_installer_cancellation_waits_for_exit_before_returning(
    tmp_path, monkeypatch
):
    exited = asyncio.Event()
    monkeypatch.setattr(
        update.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=SimpleNamespace(wait=exited.wait)),
    )
    operation = asyncio.create_task(
        update.run_installer(tmp_path / "installer.exe", tmp_path)
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    operation.cancel()
    await asyncio.sleep(0)
    assert not operation.done()
    exited.set()
    with pytest.raises(asyncio.CancelledError):
        await operation


@pytest.mark.asyncio
async def test_success_exit_without_target_version_keeps_install_blocked(installation):
    root, config, _ = installation
    update.run_installer.side_effect = None
    with pytest.raises(script_install.InstallUnsafeError):
        await update.update_before_run(root, config)
    with pytest.raises(script_install.InstallUnsafeError):
        await update.confirm_current_install(root)


@pytest.mark.asyncio
async def test_notice_restore_failure_still_releases_all_locks(
    installation, monkeypatch
):
    from contextlib import ExitStack

    root, _, _ = installation
    instance = object.__new__(manager.BetterGIManager)
    instance._update_root = root
    instance.check_result = "failed"
    instance.script_info = SimpleNamespace(user_list=[], status="等待")
    instance.task_info = SimpleNamespace(mode="AutoProxy")
    instance.user_config = None
    unlocked = AsyncMock()
    config_uid = uuid.uuid4()
    instance.script_config = SimpleNamespace(uid=config_uid, unlock=unlocked)
    instance.config_locks = {config_uid: "ticket"}
    released = []
    instance._install_access = ExitStack()
    instance._install_access.callback(lambda: released.append(True))
    monkeypatch.setattr(
        update,
        "recover_update_notice",
        lambda root: (_ for _ in ()).throw(OSError("disk error")),
    )
    with pytest.raises(OSError):
        await instance.final_task()
    unlocked.assert_awaited_once_with("ticket")
    assert released == [True]
    assert instance.script_info.status == "异常"


@pytest.mark.asyncio
async def test_unsafe_update_is_not_reported_as_completed_during_finalization(
    installation, monkeypatch
):
    from contextlib import ExitStack

    root, config, _ = installation
    instance = object.__new__(manager.BetterGIManager)
    instance._update_root = root
    instance._program_update_prepared = False
    instance._install_access = ExitStack()
    instance.config_locks = {}
    instance.check_result = "Pass"
    instance.user_config = None
    instance.script_config = config
    config.uid = uuid.uuid4()
    instance.script_info = SimpleNamespace(
        script_id=str(uuid.uuid4()),
        name="BGI",
        log="",
        status="等待",
        user_list=[SimpleNamespace(status="等待")],
    )
    instance.task_info = SimpleNamespace(task_id=str(uuid.uuid4()), mode="AutoProxy")
    monkeypatch.setattr(
        update,
        "update_before_run",
        AsyncMock(side_effect=script_install.InstallUnsafeError("unfinished install")),
    )
    monkeypatch.setattr(manager.Publisher, "send", AsyncMock())
    monkeypatch.setattr(manager.Notify, "push_proxy_result", AsyncMock())
    instance.collect_user_results = lambda: SimpleNamespace(uncompleted_count=1)
    instance._render_user_results = lambda **kwargs: ""
    instance.build_proxy_report = lambda **kwargs: "failed"
    with pytest.raises(script_install.InstallUnsafeError) as failure:
        await instance._prepare_program_update()
    await instance.on_crash(failure.value)
    await instance.final_task()
    assert instance.script_info.status == "异常"


@pytest.mark.asyncio
async def test_installer_timeout_waits_for_exit_before_releasing_lock(
    tmp_path, monkeypatch
):
    finished = asyncio.Event()

    async def pending():
        await finished.wait()
        return 0

    monkeypatch.setattr(
        update.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=SimpleNamespace(wait=pending)),
    )
    original_wait_for = update.asyncio.wait_for

    async def timed_out(awaitable, timeout):
        raise TimeoutError("installer still running")

    monkeypatch.setattr(update.asyncio, "wait_for", timed_out)
    running = asyncio.create_task(
        update.run_installer(tmp_path / "installer.exe", tmp_path)
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert not running.done()
    finished.set()
    with pytest.raises(script_install.InstallUnsafeError, match="尚未退出"):
        await running
    monkeypatch.setattr(update.asyncio, "wait_for", original_wait_for)


@pytest.mark.asyncio
async def test_beta_release_does_not_silently_fall_back_to_stable(monkeypatch):
    stable = {"tag_name": "0.66.0", "draft": False, "prerelease": False, "assets": []}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return [stable]

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url):
            return Response()

    monkeypatch.setattr(update.httpx, "AsyncClient", lambda **kwargs: Client())
    with pytest.raises(ValueError, match="不会回退"):
        await update.request_release("beta")


@pytest.mark.asyncio
async def test_game_update_allows_running_bgi_but_refuses_native_installer(
    installation, monkeypatch
):
    root, _, _ = installation
    processes = [
        SimpleNamespace(
            info={"exe": str(root / "BetterGI.exe"), "name": "BetterGI.exe"}
        )
    ]
    monkeypatch.setattr(update.psutil, "process_iter", lambda fields: processes)
    await update.confirm_safe_game_update(root)
    processes.append(
        SimpleNamespace(
            info={
                "exe": str(
                    script_install.workspace(root)
                    / "download-1"
                    / "BetterGI.Install.0.66.exe"
                ),
                "name": "BetterGI.Install.0.66.exe",
            }
        )
    )
    with pytest.raises(script_install.InstallUnsafeError, match="安装器"):
        await update.confirm_safe_game_update(root)
    processes.pop()
    marker = script_install.workspace(root) / "bgi-install.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}")
    with pytest.raises(script_install.InstallUnsafeError, match="未确认"):
        await update.confirm_safe_game_update(root)


@pytest.mark.asyncio
async def test_beta_mirror_alpha_without_github_prerelease(
    installation, monkeypatch, tmp_path
):
    root, config, _ = installation
    config.Update.Channel = "beta"
    config.Update.MirrorChyanCDK = "test-cdk"
    version = [Version("0.66.0")]
    monkeypatch.setattr(update, "read_version", lambda _root: version[0])
    monkeypatch.setattr(
        update,
        "request_release",
        AsyncMock(
            side_effect=AssertionError("beta must not depend on GitHub Releases")
        ),
    )
    archive = tmp_path / "alpha.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("BetterGI.Install.0.66.3-alpha.1.exe", pe())
    monkeypatch.setattr(
        update,
        "request_mirror_resource",
        AsyncMock(
            return_value={
                "data": {
                    "update_type": "full",
                    "version_name": "0.66.3-alpha.1",
                    "url": "https://example.com/alpha.zip",
                    "filesize": archive.stat().st_size,
                    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                }
            }
        ),
    )

    async def download(url, destination, **kwargs):
        shutil.copyfile(archive, destination)

    async def install(installer, path):
        version[0] = Version("0.66.3-alpha.1")

    update.download_script_package.side_effect = download
    update.run_installer.side_effect = install
    assert "已更新" in await update.update_before_run(root, config)
    update.request_release.assert_not_awaited()
    assert (
        update.request_mirror_resource.await_args.kwargs["params"]["channel"] == "alpha"
    )


@pytest.mark.asyncio
async def test_mirror_accepts_upstream_sevenzip_nested_installer(
    installation, monkeypatch, tmp_path
):
    root, config, _ = installation
    config.Update.MirrorChyanCDK = "test-cdk"
    archive = tmp_path / "nested.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr(
            "downloads/BetterGI_Install/BetterGI.Install.0.56.0.exe",
            pe(),
        )
    monkeypatch.setattr(
        update,
        "request_mirror_resource",
        AsyncMock(
            return_value={
                "data": {
                    "update_type": "full",
                    "version_name": "0.56.0",
                    "url": "https://example.com/nested.zip",
                    "filesize": archive.stat().st_size,
                    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                }
            }
        ),
    )

    async def download(url, destination, **kwargs):
        shutil.copyfile(archive, destination)

    update.download_script_package.side_effect = download
    assert "已更新" in await update.update_before_run(root, config)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("notice", "resource", "status", "expected"),
    [
        (
            {"version": "0.67.0", "gray": 10},
            {
                "data": {
                    "metadata": {"tag_name": "v0.67.0"},
                    "index": {"BetterGI.exe": {}},
                    "installer_end": 42,
                }
            },
            200,
            None,
        ),
        (
            {"version": "0.66.0", "gray": 10},
            None,
            200,
            "尚未进入官方更新公告",
        ),
        (
            {"Version": "0.67.0", "Gray": 4},
            None,
            200,
            "灰度推送",
        ),
        (
            {"version": "0.67.0", "gray": 10},
            {
                "data": {
                    "metadata": {"tag_name": "v0.66.0"},
                    "index": {"BetterGI.exe": {}},
                    "installer_end": 42,
                }
            },
            200,
            "尚未同步",
        ),
        (
            {"version": "0.67.0", "gray": 10},
            {"data": None},
            200,
            "无法确认",
        ),
        (
            {"version": "0.67.0", "gray": 10},
            {"message": "Not Found"},
            404,
            "无法确认",
        ),
    ],
)
async def test_stable_distribution_precheck_requires_announced_complete_resources(
    monkeypatch, notice, resource, status, expected
):
    """模拟 BetterGI 公告早于资源分发及 DFS2 无元数据；绝不依赖真实网络。"""
    import httpx

    original_client = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(str(request.url))
        if request.url.path.endswith("/notice.json"):
            return httpx.Response(200, json=notice)
        assert request.url.path.endswith("/BetterGI.Install.exe")
        assert request.url.params.get("with_metadata") == "1"
        return httpx.Response(status, json=resource)

    monkeypatch.setattr(
        update.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler)),
    )
    result = await update.check_stable_distribution(Version("0.67.0"))
    if expected is None:
        assert result is None
    else:
        assert expected in result
    checked_notice_only = expected in ("尚未进入官方更新公告", "灰度推送")
    assert len(requests) == (1 if checked_notice_only else 2)


@pytest.mark.asyncio
async def test_unready_stable_release_keeps_old_install_without_marker(
    installation, monkeypatch
):
    root, config, _ = installation
    monkeypatch.setattr(
        update,
        "check_stable_distribution",
        AsyncMock(return_value="BetterGI 新版安装资源尚未同步，暂缓本次更新"),
    )
    result = await update.update_before_run(root, config)
    assert "暂缓本次更新" in result
    update.download_script_package.assert_not_awaited()
    update.run_installer.assert_not_awaited()
    assert not (script_install.workspace(root) / "bgi-install.json").exists()
    assert update.read_version(root) == Version("0.55.0")


@pytest.mark.asyncio
async def test_unready_release_does_not_bypass_existing_unconfirmed_install(
    installation, monkeypatch
):
    root, config, _ = installation
    marker = script_install.workspace(root) / "bgi-install.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text('{"target":"0.56.0"}')
    monkeypatch.setattr(
        update,
        "check_stable_distribution",
        AsyncMock(return_value="BetterGI 安装资源暂不可用"),
    )
    with pytest.raises(script_install.InstallUnsafeError, match="上次安装仍未确认"):
        await update.update_before_run(root, config)
    assert marker.exists()
    update.run_installer.assert_not_awaited()


def test_offroot_bettergi_installer_is_not_treated_as_idle(tmp_path, monkeypatch):
    root = tmp_path / "BetterGI"
    installer = tmp_path / "downloads" / "BetterGI.Install.0.56.0.exe"
    monkeypatch.setattr(
        update.script_install, "assert_no_pending_process", lambda root: None
    )
    monkeypatch.setattr(
        update.psutil,
        "process_iter",
        lambda attrs: [SimpleNamespace(info={"exe": str(installer), "name": "setup.exe"})],
    )
    with pytest.raises(script_install.InstallUnsafeError, match="官方安装器"):
        update.assert_idle(root)
