"""运行前更新的准备回退、安装中断恢复与一次更新多用户启动。"""

import asyncio
import hashlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from packaging.version import Version

from app.task.Whimbox import manager
from app.task.Whimbox.tools import update
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "Whimbox"
    (root / "python-embedded").mkdir(parents=True)
    (root / update.APP_EXE_NAME).touch()
    (root / update.REL_PYTHON_EXE).touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(update, "find_upstream_pids", lambda root: [])
    monkeypatch.setattr(
        update,
        "Config",
        SimpleNamespace(
            proxy=None,
            setting=SimpleNamespace(Update=SimpleNamespace(FluxdownTakeoverAll=False)),
        ),
    )
    wheel = b"official-wheel"
    release = {
        "tag_name": "3.1.1",
        "assets": [
            {
                "name": "whimbox-3.1.1-py3-none-any.whl",
                "digest": "sha256:" + hashlib.sha256(wheel).hexdigest(),
            }
        ],
    }
    monkeypatch.setattr(update, "request_release", AsyncMock(return_value=release))
    monkeypatch.setattr(
        update, "installed_version", AsyncMock(return_value=Version("3.1.0"))
    )
    monkeypatch.setattr(update, "run_python", AsyncMock(return_value=""))

    async def download(url, path, **kwargs):
        path.write_bytes(wheel)

    monkeypatch.setattr(update, "download_file", AsyncMock(side_effect=download))
    return root


@pytest.mark.asyncio
async def test_no_downgrade_or_unnecessary_install(installation):
    update.installed_version.return_value = Version("3.2.0")
    await update.ensure_backend_updated(installation)
    update.download_file.assert_not_awaited()
    update.run_python.assert_not_awaited()


@pytest.mark.asyncio
async def test_installs_and_verifies_before_clearing_marker(installation):
    update.installed_version.side_effect = [Version("3.1.0"), Version("3.1.1")]
    await update.ensure_backend_updated(installation)
    assert not update.pending_marker(installation).exists()
    calls = update.run_python.await_args_list
    assert "wheel" in calls[0].args
    assert "--no-build-isolation" not in calls[0].args
    assert "install" in calls[1].args
    assert "--no-index" in calls[1].args
    assert "--only-binary=:all:" in calls[1].args
    assert "--upgrade" in calls[1].args
    assert calls[2].args[1:] == ("-m", "pip", "check")
    assert update.download_file.await_args.kwargs["source"] == "GitHub"


@pytest.mark.asyncio
async def test_partial_install_blocks_fallback_then_forces_repair(
    installation, monkeypatch
):
    async def fail_install(root, *args, **kwargs):
        if "install" in args:
            raise RuntimeError("interrupted pip")
        return ""

    update.run_python.side_effect = fail_install
    with pytest.raises(RuntimeError):
        await update.ensure_backend_updated(installation)
    assert update.pending_marker(installation).exists()
    with pytest.raises(update.WhimboxUpdateUnsafeError):
        await update.confirm_usable_installation(installation)
    # 版本已写入也不能跳过残留未完成标记。
    update.installed_version.return_value = Version("3.1.1")
    update.run_python.side_effect = None
    await update.ensure_backend_updated(installation)
    assert not update.pending_marker(installation).exists()
    installs = [
        call for call in update.run_python.await_args_list if "install" in call.args
    ]
    assert "--force-reinstall" in installs[-1].args


