# Copyright © 2025-2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""BAAH 官方完整包恢复适配器；公共入口负责恢复策略和任务末尾报告。"""

import asyncio
import base64
import hashlib
import os
from pathlib import Path
from uuid import uuid4

from packaging.version import Version

from app.core.script_update_recovery import InstallInspection
from app.services import script_install
from app.services.script_install_backup import ManagedInstallBackup
from app.utils import io as io_utils

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
        # 只读健康检查允许 BAAH 自带 adb server 持续运行。
        await asyncio.to_thread(
            program_update.assert_idle, self.root, allow_background_adb=True
        )
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
        await asyncio.to_thread(restore_original_receipts, self.root)
        # 回退前的原 MAS 收据已同步恢复，仍要重新验证目录哈希。
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


_RECEIPT_NAMES = ("installed.json", "baah-version.json")
_RECEIPT_BACKUP = "baah-managed-receipts.json"


def receipt_backup_path(root: Path) -> Path:
    return script_install.workspace(root) / _RECEIPT_BACKUP


def _read_receipt_backup(root: Path) -> dict:
    marker = receipt_backup_path(root)
    if marker.is_symlink() or not marker.is_file():
        raise script_install.InstallUnsafeError("BAAH 更新前外置收据备份缺失或被替换")
    data = io_utils.read_dict_file(marker)
    if (
        data.get("root") != str(root.resolve())
        or data.get("schema") != 1
        or not isinstance(data.get("receipts"), dict)
        or set(data["receipts"]) != set(_RECEIPT_NAMES)
    ):
        raise script_install.InstallUnsafeError("BAAH 外置收据备份身份不匹配")
    return data["receipts"]


def snapshot_original_receipts(root: Path) -> None:
    """必须在公共备份创建/任何原生安装写盘之前调用，且仅允许单次建立。"""
    marker = receipt_backup_path(root)
    if marker.exists() or marker.is_symlink():
        raise script_install.InstallUnsafeError("BAAH 尚有未结算的外置收据备份")
    receipts = {}
    for name in _RECEIPT_NAMES:
        path = script_install.record_path(root, name)
        if path.is_symlink():
            raise script_install.InstallUnsafeError("BAAH 收据目录包含链接")
        content = path.read_bytes() if path.is_file() else None
        if content is not None and len(content) > 32 * 1024 * 1024:
            raise script_install.InstallUnsafeError("BAAH 原安装收据异常大")
        receipts[name] = (
            None
            if content is None
            else {
                "data": base64.b64encode(content).decode("ascii"),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    marker.parent.mkdir(parents=True, exist_ok=True)
    io_utils.write_file(
        marker,
        {
            "schema": 1,
            "root": str(root.resolve()),
            "receipts": receipts,
        },
    )


def restore_original_receipts(root: Path) -> None:
    """公共备份恢复原程序目录之后，再恢复 MAS 自有的两份外置收据。"""
    receipts = _read_receipt_backup(root)
    for name in _RECEIPT_NAMES:
        path = script_install.record_path(root, name)
        if path.is_symlink():
            raise script_install.InstallUnsafeError("BAAH 收据目标是符号链接")
        entry = receipts[name]
        if entry is None:
            path.unlink(missing_ok=True)
            continue
        try:
            content = base64.b64decode(entry["data"], validate=True)
            if hashlib.sha256(content).hexdigest() != entry["sha256"]:
                raise ValueError("digest mismatch")
        except (KeyError, TypeError, ValueError) as error:
            raise script_install.InstallUnsafeError(
                "BAAH 更新前原始收据校验失败，拒绝回滚"
            ) from error
        path.parent.mkdir(parents=True, exist_ok=True)
        staged = path.with_name(f"{path.name}.restore-{os.getpid()}.tmp")
        if staged.is_symlink():
            raise script_install.InstallUnsafeError("BAAH 收据暂存路径不安全")
        staged.write_bytes(content)
        os.replace(staged, path)


def cleanup_original_receipts(root: Path) -> None:
    marker = receipt_backup_path(root)
    if marker.is_symlink():
        raise script_install.InstallUnsafeError("BAAH 备份文件被重定向")
    if marker.exists():
        _read_receipt_backup(root)
        marker.unlink()
