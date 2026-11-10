#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""BAAH 安装事务异常时的用户确认恢复；任何现存备份/暂存目录禁止跳过。"""

import asyncio
from pathlib import Path
from uuid import uuid4

from app.core import Dispatcher, Publisher
from app.core.ws import protocol
from app.services import script_install
from app.utils import get_logger

from . import program_update

logger = get_logger("BAAH 安装恢复")
_TIMEOUT = 120


def _state(root: Path) -> tuple[Path, Path, Path]:
    directory = script_install.workspace(root)
    return (
        directory / "transaction.json",
        directory / "previous",
        directory / "ready",
    )


def confirm_snapshot(root: Path, snapshot: bytes) -> None:
    marker, _, _ = _state(root)
    if (
        marker.is_symlink()
        or not marker.is_file()
        or len(snapshot) > 64 * 1024
        or marker.read_bytes() != snapshot
    ):
        raise script_install.InstallUnsafeError("BAAH 安装恢复记录已变化，拒绝旧选择")


async def ask_install_recovery(
    task_id: str,
    root: Path,
    *,
    managed_name: str,
    takeover_enabled: bool,
) -> tuple[str, bytes]:
    marker, previous, ready = _state(root)
    if marker.is_symlink() or not marker.is_file():
        raise script_install.InstallUnsafeError("BAAH 安装事务标记异常，请保留现场")
    snapshot = await asyncio.to_thread(marker.read_bytes)
    if len(snapshot) > 64 * 1024:
        raise script_install.InstallUnsafeError("BAAH 事务标记过大，拒绝修改")
    can_skip = not (
        previous.exists() or previous.is_symlink() or ready.exists() or ready.is_symlink()
    )
    try:
        current = str(await asyncio.to_thread(program_update.read_version, root))
    except Exception:
        current = "未知"

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
        protocol.ID_TASK_MANAGER, protocol.BAAH_INSTALL_DECISION, receive
    )
    try:
        sent = await Publisher.send(
            id=protocol.ID_TASK_MANAGER,
            type=protocol.BAAH_INSTALL_PROMPT,
            data={
                "requestId": request_id,
                "taskId": task_id,
                "managedName": managed_name,
                "installPath": str(root.resolve()),
                "installedVersion": current,
                "takeoverEnabled": takeover_enabled,
                "canSkip": can_skip,
            },
        )
        if not sent:
            raise script_install.InstallUnsafeError(
                "BAAH 上次安装未完成且主界面未连接，请打开 MAS 界面选择恢复"
            )
        try:
            action = await asyncio.wait_for(future, timeout=_TIMEOUT)
        except TimeoutError as error:
            raise script_install.InstallUnsafeError(
                "BAAH 恢复选择超时，已保留原安装事务"
            ) from error
        if action == "stop":
            raise script_install.InstallUnsafeError(
                "用户取消 BAAH 安装恢复，原安装事务已保留"
            )
        if action == "skip" and not can_skip:
            raise script_install.InstallUnsafeError(
                "BAAH 仍有安装备份或暂存，必须先完成自动回滚，不能直接跳过"
            )
        await asyncio.to_thread(confirm_snapshot, root, snapshot)
        return action, snapshot
    finally:
        unregister()
        try:
            await Publisher.send(
                id=protocol.ID_TASK_MANAGER,
                type=protocol.BAAH_INSTALL_PROMPT_CLOSED,
                data={"requestId": request_id},
            )
        except Exception:
            logger.warning("BAAH 安装恢复弹窗关闭通知失败")


async def skip_stale_transaction(root: Path, snapshot: bytes) -> str:
    """仅在没有待切换目录、原本体可验证时，归档失效 journal 继续运行。"""
    marker, previous, ready = _state(root)
    await asyncio.to_thread(program_update.assert_idle, root)
    confirm_snapshot(root, snapshot)
    if any(path.exists() or path.is_symlink() for path in (previous, ready)):
        raise script_install.InstallUnsafeError(
            "BAAH 仍保留安装备份或暂存目录，禁止跳过事务恢复"
        )
    if await asyncio.to_thread(
        script_install.read_pe_architecture, root / "BAAH.exe"
    ) != "x86_64":
        raise script_install.InstallUnsafeError(
            "BAAH 主程序架构不可识别，无法确认手动修复已完成"
        )
    try:
        version = await asyncio.to_thread(program_update.read_version, root)
    except Exception as error:
        raise script_install.InstallUnsafeError(
            "BAAH 程序版本不可识别，不能跳过安装事务"
        ) from error
    receipt = script_install.record_path(root, "installed.json")
    if receipt.exists() and not await script_install.run_worker(
        script_install.verify_installed_files, root
    ):
        raise script_install.InstallUnsafeError(
            "BAAH 文件与上次安装回执不符，不能跳过，请运行官方安装修复"
        )
    await asyncio.to_thread(program_update.assert_idle, root)
    confirm_snapshot(root, snapshot)
    if any(path.exists() or path.is_symlink() for path in (previous, ready)):
        raise script_install.InstallUnsafeError("BAAH 事务在恢复期间发生变化")
    backup = marker.with_name(f"baah-transaction-ack-{uuid4().hex}.json")
    marker.replace(backup)
    try:
        await program_update.confirm_current_install(root)
    except BaseException:
        if not marker.exists() and backup.exists():
            backup.replace(marker)
        raise
    logger.warning(f"用户确认 BAAH 手动修复完成，原事务已归档，当前版本={version}")
    return str(version)
