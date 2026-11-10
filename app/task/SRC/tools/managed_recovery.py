# Copyright © 2025-2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""SRC 原生 Git/installer 的健康证据，恢复决策统一交给公共入口。"""

import asyncio
import re
from pathlib import Path

from app.core.script_update_recovery import InstallInspection
from app.services import script_install
from app.services.script_install_backup import ManagedInstallBackup
from app.utils import io as io_utils

from . import program_update


class SRCInstallAdapter:
    def __init__(
        self,
        root: Path,
        *,
        prepared: program_update.PreparedUpdate | None = None,
    ) -> None:
        self.root = root
        self.prepared = prepared

    async def ensure_idle(self) -> None:
        await asyncio.to_thread(
            program_update.assert_idle, self.root, allow_background_adb=True
        )

    async def inspect(self) -> InstallInspection:
        await self.ensure_idle()
        marker = script_install.workspace(self.root) / "src-install.json"
        if marker.is_symlink():
            raise script_install.InstallUnsafeError("SRC 更新标记为符号链接")
        pending = marker.exists()
        await asyncio.to_thread(program_update.recover_deploy, self.root)
        deploy = await asyncio.to_thread(program_update.read_deploy, self.root)
        git = program_update.git_executable(self.root, deploy)
        commit = await program_update.command(git, "rev-parse", "HEAD", cwd=self.root)
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise script_install.InstallUnsafeError("SRC 当前 Git HEAD 不可识别")
        expected = self.prepared.target_commit if self.prepared else None
        previous = self.prepared.base_commit if self.prepared else None
        if previous is None:
            record = ManagedInstallBackup(
                self.root, script_id="", script_type="SRC"
            ).read()
            previous = record.get("version") if record else None
            if previous is None and not pending:
                previous = commit
        completed = (
            script_install.workspace(self.root) / "src-native-install-complete.json"
        )
        if completed.is_symlink():
            raise script_install.InstallUnsafeError("SRC 原生安装完成记录不可为链接")
        completed_target = None
        if completed.is_file():
            try:
                record = io_utils.read_dict_file(completed)
                token = record.get("target")
                if (
                    record.get("root") == str(self.root.resolve())
                    and isinstance(token, str)
                    and re.fullmatch(r"[0-9a-f]{40}", token)
                ):
                    completed_target = token
            except (OSError, ValueError, KeyError, TypeError):
                pass
        if pending:
            target = program_update.validate_install_marker(
                self.root, marker.read_bytes()
            )
            if expected is None:
                expected = target
        elif expected is None:
            expected = completed_target
        healthy = (self.root / "src.exe").is_file() and (
            self.root / "installer.py"
        ).is_file()
        if healthy:
            try:
                python = self.root / str(
                    deploy.get("PythonExecutable") or "./toolkit/python.exe"
                )
                if not python.is_file():
                    healthy = False
                else:
                    await program_update.command(
                        str(python.resolve()), "-m", "pip", "check", cwd=self.root
                    )
            except (OSError, ValueError, RuntimeError):
                healthy = False
        await self.ensure_idle()
        return InstallInspection(
            pending=pending,
            healthy=healthy,
            installed_version=commit,
            target_version=expected,
            # pending 不能仅靠 Git 目标 + pip check 推断原生 installer 已成功。
            # 仅接受 installer 在 Git 验证之后写下的完成记录。
            updated_confirmed=bool(
                healthy
                and not pending
                and completed_target == expected == commit
                and (previous is None or commit != previous)
            ),
            previous_confirmed=bool(
                healthy and not pending and previous and commit == previous
            ),
        )

    async def acknowledge(self) -> None:
        marker = script_install.workspace(self.root) / "src-install.json"
        if not marker.exists():
            return
        snapshot = marker.read_bytes()
        await program_update.skip_unconfirmed_install(self.root, snapshot)

    async def install(self) -> None:
        if self.prepared is None:
            marker = script_install.workspace(self.root) / "src-install.json"
            snapshot = marker.read_bytes() if marker.exists() else None
            await program_update.update_before_run(
                self.root, recovery_snapshot=snapshot
            )
            return
        try:
            await program_update.apply_update(self.root, self.prepared)
        finally:
            # 原生安装器是否停写由公共恢复入口和 SRC 安装锁最终确认。
            # Git 对象删除仅在安全的进程收尾之后执行。
            await self.ensure_idle()
            program_update.remove_cached_git_objects(self.prepared.objects)

    async def after_rollback(self) -> None:
        await self.ensure_idle()
        completed = (
            script_install.workspace(self.root) / "src-native-install-complete.json"
        )
        if completed.is_symlink():
            raise script_install.InstallUnsafeError("SRC 原生安装完成记录路径异常")
        completed.unlink(missing_ok=True)
        await asyncio.to_thread(program_update.recover_deploy, self.root)
        marker = script_install.workspace(self.root) / "src-install.json"
        if marker.is_symlink():
            raise script_install.InstallUnsafeError("SRC 回退标记异常")
        if marker.exists():
            # 只允许公共备份证明的本次 MAS 安装清理其自有标记。
            record = ManagedInstallBackup(
                self.root, script_id="", script_type="SRC"
            ).read()
            if record is None:
                raise script_install.InstallUnsafeError("缺失 SRC 公共备份所有权记录")
            marker.unlink()
