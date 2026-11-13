"""旧版本入口不再更新时，自动与手动更新仍交给官方启动器。"""

import base64
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.models.config import OkwwConfig, OkwwUserConfig
from app.task.Okww import AutoProxy as proxy_module
from app.task.Okww.AutoProxy import AutoProxyTask
from app.task.Okww.tools import launcher_start
from app.task.Okww.Update import WuwaUpdateTask
from app.utils import ProcessManager
from tests.config_support import activate_config
from tests.runtime_support import create_runtime_tree


@pytest_asyncio.fixture
async def update_context(tmp_path, monkeypatch):
    launcher = tmp_path / "launcher/launcher.exe"
    launcher.parent.mkdir()
    launcher.touch()
    install = tmp_path / "game"
    client = install / "Client/Binaries/Win64/Client-Win64-Shipping.exe"
    client.parent.mkdir(parents=True)
    client.touch()
    cache = launcher.parent / "kr_game_cache/kr_game_temp.bin"
    cache.parent.mkdir()
    raw = json.dumps({"installDirPath": str(install)}).encode()
    cache.write_bytes(base64.b64encode(bytes(value ^ 0x63 for value in raw)))
    (install / "launcherDownloadConfig.json").write_text('{"version":"3.7.1"}')
    config = OkwwConfig.model_validate(
        {"Game": {"Enabled": True, "Path": str(launcher), "WaitTime": 0}}
    )
    await activate_config(config)
    uid = uuid.uuid4()
    user_config = OkwwUserConfig()
    await activate_config(user_config)
    # 子节点通过弱引用访问所属任务；夹具存续期间保留根节点。
    root, script, user = await create_runtime_tree(user_id=str(uid))
    opened = []

    async def open_process(self, path, *args, **kwargs):
        opened.append(path)

    monkeypatch.setattr(ProcessManager, "open_process", open_process)
    monkeypatch.setattr(ProcessManager, "kill", AsyncMock())
    monkeypatch.setattr(proxy_module, "is_process_running", lambda name: False)
    monkeypatch.setattr(launcher_start, "find_launcher_pids", lambda path: [])
    monkeypatch.setattr(launcher_start, "find_client_pids", lambda *args: set())
    monkeypatch.setattr(launcher_start, "has_launcher_window", lambda path: False)
    interact = AsyncMock(return_value=True)
    monkeypatch.setattr(launcher_start, "async_start_game_via_launcher", interact)

    # 实测旧公开入口仍返回 3.7.1；不能用它把新版启动器误判为已更新。
    client_class = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"default": {"version": "3.7.1"}})
    )
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(transport=transport, **kwargs),
    )
    yield config, {uid: user_config}, script, user, launcher, client, opened, interact
    del root


@pytest.mark.asyncio
async def test_manual_update_uses_launcher_when_legacy_feed_is_unchanged(
    update_context,
):
    config, _, script, user, launcher, _, opened, interact = update_context
    await WuwaUpdateTask(script, config).main_task()
    assert opened == [launcher]
    assert interact.await_args.kwargs["update_only"] is True
    assert user.status == "完成"


@pytest.mark.asyncio
async def test_manual_update_allows_launcher_to_restore_missing_client(update_context):
    config, _, script, user, launcher, client, opened, interact = update_context
    client.unlink()

    async def restore_client(*args, **kwargs):
        client.touch()

    interact.side_effect = restore_client
    await WuwaUpdateTask(script, config).main_task()
    assert opened == [launcher]
    assert client.is_file()
    assert user.status == "完成"


@pytest.mark.asyncio
async def test_auto_update_precedes_direct_launch(update_context):
    config, users, script, _, launcher, client, opened, interact = update_context
    proxy = AutoProxyTask(script, config, users, ProcessManager())
    proxy.launcher_path = launcher
    proxy.game_process_path = client
    await proxy._mas_launch_game_before_task()
    assert opened == [launcher, client]
    assert interact.await_args.kwargs["update_only"] is True


@pytest.mark.asyncio
async def test_update_failure_blocks_direct_launch(update_context):
    config, users, script, _, launcher, client, opened, interact = update_context
    interact.side_effect = RuntimeError("launcher unavailable")
    proxy = AutoProxyTask(script, config, users, ProcessManager())
    proxy.launcher_path = launcher
    proxy.game_process_path = client
    with pytest.raises(RuntimeError, match="launcher unavailable"):
        await proxy._mas_launch_game_before_task()
    assert client not in opened


