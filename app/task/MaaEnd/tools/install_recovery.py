#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MaaEnd 更新目录切换的未确认事务恢复。

先调用通用 recover_install；只有它无法确认且存在实际 journal 才询问。
任何仍有原始备份/ready 暂存的目录均禁止跳过；不触碰 MXU 的内部 pending。
"""

import asyncio
from pathlib import Path
from uuid import uuid4

from app.core import Dispatcher, Publisher
from app.core.ws import protocol
from app.services import script_install
from app.utils import get_logger

from . import script_update

logger = get_logger("MaaEnd 安装恢复")
_TIMEOUT = 120


def _state(root: Path) -> tuple[Path, Path, Path]:
    directory = script_install.workspace(root)
    return (
        directory / "transaction.json",
        directory / "previous",
        directory / "ready",
    )


def confirm_snapshot(root: Path, snapshot: bytes) -> None:
    journal, _, _ = _state(root)
    if (
        journal.is_symlink()
        or not journal.is_file()
        or len(snapshot) > 64 * 1024
        or journal.read_bytes() != snapshot
    ):
        raise script_install.InstallUnsafeError(
            "MaaEnd 安装记录在确认期间发生变化，拒绝旧请求"
        )


async def ask_install_recovery(
    task_id: str,
    root: Path,
    *,
    managed_name: str,
    takeover_enabled: bool,
) -> tuple[str, bytes]:
    journal, previous, ready = _state(root)
    if journal.is_symlink() or not journal.is_file():
        raise script_install.InstallUnsafeError("MaaEnd 事务记录异常，禁止恢复")
    snapshot = await asyncio.to_thread(journal.read_bytes)
    if len(snapshot) > 64 * 1024:
        raise script_install.InstallUnsafeError("MaaEnd 事务记录过大，禁止自动恢复")
    can_skip = not (
        previous.exists()
        or previous.is_symlink()
        or ready.exists()
        or ready.is_symlink()
    )
    try:
        installed = str((await asyncio.to_thread(script_update.read_install, root))[0])
    except Exception:
        installed = "未知"

    request_id = uuid4().hex
    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    def receive(envelope) -> None:
        data = envelope.data
        if (
            data.get("requestId") == request_id
            and data.get("taskId") == task_id
            and data.get("action") in ("retry", "skip", "stop")
            and not future.done()
        ):
            future.set_result(data["action"])

    unregister = Dispatcher.register(
        protocol.ID_TASK_MANAGER, protocol.MAAEND_INSTALL_DECISION, receive
    )
    try:
        sent = await Publisher.send(
            id=protocol.ID_TASK_MANAGER,
            type=protocol.MAAEND_INSTALL_PROMPT,
            data={
                "requestId": request_id,
                "taskId": task_id,
                "managedName": managed_name,
                "installPath": str(root.resolve()),
                "installedVersion": installed,
                "takeoverEnabled": takeover_enabled,
                "canSkip": can_skip,
            },
        )
        if not sent:
            raise script_install.InstallUnsafeError(
                "MaaEnd 未完成安装事务尚未恢复，主界面未连接"
            )
        try:
            action = await asyncio.wait_for(future, timeout=_TIMEOUT)
        except TimeoutError as error:
            raise script_install.InstallUnsafeError(
                "MaaEnd 恢复确认超时，已保留原安装事务"
            ) from error
        if action == "stop":
            raise script_install.InstallUnsafeError(
                "用户取消 MaaEnd 恢复，本轮已停止，保留安装事务"
            )
        if action == "skip" and not can_skip:
            raise script_install.InstallUnsafeError(
                "MaaEnd 仍有原始备份或暂存，不能跳过未完成的安装"
            )
        await asyncio.to_thread(confirm_snapshot, root, snapshot)
        return action, snapshot
    finally:
        unregister()
        try:
            await Publisher.send(
                id=protocol.ID_TASK_MANAGER,
                type=protocol.MAAEND_INSTALL_PROMPT_CLOSED,
                data={"requestId": request_id},
            )
        except Exception:
            logger.warning("MaaEnd 安装恢复弹窗关闭通知失败")


async def skip_stale_transaction(root: Path, snapshot: bytes) -> str:
    """只归档没有备份/待切换目录的旧 journal；核对原安装与版本回执。"""
    marker, previous, ready = _state(root)
    await asyncio.to_thread(script_update.assert_idle, root)
    confirm_snapshot(root, snapshot)
    if any(p.exists() or p.is_symlink() for p in (previous, ready)):
        raise script_install.InstallUnsafeError(
            "MaaEnd 有旧安装备份或 ready 暂存目录，禁止跳过"
        )
    try:
        version, arch = await asyncio.to_thread(script_update.read_install, root)
        if arch not in ("x86_64", "aarch64"):
            raise ValueError("MaaEnd 架构不可识别")
    except (ValueError, OSError) as error:
        raise script_install.InstallUnsafeError(
            "MaaEnd 当前主程序、资源或版本不完整，无法确认手动恢复"
        ) from error
    receipt = script_install.record_path(root, "installed.json")
    if receipt.exists() and not await script_install.run_worker(
        script_install.verify_installed_files, root
    ):
        raise script_install.InstallUnsafeError(
            "MaaEnd 当前文件与 MAS 校验回执不符，不允许跳过；请手动修复"
        )
    await asyncio.to_thread(script_update.assert_idle, root)
    confirm_snapshot(root, snapshot)
    if any(p.exists() or p.is_symlink() for p in (previous, ready)):
        raise script_install.InstallUnsafeError(
            "MaaEnd 原始备份或暂存目录在恢复过程中发生变化"
        )
    backup = marker.with_name(f"maaend-transaction-ack-{uuid4().hex}.json")
    marker.replace(backup)
    try:
        await script_update.confirm_current_install(root)
    except BaseException:
        if not marker.exists() and backup.exists():
            backup.replace(marker)
        raise
    logger.warning(f"用户确认 MaaEnd 已手动修复并跳过遗留安装记录：{version}")
    return str(version)
