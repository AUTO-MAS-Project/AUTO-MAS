#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MAA 官方委托更新失败与 MAS 资源中断的用户确认恢复。

官方 MAA 的失败标志不能当成 MAS 的普通 JSON 随便删除；
用户确认跳过时，先校验完整的可识别安装状态，再原子归档原标志。
MAS 资源合并标志绝不允许跳过，只能重新执行带摘要校验的合并。
"""

import asyncio
from pathlib import Path
from uuid import uuid4

from app.core import Dispatcher, Publisher
from app.core.ws import protocol
from app.services import script_install
from app.utils import get_logger, process

from .resource_update import has_incomplete_resource_update, read_resource_clock
from .software_package import has_delegated_update_failure, read_pending_update
from .software_update import parse_version, read_installed_release
from .update_errors import MaaUpdateUnsafeError

logger = get_logger("MAA 更新恢复")
_PROMPT_TIMEOUT = 120
_SOFTWARE_MARKER = "pending-update-failure.txt"
_RESOURCE_MARKER = ".automas-resource-update.json"


def _markers(root: Path) -> tuple[Path, Path]:
    return root / _SOFTWARE_MARKER, root / _RESOURCE_MARKER


def _read_snapshot(root: Path) -> dict[str, bytes]:
    software, resource = _markers(root)
    result: dict[str, bytes] = {}
    for kind, marker in (("software", software), ("resource", resource)):
        if marker.is_symlink():
            raise MaaUpdateUnsafeError("MAA 恢复标记是链接，拒绝修改原安装状态")
        if not marker.exists():
            continue
        if not marker.is_file():
            raise MaaUpdateUnsafeError("MAA 恢复标记不是普通文件，拒绝修改")
        data = marker.read_bytes()
        if len(data) > 64 * 1024:
            raise MaaUpdateUnsafeError("MAA 恢复记录过大，拒绝修改")
        result[kind] = data
    return result


def confirm_snapshot(root: Path, snapshot: dict[str, bytes]) -> None:
    if not snapshot or _read_snapshot(root) != snapshot:
        raise MaaUpdateUnsafeError("MAA 恢复记录已变化，本轮选择失效")


def confirm_recovery_finished(root: Path) -> None:
    if has_delegated_update_failure(root) or has_incomplete_resource_update(root):
        raise MaaUpdateUnsafeError("MAA 安装或资源更新仍未确认完成，请先修复")
    for marker in _markers(root):
        if marker.is_symlink():
            raise MaaUpdateUnsafeError("MAA 恢复记录异常，不能继续启动")


async def ask_maa_recovery(
    task_id: str,
    root: Path,
    *,
    managed_name: str,
    takeover_enabled: bool,
) -> tuple[str, dict[str, bytes]]:
    snapshot = await asyncio.to_thread(_read_snapshot, root)
    if not snapshot:
        raise MaaUpdateUnsafeError("MAA 恢复记录已消失，请重新运行")
    try:
        release = await asyncio.to_thread(read_installed_release, root)
        current = release[0] if release else "未知"
    except Exception:
        current = "未知"
    try:
        target, package = read_pending_update(root)
    except (OSError, ValueError):
        target, package = "", ""
    can_retry = "resource" in snapshot or bool(
        package and (root / package).is_file()
    )
    can_skip = "software" in snapshot and "resource" not in snapshot

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
        protocol.ID_TASK_MANAGER, protocol.MAA_INSTALL_DECISION, receive
    )
    try:
        sent = await Publisher.send(
            id=protocol.ID_TASK_MANAGER,
            type=protocol.MAA_INSTALL_PROMPT,
            data={
                "requestId": request_id,
                "taskId": task_id,
                "managedName": managed_name,
                "installPath": str(root.resolve()),
                "takeoverEnabled": takeover_enabled,
                "installedVersion": current,
                "targetVersion": target or "未知",
                "hasResourceMarker": "resource" in snapshot,
                "canSkip": can_skip,
                "canRetry": can_retry,
            },
        )
        if not sent:
            raise MaaUpdateUnsafeError(
                "MAA 安装未确认且未连接 MAS 主界面，未修改恢复记录"
            )
        try:
            action = await asyncio.wait_for(future, timeout=_PROMPT_TIMEOUT)
        except TimeoutError as error:
            raise MaaUpdateUnsafeError(
                "MAA 安装恢复选择超时，原记录已保留，本次任务停止"
            ) from error
        if action == "stop":
            raise MaaUpdateUnsafeError(
                "用户取消 MAA 安装恢复，本次任务停止，原记录已保留"
            )
        if action == "skip" and not can_skip:
            raise MaaUpdateUnsafeError(
                "MAA 资源可能处于半更新状态，禁止跳过安装校验"
            )
        if action == "retry" and not can_retry:
            raise MaaUpdateUnsafeError(
                "MAA 安装包已不存在，无法重试，请使用官方安装器修复"
            )
        await asyncio.to_thread(confirm_snapshot, root, snapshot)
        return action, snapshot
    finally:
        unregister()
        try:
            await Publisher.send(
                id=protocol.ID_TASK_MANAGER,
                type=protocol.MAA_INSTALL_PROMPT_CLOSED,
                data={"requestId": request_id},
            )
        except Exception:
            logger.warning("发送 MAA 恢复弹窗关闭消息失败")


async def _check_current_install(root: Path) -> str:
    if await process.is_process_running(root / "MAA.Updater.exe"):
        raise MaaUpdateUnsafeError("MAA 官方更新器仍在写盘，禁止跳过")
    if not (root / "MAA.exe").is_file() or not (root / "MAA.dll").is_file():
        raise MaaUpdateUnsafeError("MAA 主程序或核心程序集缺失，不能跳过安装失败")
    release = await asyncio.to_thread(read_installed_release, root)
    if release is None or parse_version(release[0]) is None:
        raise MaaUpdateUnsafeError("MAA 版本或架构不可识别，不能跳过安装失败")
    clock = await asyncio.to_thread(read_resource_clock, root)
    if clock is None:
        raise MaaUpdateUnsafeError("MAA 资源版本不可识别，不能跳过安装失败")
    version, package = read_pending_update(root)
    if package and (root / package).is_file():
        raise MaaUpdateUnsafeError(
            "MAA 尚存在待安装的原生更新包，不能跳过，请先重试官方安装"
        )
    if has_incomplete_resource_update(root):
        raise MaaUpdateUnsafeError("MAA 资源更新尚未完成，不能跳过")
    return release[0]


async def skip_delegated_failure(root: Path, snapshot: dict[str, bytes]) -> str:
    """显式确认后归档官方失败标志，资源写入标志永远不允许跳过。"""
    if set(snapshot) != {"software"}:
        raise MaaUpdateUnsafeError("只能跳过已由用户手动修复的 MAA 本体安装")
    await asyncio.to_thread(confirm_snapshot, root, snapshot)
    version = await _check_current_install(root)
    await asyncio.to_thread(confirm_snapshot, root, snapshot)
    version = await _check_current_install(root)
    await asyncio.to_thread(confirm_snapshot, root, snapshot)
    marker, _ = _markers(root)
    directory = script_install.workspace(root)
    directory.mkdir(parents=True, exist_ok=True)
    backup = directory / f"maa-failure-ack-{uuid4().hex}.txt"
    marker.replace(backup)
    try:
        if await process.is_process_running(root / "MAA.Updater.exe"):
            raise MaaUpdateUnsafeError("MAA 更新器在确认过程中启动，不能跳过")
        confirm_recovery_finished(root)
    except BaseException:
        if not marker.exists() and backup.exists():
            backup.replace(marker)
        raise
    logger.warning(f"用户确认跳过 MAA 原生安装失败标记，旧标记已归档，当前={version}")
    return version
