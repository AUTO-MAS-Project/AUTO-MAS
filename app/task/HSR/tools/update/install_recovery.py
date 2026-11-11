# Copyright © 2025-2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""M7A / SRA 原生安装事务的健康证据；不再询问用户，也不删除原生 journal。

上轮事务的恢复动作和任务末尾异常汇总均由 #1916 公共入口决定。
"""

import asyncio
from pathlib import Path

import psutil

from app.core.script_update_recovery import InstallInspection
from app.services import script_install

from .apply import journal_path, work_dir
from .engines import get_spec, read_installed_version
from .guards import check_no_process_running


def assert_idle(root: Path) -> None:
    failure = check_no_process_running(root)
    if failure:
        raise script_install.InstallUnsafeError(failure.reason)
    names = {
        "march7th assistant.exe",
        "sra.exe",
        "sra-cli.exe",
        "sra-server.exe",
    }
    for process in psutil.process_iter(["exe", "name"]):
        try:
            path = process.info.get("exe")
            name = str(process.info.get("name") or "").casefold()
            if not path and name in names:
                raise script_install.InstallUnsafeError(
                    "无法确认原生脚本进程是否退出，拒绝修改安装"
                )
        except psutil.NoSuchProcess:
            continue
        except (psutil.AccessDenied, OSError) as error:
            raise script_install.InstallUnsafeError(
                "无法读取原生脚本进程状态，拒绝恢复"
            ) from error


async def inspect_installation(engine: str, root: Path) -> InstallInspection:
    """可证明当前原生安装健康时才允许公共入口放行。版本文本不是 EXE 校验。"""
    marker = journal_path(root)
    directory = work_dir(root)
    if marker.is_symlink() or directory.is_symlink():
        raise script_install.InstallUnsafeError("原生恢复事务路径是符号链接")
    await asyncio.to_thread(assert_idle, root)
    spec = get_spec(engine)
    executable = root / spec.executable
    healthy = executable.is_file()
    if healthy and engine == "M7A":
        try:
            await asyncio.to_thread(script_install.read_pe_architecture, executable)
        except (OSError, ValueError):
            healthy = False
    try:
        version = (
            await asyncio.to_thread(read_installed_version, spec, root)
            if healthy
            else None
        )
    except (OSError, ValueError):
        version = None
    healthy = healthy and bool(version)
    return InstallInspection(
        pending=marker.exists(),
        healthy=healthy,
        installed_version=version,
        # 原生更新 journal 中断不代表新版安装成功，绝不自动丢弃 journal。
        updated_confirmed=False,
        previous_confirmed=healthy and not marker.exists(),
    )