@pytest.mark.asyncio
async def test_bad_download_never_starts_installation(installation):
    update.request_release.return_value["assets"][0]["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError):
        await update.ensure_backend_updated(installation)
    assert not update.pending_marker(installation).exists()
    update.run_python.assert_not_awaited()


@pytest.mark.asyncio
async def test_install_cancel_keeps_marker(installation):
    async def cancel_install(root, *args, **kwargs):
        if "install" in args:
            raise asyncio.CancelledError()
        return ""

    update.run_python.side_effect = cancel_install
    with pytest.raises(asyncio.CancelledError):
        await update.ensure_backend_updated(installation)
    assert update.pending_marker(installation).exists()


@pytest.mark.asyncio
async def test_version_mismatch_keeps_marker(installation):
    with pytest.raises(RuntimeError):
        await update.ensure_backend_updated(installation)
    assert update.pending_marker(installation).exists()


def test_access_lock_excludes_same_installation(installation):
    with update.installation_access(installation):
        with pytest.raises(RuntimeError):
            with update.installation_access(installation):
                pytest.fail("concurrent installation access")
    with update.installation_access(installation):
        pass


@pytest.fixture
def managed_batch(installation, monkeypatch):
    instance = object.__new__(manager.WhimboxManager)
    users = [
        SimpleNamespace(user_id=str(uuid.uuid4()), status="等待") for _ in range(2)
    ]
    instance.script_info = SimpleNamespace(
        script_id=str(uuid.uuid4()), user_list=users, current_index=0, log=""
    )
    instance.script_config = SimpleNamespace(
        Update=SimpleNamespace(TakeoverEnabled=True)
    )
    instance.user_config = {uuid.UUID(user.user_id): object() for user in users}
    instance.task_info = SimpleNamespace(mode="AutoProxy", task_id="test")
    instance.check_result = "Pass"
    instance.check_user_before_run = AsyncMock(return_value=True)
    instance.run_user_task = AsyncMock()
    monkeypatch.setattr(
        manager,
        "AutoProxyTask",
        lambda **kwargs: SimpleNamespace(check=AsyncMock(return_value="Pass")),
    )
    monkeypatch.setattr(
        manager, "ensure_backend_updated", AsyncMock(return_value="updated")
    )
    monkeypatch.setattr(manager, "confirm_usable_installation", AsyncMock())
    monkeypatch.setattr(manager, "push_dispatch_log", AsyncMock())
    monkeypatch.setattr(manager.Publisher, "send", AsyncMock())
    return instance


@pytest.mark.asyncio
async def test_updates_once_before_all_users(managed_batch, installation):
    async def updated(root):
        managed_batch.run_user_task.assert_not_awaited()
        return "updated"

    manager.ensure_backend_updated.side_effect = updated
    await managed_batch._run_prepared(installation)
    manager.ensure_backend_updated.assert_awaited_once_with(installation)
    assert managed_batch.run_user_task.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TimeoutError(), ValueError(), OSError()])
async def test_preparation_failure_warns_and_continues(
    managed_batch, installation, error
):
    manager.ensure_backend_updated.side_effect = error
    await managed_batch._run_prepared(installation)
    manager.confirm_usable_installation.assert_awaited_once_with(installation)
    assert managed_batch.run_user_task.await_count == 2
    assert managed_batch.check_result == "Pass"
    manager.Publisher.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_warning_delivery_failure_still_continues(managed_batch, installation):
    manager.ensure_backend_updated.side_effect = TimeoutError()
    manager.Publisher.send.side_effect = RuntimeError()
    await managed_batch._run_prepared(installation)
    assert managed_batch.run_user_task.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        asyncio.CancelledError(),
        FluxdownCancelUnconfirmed("active"),
        update.WhimboxUpdateUnsafeError("partial"),
    ],
)
async def test_unsafe_or_cancelled_update_never_falls_back(
    managed_batch, installation, error
):
    manager.ensure_backend_updated.side_effect = error
    with pytest.raises(type(error)):
        await managed_batch._run_prepared(installation)
    manager.confirm_usable_installation.assert_not_awaited()
    managed_batch.run_user_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_fallback_rejects_unusable_installation(managed_batch, installation):
    manager.ensure_backend_updated.side_effect = TimeoutError()
    manager.confirm_usable_installation.side_effect = update.WhimboxUpdateUnsafeError(
        "unusable"
    )
    with pytest.raises(update.WhimboxUpdateUnsafeError):
        await managed_batch._run_prepared(installation)
    managed_batch.run_user_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_takeover_cannot_bypass_partial_install(
    managed_batch, installation
):
    managed_batch.script_config.Update.TakeoverEnabled = False
    update.pending_marker(installation).touch()
    with pytest.raises(RuntimeError):
        await managed_batch._run_prepared(installation)
    manager.ensure_backend_updated.assert_not_awaited()
    managed_batch.run_user_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_takeover_keeps_existing_run(managed_batch, installation):
    managed_batch.script_config.Update.TakeoverEnabled = False
    await managed_batch._run_prepared(installation)
    manager.ensure_backend_updated.assert_not_awaited()
    assert managed_batch.run_user_task.await_count == 2


@pytest.mark.asyncio
async def test_dependency_download_failure_does_not_dirty_installation(installation):
    update.run_python.side_effect = TimeoutError()
    with pytest.raises(TimeoutError):
        await update.ensure_backend_updated(installation)
    assert not update.pending_marker(installation).exists()
    assert all("install" not in call.args for call in update.run_python.await_args_list)


