# Copyright © 2025-2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""MAA 官方更新/资源合并健康证据，恢复动作仅由 #1916 公共入口编排。"""

import asyncio
from pathlib import Path

from app.core.script_update_recovery import InstallInspection
from app.services import script_install
from app.utils import process

from .resource_update import (
    has_incomplete_resource_update,
    read_resource_clock,
    verify_resource_recovery_marker,
)
from .software_package import read_pending_update
from .software_update import (
    _read_pe_machine,
    compare_versions,
    parse_version,
    read_installed_release,
)
from .update_errors import MaaUpdateUnsafeError

_SOFTWARE_MARKER = "pending-update-failure.txt"
_RESOURCE_MARKER = ".automas-resource-update.json"


class MAAInstallAdapter:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.previous_target: str | None = None

    async def ensure_idle(self) -> None:
        if await process.is_process_running(self.root / "MAA.Updater.exe"):
            raise MaaUpdateUnsafeError("MAA 官方更新器仍在运行，不能修改安装状态")

    async def inspect(self) -> InstallInspection:
        await self.ensure_idle()
        software = self.root / _SOFTWARE_MARKER
        resource = self.root / _RESOURCE_MARKER
        if software.is_symlink() or resource.is_symlink():
            raise MaaUpdateUnsafeError("MAA 失败/资源标记包含符号链接")
        software_pending = software.exists()
        resource_pending = resource.exists()
        pending = software_pending or resource_pending
        try:
            release = await asyncio.to_thread(read_installed_release, self.root)
            exe_ok = await asyncio.to_thread(_read_pe_machine, self.root / "MAA.exe")
            clock = await asyncio.to_thread(read_resource_clock, self.root)
        except (OSError, ValueError):
            release, exe_ok, clock = None, None, None
        version = release[0] if release else None
        healthy = bool(version and exe_ok and clock is not None)
        target = self.previous_target
        package = ""
        if software_pending:
            try:
                target, package = await asyncio.to_thread(
                    read_pending_update, self.root
                )
            except (OSError, ValueError):
                target, package = "", ""
        # 上游更新失败标记不能凭借“旧程序还可启动”直接删除；
        # 必须能证明当前发布版已达到原生目标，且原安装包不再待执行。
        updated = False
        if software_pending and not resource_pending and healthy and target:
            try:
                parsed_version = parse_version(version)
                parsed_target = parse_version(target)
                updated = bool(
                    parsed_version is not None
                    and parsed_target is not None
                    and compare_versions(parsed_version, parsed_target) >= 0
                    and not (package and (self.root / package).is_file())
                )
            except (TypeError, ValueError):
                updated = False
        return InstallInspection(
            pending=pending,
            healthy=healthy and not resource_pending,
            installed_version=version,
            target_version=target,
            updated_confirmed=updated,
            previous_confirmed=healthy and not pending,
        )

    async def acknowledge(self) -> None:
        """公共层已经通过更新版本判断，再复核身份并归档原生失败记录。"""
        software = self.root / _SOFTWARE_MARKER
        resource = self.root / _RESOURCE_MARKER
        if resource.exists() or resource.is_symlink():
            raise MaaUpdateUnsafeError("MAA 资源处于半更新，禁止直接清除标记")
        if software.is_symlink() or not software.is_file():
            raise MaaUpdateUnsafeError("MAA 原生失败标记已变化")
        from .install_recovery import skip_delegated_failure

        await skip_delegated_failure(self.root, {"software": software.read_bytes()})

    async def reinstall(self, install_software, install_resources) -> None:
        """仅自动修复 MAS 自有资源半更新；原生本体失败交官方恢复。"""
        software = self.root / _SOFTWARE_MARKER
        resource = self.root / _RESOURCE_MARKER
        if software.exists() or software.is_symlink():
            # 官方 MAA 启动时首先消费旧失败状态，并清空 UpdatePackage。
            # 配置中重新写入包路径不等于调用其私有 RegisterPendingUpdatePackage；
            # 直接拉起 MAA.exe 只会空转，绝不能误报自动恢复成功。
            await self.ensure_idle()
            raise MaaUpdateUnsafeError(
                "MAA 官方本体更新已报告失败：当前版本的官方启动流程会"
                "清除待安装包登记，MAS 无法直接进行无人值守重试。"
                "请在 MAA 官方界面使用更新修复或重新登记完整包；"
                "完成后再启动 MAS，原失败标记和更新包已保留。"
            )
        if resource.exists():
            snapshot = resource.read_bytes()
            await asyncio.to_thread(
                verify_resource_recovery_marker, self.root, snapshot
            )
            await install_resources()
        if has_incomplete_resource_update(self.root):
            raise MaaUpdateUnsafeError("MAA 资源恢复后仍有未完成写入标记")