@pytest.mark.asyncio
@pytest.mark.parametrize("configured_launcher", [False, True])
async def test_client_only_auto_update_preserves_optional_launcher(
    update_context, configured_launcher
):
    config, users, script, _, path, client, opened, interact = update_context
    await config.update(
        OkwwConfig.model_validate(
            {
                "Game": {
                    "Path": str(path) if configured_launcher else None,
                    "ClientPath": str(client),
                }
            }
        )
    )
    proxy = AutoProxyTask(script, config, users, ProcessManager())
    # 路径通过配置校验后启动器被删除，与从未配置启动器是不同的可达情况。
    path.unlink()
    proxy.launcher_path = path if configured_launcher else Path("")
    proxy.game_process_path = client

    if not configured_launcher:
        await proxy._mas_launch_game_before_task()
        assert opened == [client]
    else:
        with pytest.raises(RuntimeError):
            await proxy._mas_launch_game_before_task()
        assert opened == []
    interact.assert_not_awaited()


def select_quality(launcher, quality):
    raw = json.dumps(
        {"activeGameScope": {"gameIdentity": "Aki", "bundleName": quality}}
    ).encode()
    (launcher.parent / "kr_game_cache/platform_ui_state.bin").write_bytes(
        base64.b64encode(bytes(value ^ 0x63 for value in raw))
    )


@pytest.mark.asyncio
async def test_direct_launch_uses_updated_launcher_quality(update_context, monkeypatch):
    config, users, script, _, launcher, client, _, _ = update_context
    select_quality(launcher, "UHD")
    started = []

    async def open_process(self, path, *args, **kwargs):
        started.append((path, args))

    monkeypatch.setattr(ProcessManager, "open_process", open_process)
    proxy = AutoProxyTask(script, config, users, ProcessManager())
    proxy.launcher_path = launcher
    proxy.game_process_path = client
    await proxy._mas_launch_game_before_task()
    assert started[-1] == (client, ("-krqlv=uhd",))


@pytest.mark.asyncio
async def test_explicit_quality_mismatch_does_not_update_other_package(update_context):
    config, users, script, _, launcher, client, opened, interact = update_context
    await config.update(OkwwConfig.model_validate({"Game": {"Arguments": "-krqlv=hd"}}))
    select_quality(launcher, "UHD")
    proxy = AutoProxyTask(script, config, users, ProcessManager())
    proxy.launcher_path = launcher
    proxy.game_process_path = client
    with pytest.raises(RuntimeError):
        await proxy._mas_launch_game_before_task()
    assert opened == []
    interact.assert_not_awaited()


@pytest.mark.asyncio
async def test_launcher_mode_ignores_direct_client_quality_argument(update_context):
    config, users, script, _, path, client, opened, interact = update_context
    await config.update(
        OkwwConfig.model_validate(
            {"Game": {"Type": "Launcher", "Arguments": "-krqlv=hd"}}
        )
    )
    select_quality(path, "UHD")
    proxy = AutoProxyTask(script, config, users, ProcessManager())
    proxy.launcher_path = path
    proxy.game_process_path = client

    await proxy._ensure_wuthering_waves_updated()

    assert opened == [path]
    assert interact.await_args.kwargs["update_only"] is True


@pytest.mark.asyncio
async def test_quality_change_during_update_blocks_direct_launch(update_context):
    config, users, script, _, launcher, client, opened, interact = update_context
    select_quality(launcher, "HD")

    async def switch_quality(*args, **kwargs):
        select_quality(launcher, "UHD")

    interact.side_effect = switch_quality
    proxy = AutoProxyTask(script, config, users, ProcessManager())
    proxy.launcher_path = launcher
    proxy.game_process_path = client
    with pytest.raises(RuntimeError):
        await proxy._mas_launch_game_before_task()
    assert client not in opened


@pytest.mark.asyncio
async def test_manual_update_checks_resolved_game_outside_launcher_tree(
    update_context, monkeypatch
):
    config, _, script, _, launcher, client, opened, interact = update_context
    observed = []

    def find_running(actual_client, actual_launcher):
        observed.append((actual_client, actual_launcher))
        return {123}

    monkeypatch.setattr(launcher_start, "find_client_pids", find_running)
    with pytest.raises(RuntimeError):
        await WuwaUpdateTask(script, config).main_task()
    assert observed == [(client, launcher)]
    assert opened == []
    interact.assert_not_awaited()