@pytest.mark.asyncio
async def test_fallback_checks_real_installation_boundaries(installation, monkeypatch):
    monkeypatch.setattr(
        update.WheelAssetsConfigSurface, "check_install", lambda self: None
    )
    await update.confirm_usable_installation(installation)
    update.installed_version.assert_awaited_once_with(installation)
    assert update.run_python.await_args_list[0].args[1:] == ("-m", "pip", "check")
    monkeypatch.setattr(update, "find_upstream_pids", lambda root: [123])
    with pytest.raises(update.WhimboxUpdateUnsafeError):
        await update.confirm_usable_installation(installation)


def test_old_configs_default_to_no_takeover_and_patch_contract_is_generated():
    from app.config.wire import config_contract
    from app.models.config import WhimboxConfig

    assert WhimboxConfig.model_validate({}).Update.TakeoverEnabled is False
    contract = config_contract(WhimboxConfig, mode="input")
    patch = contract.model_validate({"Update": {"TakeoverEnabled": True}})
    assert patch.model_dump(exclude_unset=True) == {"Update": {"TakeoverEnabled": True}}


def test_release_must_match_official_package_and_digest():
    with pytest.raises(ValueError):
        update.select_wheel(
            {"tag_name": "3.1.1", "assets": [{"name": "other-3.1.1-py3-none-any.whl"}]}
        )
    with pytest.raises(ValueError):
        update.select_wheel(
            {
                "tag_name": "3.1.1",
                "assets": [
                    {"name": "whimbox-3.1.1-py3-none-any.whl", "digest": "invalid"}
                ],
            }
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("repairing", [False, True])
async def test_wheel_build_failure_preserves_previous_install_state(
    installation, repairing
):
    marker = update.pending_marker(installation)
    if repairing:
        marker.write_text("previous-attempt", encoding="utf-8")
    directories = []

    async def fail_build(root, *args, **kwargs):
        assert "wheel" in args
        assert "--no-build-isolation" not in args
        directories.append(update.Path(args[args.index("--wheel-dir") + 1]))
        assert marker.exists() is repairing
        raise RuntimeError("build dependency unavailable")

    update.run_python.side_effect = fail_build
    with pytest.raises(RuntimeError, match="build dependency unavailable"):
        await update.ensure_backend_updated(installation)
    assert marker.exists() is repairing
    if repairing:
        assert marker.read_text(encoding="utf-8") == "previous-attempt"
    assert directories and all(not directory.exists() for directory in directories)
    assert update.run_python.await_count == 1


@pytest.mark.asyncio
async def test_wheelhouse_is_fresh_and_install_is_binary_only(installation):
    directories = []
    marker = update.pending_marker(installation)

    async def run(root, *args, **kwargs):
        if "wheel" in args:
            directory = update.Path(args[args.index("--wheel-dir") + 1])
            assert not list(directory.iterdir())
            directories.append(directory)
            assert not marker.exists()
        elif "install" in args:
            assert marker.exists()
            assert "--no-index" in args and "--only-binary=:all:" in args
            assert update.Path(args[args.index("--find-links") + 1]) == directories[-1]
        return ""

    update.run_python.side_effect = run
    update.installed_version.side_effect = [
        Version("3.1.0"),
        Version("3.1.1"),
        Version("3.1.0"),
        Version("3.1.1"),
    ]
    await update.ensure_backend_updated(installation)
    await update.ensure_backend_updated(installation)
    assert len(directories) == 2 and directories[0] != directories[1]
    assert all(not directory.exists() for directory in directories)
    assert not marker.exists()


@pytest.mark.asyncio
async def test_build_uses_configured_proxy_without_credentials_in_arguments(
    installation, monkeypatch
):
    import httpx

    proxy = httpx.Proxy("http://127.0.0.1:7890", auth=("user", "secret-password"))
    monkeypatch.setattr(update.Config, "proxy", proxy)
    update.installed_version.side_effect = [Version("3.1.0"), Version("3.1.1")]
    await update.ensure_backend_updated(installation)
    build = update.run_python.await_args_list[0]
    assert build.kwargs["env"]["https_proxy"] == (
        "http://user:secret-password@127.0.0.1:7890"
    )
    assert "secret-password" not in repr(build.args)
    assert "env" not in update.run_python.await_args_list[1].kwargs


@pytest.mark.asyncio
async def test_app_repair_does_not_bypass_pending_marker(installation):
    marker = update.pending_marker(installation)
    marker.write_text("3.1.1", encoding="utf-8")
    update.installed_version.return_value = Version("3.1.1")
    with pytest.raises(update.WhimboxUpdateUnsafeError) as error:
        await update.confirm_usable_installation(installation)
    assert str(error.value) == update.RECOVERY_HINT
    assert marker.exists()
    update.installed_version.assert_not_awaited()
