"""公共脚本安装恢复状态机：拒绝半安装，允许安全旧版并延后报告。"""

from unittest.mock import AsyncMock

import pytest

from app.core.script_update_recovery import (
    DownloadRetryFailed,
    InstallInspection,
    InstallReportedFailure,
    InstallTimedOut,
    run_managed_installation,
)
from app.services.script_install import InstallUnsafeError
from app.services.script_install_backup import ManagedInstallBackup


@pytest.mark.asyncio
@pytest.mark.parametrize("first_failure", ["timeout", "unconfirmed_writer"])
async def test_failed_install_retains_backup_until_writer_stops_then_recovers(
    tmp_path, first_failure
):
    root = tmp_path / "MAA"
    root.mkdir()
    exe = root / "program.exe"
    exe.write_bytes(b"old-good")
    events = []
    install_count = 0
    active = False

    async def inspect():
        blob = exe.read_bytes()
        return InstallInspection(
            pending=blob == b"pending",
            healthy=blob in {b"old-good", b"new-good"},
            installed_version="1.0.0" if blob == b"old-good" else "1.1.0",
            updated_confirmed=blob == b"new-good",
            previous_confirmed=blob == b"old-good",
        )

    async def install():
        nonlocal install_count, active
        install_count += 1
        if install_count == 1:
            exe.write_bytes(b"pending")
            if first_failure == "unconfirmed_writer":
                active = True
                raise InstallReportedFailure(
                    "installer failed while child still writing"
                )
            raise InstallTimedOut("installer timed out")
        raise DownloadRetryFailed(source="GitHub", reason="network timed out again")

    async def ensure_idle():
        if active:
            raise InstallUnsafeError("installer is still writing")

    args = dict(
        script_id="one",
        script_type="MAA",
        install_root=root,
        inspect=inspect,
        acknowledge=AsyncMock(),
        install=install,
        ensure_idle=ensure_idle,
        after_rollback=AsyncMock(),
        report=events.append,
    )
    with pytest.raises(
        InstallUnsafeError,
        match="下一次运行" if first_failure == "timeout" else "still writing",
    ):
        await run_managed_installation(**args)
    backup = ManagedInstallBackup(root, script_id="one", script_type="MAA")
    assert backup.read()["phase"] == (
        "timed_out" if first_failure == "timeout" else "installing"
    )
    assert exe.read_bytes() == b"pending"
    assert events[-1].outcome == (
        "deferred" if first_failure == "timeout" else "blocked"
    )
    if active:
        with pytest.raises(InstallUnsafeError, match="still writing"):
            await run_managed_installation(**args)
        assert install_count == 1 and exe.read_bytes() == b"pending"
    active = False
    assert await run_managed_installation(**args) == "old_version"
    assert exe.read_bytes() == b"old-good"
    assert not backup.record.exists()
    assert install_count == 2
    assert events[-1].source == "GitHub"
    assert "再次下载失败" in events[-1].reason


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["interrupted_swap", "tampered_backup"])
async def test_managed_recovery_only_restores_a_trusted_backup(tmp_path, state):
    root = tmp_path / "script"
    root.mkdir()
    (root / "bin").write_bytes(b"old")
    backup = ManagedInstallBackup(root, script_id="one", script_type="SRC")
    await backup.create("1.0.0")
    backup.set_phase("installing")
    (root / "bin").write_bytes(b"broken-install")
    backup.set_phase("restoring")
    if state == "interrupted_swap":
        root.replace(backup.failed)
        backup.snapshot.replace(root)
    else:
        (backup.snapshot / "bin").write_bytes(b"tampered-backup")
    reinstall = AsyncMock()

    async def inspect():
        return InstallInspection(
            pending=False,
            healthy=(root / "bin").read_bytes() == b"old",
            installed_version="1.0.0",
            previous_confirmed=(root / "bin").read_bytes() == b"old",
        )

    events = []
    args = dict(
        script_id="one",
        script_type="SRC",
        install_root=root,
        inspect=inspect,
        acknowledge=AsyncMock(),
        install=reinstall,
        ensure_idle=AsyncMock(),
        after_rollback=AsyncMock(),
        report=events.append,
    )
    if state == "interrupted_swap":
        assert await run_managed_installation(**args) == "old_version"
        assert (root / "bin").read_bytes() == b"old"
        assert not backup.record.exists()
    else:
        with pytest.raises(InstallUnsafeError, match="备份文件不完整"):
            await run_managed_installation(**args)
        assert events[-1].outcome == "blocked"
        assert (root / "bin").read_bytes() == b"broken-install"
        assert (backup.snapshot / "bin").read_bytes() == b"tampered-backup"
        assert backup.record.exists()
    reinstall.assert_not_awaited()


@pytest.mark.asyncio
async def test_symlinked_backup_workspace_is_never_followed(tmp_path):
    from app.services import script_install

    root = tmp_path / "script"
    root.mkdir()
    (root / "bin").write_bytes(b"old")
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace = script_install.workspace(root)
    try:
        workspace.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("当前系统未允许创建目录符号链接")
    backup = ManagedInstallBackup(root, script_id="one", script_type="MAA")
    with pytest.raises(InstallUnsafeError, match="链接|重解析"):
        await backup.create("1.0.0")
    assert not any(outside.iterdir())
