# Copyright © 2025-2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""MaaEnd 安装状态与修复适配器。公共 #1916 负责决定恢复策略。"""

import asyncio
from pathlib import Path
from uuid import uuid4

from app.core.script_update_recovery import InstallInspection
from app.services import script_install

from . import script_update

_MAX_TRANSACTION_BYTES = 128 * 1024 * 1024


class MaaEndInstallAdapter:
    def __init__(self, root: Path, config, *, takeover_enabled: bool) -> None:
        self.root = root
        self.config = config
        self.takeover_enabled = takeover_enabled

    async def ensure_idle(self) -> None:
        await asyncio.to_thread(script_update.assert_idle, self.root)

    async def inspect(self) -> InstallInspection:
        await self.ensure_idle()
        directory = script_install.workspace(self.root)
        marker = directory / "transaction.json"
        previous = directory / "previous"
        ready = directory / "ready"
        if any(p.is_symlink() for p in (directory, marker, previous, ready)):
            raise script_install.InstallUnsafeError("MaaEnd 原生安装事务路径不安全")
        pending = marker.exists()
        if previous.exists() or ready.exists():
            return InstallInspection(pending=True, healthy=False)
        try:
            version, architecture = await asyncio.to_thread(
                script_update.read_install, self.root
            )
            healthy = architecture in {"x86_64", "aarch64"}
            receipt = script_install.record_path(self.root, "installed.json")
            if healthy and self.takeover_enabled and receipt.is_file():
                healthy = await script_install.run_worker(
                    script_install.verify_installed_files, self.root
                )
        except (OSError, ValueError, script_install.InstallUnsafeError):
            return InstallInspection(pending=pending, healthy=False)
        return InstallInspection(
            pending=pending,
            healthy=healthy,
            installed_version=str(version),
            # 原安装记录存在不等于新版本已完成，必须再次检查回执。
            updated_confirmed=healthy and pending,
            previous_confirmed=healthy and not pending,
        )

    async def acknowledge(self) -> None:
        """只归档无原版备份、版本和安装清单仍完整的遗留 journal。"""
        state = await self.inspect()
        if not (state.pending and state.healthy and state.updated_confirmed):
            raise script_install.InstallUnsafeError(
                "MaaEnd 遗留事务尚未完成，不允许清除记录"
            )
        directory = script_install.workspace(self.root)
        marker = directory / "transaction.json"
        snapshot = marker.read_bytes()
        if not snapshot or len(snapshot) > _MAX_TRANSACTION_BYTES:
            raise script_install.InstallUnsafeError("原生事务标记无效")
        await self.ensure_idle()
        if marker.is_symlink() or marker.read_bytes() != snapshot:
            raise script_install.InstallUnsafeError("事务内容在恢复时发生变化")
        if any(
            p.exists() or p.is_symlink()
            for p in (directory / "previous", directory / "ready")
        ):
            raise script_install.InstallUnsafeError("仍有可恢复的安装目录")
        archive = directory / f"maaend-transaction-ack-{uuid4().hex}.json"
        marker.replace(archive)
        try:
            await script_update.confirm_current_install(
                self.root, verify_receipt=self.takeover_enabled
            )
        except BaseException:
            if archive.exists() and not marker.exists():
                archive.replace(marker)
            raise

    async def recover_native(self) -> None:
        """仅恢复原生目录事务；安装健康验证留给后续公共恢复入口。"""
        await script_install.run_worker(
            script_install.recover_install,
            self.root,
            lambda: script_update.assert_idle(self.root),
        )

    async def retry_native(self) -> None:
        await self.recover_native()
        await script_update.confirm_current_install(
            self.root, verify_receipt=self.takeover_enabled
        )

    async def inspect_repair(self) -> InstallInspection:
        """将无 journal、但有可信身份的损坏安装表达为公共待恢复态。"""
        state = await self.inspect()
        if state.pending or state.healthy:
            return state
        return InstallInspection(
            pending=True,
            healthy=False,
            installed_version=state.installed_version,
            previous_confirmed=False,
            updated_confirmed=False,
        )

    async def repair_program(self) -> None:
        identity = script_install.record_path(self.root, "program-identity.json")
        if identity.is_symlink() or not identity.is_file():
            raise script_install.InstallUnsafeError(
                "当前 MaaEnd 安装损坏且缺少可信架构身份，不能自动重装"
            )
        snapshot = identity.read_bytes()
        script_update.verify_repair_identity(self.root, snapshot)
        # 可识别的 MXU 原生升级不应被当作损坏 EXE，更不能降低版本。
        # 仅在原生安装身份本身无法读取时走带身份绑定的强制修复；
        # 旧 MAS 回执失效时保留正常更新器的精确版本官方包复核。
        try:
            await asyncio.to_thread(script_update.read_install, self.root)
        except (OSError, ValueError):
            await script_update.update_before_run(
                self.root, self.config, recovery_identity=snapshot
            )
        else:
            await script_update.update_before_run(self.root, self.config)
        await script_update.confirm_current_install(self.root)
