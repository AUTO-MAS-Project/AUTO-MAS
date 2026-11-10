# Copyright © 2025-2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""BAAH 官方完整包恢复适配器；公共入口负责恢复策略和任务末尾报告。"""

import asyncio
from pathlib import Path

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
        if healthy and self.recovery_receipt is not None:
            # 损坏安装只有真正完成新安装、旧记录已被更新后才算恢复。
            receipt = script_install.record_path(self.root, "installed.json")
            if receipt.read_bytes() == self.recovery_receipt:
                healthy = False
        return InstallInspection(
            pending=pending or (not healthy and self.recovery_receipt is not None),
            healthy=healthy,
            installed_version=str(version) if version else None,
            target_version=str(target) if target else None,
            updated_confirmed=bool(
                healthy
                and (
                    (target is not None and version == target)
                    or (previous is not None and version is not None and version > previous)
                )
            ),
            previous_confirmed=bool(
                healthy
                and not pending
                and previous is not None
                and version == previous
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
