# Copyright © 2025-2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""BAAH 官方完整包恢复适配器；公共入口负责恢复策略和任务末尾报告。"""

import asyncio
from pathlib import Path
from uuid import uuid4

from packaging.version import Version

from app.core.script_update_recovery import InstallInspection
from app.services import script_install
from app.services.script_install_backup import ManagedInstallBackup

from . import program_update


class BAAHInstallAdapter:
    def __init__(
        self,
        root: Path,
        config,
        *,
        prepared: program_update.PreparedUpdate | None = None,
        recovery_receipt: bytes | None = None,
    ) -> None:
        self.root = root
        self.config = config
        self.prepared = prepared
        self.recovery_receipt = recovery_receipt

    async def ensure_idle(self) -> None:
        await asyncio.to_thread(program_update.assert_idle, self.root)

    async def inspect(self) -> InstallInspection:
        await self.ensure_idle()
        pending_file = script_install.workspace(self.root) / "transaction.json"
        if pending_file.is_symlink():
            raise script_install.InstallUnsafeError("BAAH 原生事务标记为链接")
        pending = pending_file.exists()
        version = None
        healthy = False
        try:
            await program_update.confirm_current_install(self.root)
            version = await asyncio.to_thread(program_update.read_version, self.root)
            healthy = not pending
        except (script_install.InstallUnsafeError, OSError, ValueError, KeyError):
            healthy = False
        target = self.prepared.version if self.prepared else None
        previous = None
        if self.prepared is None:
            state = ManagedInstallBackup(
                self.root, script_id="", script_type="BAAH"
            ).read()
            if state and state.get("version"):
                previous = Version(state["version"])
            elif version is not None and not pending:
                previous = version
        else:
            try:
                previous = await asyncio.to_thread(
                    program_update.read_version, self.root
                )
            except (OSError, ValueError, KeyError):
                previous = None
        return InstallInspection(
            pending=pending or (not healthy and self.recovery_receipt is not None),
            healthy=healthy,
            installed_version=str(version) if version else None,
            target_version=str(target) if target else None,
            updated_confirmed=bool(
                healthy
                and (
                    (target is not None and version == target)
                    or (
                        previous is not None
                        and version is not None
                        and version > previous
                    )
                )
            ),
            previous_confirmed=bool(
                healthy and not pending and previous is not None and version == previous
            ),
        )

    async def acknowledge(self) -> None:
        await self.ensure_idle()
        await script_install.run_worker(
            script_install.recover_install,
            self.root,
            lambda: program_update.assert_idle(self.root),
        )
        await program_update.confirm_current_install(self.root)

    async def install(self) -> None:
        if self.prepared:
            await program_update.apply_update(self.root, self.prepared)
        else:
            await program_update.update_before_run(
                self.root,
                self.config,
                recovery_receipt=self.recovery_receipt,
            )

    async def after_rollback(self) -> None:
        await self.ensure_idle()
        # 如果安装回执无法匹配已恢复旧版，则不能宣称回滚完成并启动任务。
        await program_update.confirm_current_install(self.root)


async def inspect_stale_transaction(root: Path) -> InstallInspection:
    """只接受原安装回执已验证、目录切换已结束的遗留事务。"""
    await asyncio.to_thread(program_update.assert_idle, root)
    directory = script_install.workspace(root)
    marker = directory / "transaction.json"
    previous = directory / "previous"
    ready = directory / "ready"
    if any(path.is_symlink() for path in (marker, previous, ready)):
        raise script_install.InstallUnsafeError("BAAH 恢复目录包含符号链接")
    pending = marker.exists()
    if previous.exists() or ready.exists():
        return InstallInspection(pending=pending, healthy=False)
    receipt = script_install.record_path(root, "installed.json")
    if not receipt.is_file() or receipt.is_symlink():
        return InstallInspection(pending=pending, healthy=False)
    try:
        arch = await asyncio.to_thread(
            script_install.read_pe_architecture, root / "BAAH.exe"
        )
        version = await asyncio.to_thread(program_update.read_version, root)
        verified = await script_install.run_worker(
            script_install.verify_installed_files, root
        )
    except (OSError, ValueError, KeyError):
        return InstallInspection(pending=pending, healthy=False)
    healthy = arch == "x86_64" and verified
    return InstallInspection(
        pending=pending,
        healthy=healthy,
        installed_version=str(version),
        updated_confirmed=healthy,
        previous_confirmed=healthy and not pending,
    )


async def acknowledge_stale_transaction(root: Path) -> None:
    """经公共入口确认后归档旧 journal，不接受有 backup/ready 的回滚事务。"""
    state = await inspect_stale_transaction(root)
    if not (state.pending and state.healthy and state.updated_confirmed):
        raise script_install.InstallUnsafeError("旧 BAAH 安装事务无法确认完整")
    directory = script_install.workspace(root)
    marker = directory / "transaction.json"
    snapshot = marker.read_bytes()
    if not snapshot or len(snapshot) > 128 * 1024 * 1024:
        raise script_install.InstallUnsafeError("旧 BAAH 事务内容无效")
    await asyncio.to_thread(program_update.assert_idle, root)
    if marker.is_symlink() or marker.read_bytes() != snapshot:
        raise script_install.InstallUnsafeError("BAAH 事务记录已变化")
    if any(
        path.exists() or path.is_symlink()
        for path in (directory / "previous", directory / "ready")
    ):
        raise script_install.InstallUnsafeError("BAAH 仍有可恢复的旧版目录")
    archive = marker.with_name(f"baah-transaction-ack-{uuid4().hex}.json")
    marker.replace(archive)
    try:
        await program_update.confirm_current_install(root)
    except BaseException:
        if not marker.exists() and archive.exists():
            archive.replace(marker)
        raise
