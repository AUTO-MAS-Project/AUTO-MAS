# Copyright © 2025-2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""奇想盒安装健康证据与原生命令适配器；恢复决策交由公共入口。"""

import asyncio
from pathlib import Path

from packaging.version import Version

from app.core.script_update_recovery import DownloadRetryFailed, InstallInspection
from app.services.script_install_backup import ManagedInstallBackup
from app.services import script_install

from . import update
from .launcher import find_upstream_pids
from .upstream import WheelAssetsConfigSurface


class WhimboxInstallAdapter:
    def __init__(
        self,
        root: Path,
        *,
        target: Version | None = None,
        previous: Version | None = None,
        candidate: update.PreparedUpdate | None = None,
    ) -> None:
        self.root = root
        self.target = target
        self.previous = previous
        self.candidate = candidate

    async def ensure_idle(self) -> None:
        script_install.assert_no_pending_process(self.root)
        if await asyncio.to_thread(find_upstream_pids, self.root):
            raise script_install.InstallUnsafeError(
                "奇想盒应用或后端仍在运行，不允许更新、清理备份或回退"
            )

    async def inspect(self) -> InstallInspection:
        await self.ensure_idle()
        marker = update.pending_marker(self.root)
        if marker.is_symlink():
            raise script_install.InstallUnsafeError("奇想盒安装标记是符号链接")
        pending = marker.exists()
        target = self.target
        previous = self.previous
        if not pending and previous is None:
            state = ManagedInstallBackup(
                self.root, script_id="", script_type="Whimbox"
            ).read()
            if state and state.get("version"):
                previous = Version(state["version"])
        if pending:
            try:
                marked = Version(marker.read_text(encoding="utf-8").strip())
            except (OSError, ValueError) as error:
                raise script_install.InstallUnsafeError(
                    "奇想盒遗留安装记录不可识别，保留现场"
                ) from error
            if target is None:
                target = marked
        version = None
        healthy = False
        if WheelAssetsConfigSurface(self.root).check_install() is None:
            try:
                version = await update.installed_version(self.root)
                await update.run_python(self.root, "-m", "pip", "check")
                await update.run_python(
                    self.root,
                    "-c",
                    "import importlib.util as u; assert u.find_spec('whimbox.main')",
                )
                await self.ensure_idle()
                healthy = True
            except (OSError, ValueError, RuntimeError):
                healthy = False
        return InstallInspection(
            pending=pending,
            healthy=healthy,
            installed_version=str(version) if version else None,
            target_version=str(target) if target else None,
            updated_confirmed=bool(
                healthy and version is not None
                and (
                    (target is not None and version >= target)
                    or (previous is not None and version > previous)
                )
            ),
            previous_confirmed=bool(
                healthy and not pending and previous is not None
                and version == previous
            ),
        )

    async def acknowledge(self) -> None:
        marker = update.pending_marker(self.root)
        if marker.is_symlink() or not marker.is_file():
            raise script_install.InstallUnsafeError("奇想盒安装确认记录已变化")
        await update.skip_pending_installation(self.root, marker.read_bytes())

    async def install(self) -> None:
        if self.candidate is not None:
            await update.apply_update(self.root, self.candidate)
            self.candidate = None
        else:
            try:
                candidate = await update.prepare_update(self.root)
            except (TimeoutError, ConnectionError, OSError) as error:
                raise DownloadRetryFailed(
                    source="GitHub",
                    reason=f"奇想盒恢复下载失败（{type(error).__name__}）",
                ) from error
            try:
                await update.apply_update(self.root, candidate)
            finally:
                update.discard_update(candidate)

    async def after_rollback(self) -> None:
        # 公共层恢复的是完整的安装前目录；正常快照不包含本次安装标记。
        await self.ensure_idle()
        if update.pending_marker(self.root).exists():
            raise script_install.InstallUnsafeError(
                "奇想盒回退后仍有未确认原生安装标记，不能启动"
            )
