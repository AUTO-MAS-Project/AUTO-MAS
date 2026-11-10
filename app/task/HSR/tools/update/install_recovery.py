#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""HSR M7A/SRA 外部更新无法回滚时的用户恢复选择。

原 journal 可能是旧文件唯一回滚依据：存在 backup 或 stage 时不允许跳过。
同一 HSR manager 已持有两份外部根目录的跨任务路径锁。
"""

import asyncio
import hashlib
import os
from pathlib import Path
from uuid import uuid4

import psutil

from app.core import Dispatcher, Publisher
from app.core.ws import protocol
from app.utils import get_logger

from .apply import journal_path, work_dir
from .engines import get_spec, read_installed_version
from .guards import check_no_process_running

logger = get_logger("HSR 更新恢复")
_TIMEOUT = 120


class HSRRecoveryUnsafeError(RuntimeError):
    """外部引擎当前安装不适合跳过恢复。"""


def _assert_idle(root: Path) -> None:
    failure = check_no_process_running(root)
    if failure:
        raise HSRRecoveryUnsafeError(failure.reason)
    # 不要把无法读取路径的相关安装器进程视为确定已退出。
    names = {"march7th assistant.exe", "sra-cli.exe", "sra-server.exe"}
    for proc in psutil.process_iter(["exe", "name"]):
        try:
            path = proc.info.get("exe")
            name = str(proc.info.get("name") or "").casefold()
            if not path and name in names:
                raise HSRRecoveryUnsafeError(
                    "无法确认外部原生脚本进程是否退出，请以管理员身份重试"
                )
        except psutil.NoSuchProcess:
            continue
        except (psutil.AccessDenied, OSError) as error:
            raise HSRRecoveryUnsafeError(
                "无法读取外部脚本进程状态，禁止跳过"
            ) from error


def confirm_snapshot(root: Path, snapshot: bytes) -> None:
    marker = journal_path(root)
    if (
        marker.is_symlink()
        or not marker.is_file()
        or len(snapshot) > 64 * 1024
        or marker.read_bytes() != snapshot
    ):
        raise HSRRecoveryUnsafeError("HSR 旧更新事务记录已经变化，拒绝旧请求")


async def ask_install_recovery(
    task_id: str,
    engine: str,
    root: Path,
    *,
    managed_name: str,
) -> tuple[str, bytes]:
    marker = journal_path(root)
    if marker.is_symlink() or not marker.is_file():
        raise HSRRecoveryUnsafeError("HSR 外部脚本恢复记录不是普通文件")
    snapshot = await asyncio.to_thread(marker.read_bytes)
    if len(snapshot) > 64 * 1024:
        raise HSRRecoveryUnsafeError("HSR 外部脚本记录异常，拒绝恢复")
    stage = work_dir(root) / "stage"
    backup = work_dir(root) / "backup"
    can_skip = not any(
        item.exists() or item.is_symlink() for item in (stage, backup)
    )
    spec = get_spec(engine)
    try:
        installed = await asyncio.to_thread(read_installed_version, spec, root)
    except Exception:
        installed = None

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
        protocol.ID_TASK_MANAGER, protocol.HSR_INSTALL_DECISION, receive
    )
    try:
        sent = await Publisher.send(
            id=protocol.ID_TASK_MANAGER,
            type=protocol.HSR_INSTALL_PROMPT,
            data={
                "requestId": request_id,
                "taskId": task_id,
                "managedName": managed_name,
                "installPath": str(root.resolve()),
                "installedVersion": installed or "未知",
                "engine": engine,
                "canSkip": can_skip,
            },
        )
        if not sent:
            raise HSRRecoveryUnsafeError(
                "HSR 安装中断且主界面未连接，请打开 MAS 界面选择恢复"
            )
        try:
            action = await asyncio.wait_for(future, timeout=_TIMEOUT)
        except TimeoutError as error:
            raise HSRRecoveryUnsafeError(
                "HSR 恢复选择超时，未修改安装状态"
            ) from error
        if action == "stop":
            raise HSRRecoveryUnsafeError("用户取消 HSR 更新恢复，原记录保留")
        if action == "skip" and not can_skip:
            raise HSRRecoveryUnsafeError(
                "HSR 更新仍有原始备份或暂存，禁止跳过回滚"
            )
        await asyncio.to_thread(confirm_snapshot, root, snapshot)
        return action, snapshot
    finally:
        unregister()
        try:
            await Publisher.send(
                id=protocol.ID_TASK_MANAGER,
                type=protocol.HSR_INSTALL_PROMPT_CLOSED,
                data={"requestId": request_id},
            )
        except Exception:
            logger.warning("HSR 更新恢复弹窗关闭通知失败")


async def skip_stale_journal(engine: str, root: Path, snapshot: bytes) -> str:
    """跳过仅适用于备份/暂存均不存在且用户已手动修复的原生安装。"""
    spec = get_spec(engine)
    stage = work_dir(root) / "stage"
    backup = work_dir(root) / "backup"
    _assert_idle(root)
    confirm_snapshot(root, snapshot)
    if any(p.exists() or p.is_symlink() for p in (stage, backup)):
        raise HSRRecoveryUnsafeError(
            "HSR 仍有更新备份或暂存目录，禁止跳过"
        )
    if not (root / spec.executable).is_file():
        raise HSRRecoveryUnsafeError(
            "HSR 外部脚本主程序缺失，必须重新安装"
        )
    try:
        version = await asyncio.to_thread(read_installed_version, spec, root)
    except Exception as error:
        raise HSRRecoveryUnsafeError(
            "HSR 外部脚本版本信息不可读，无法确认安装可用"
        ) from error
    if not version:
        raise HSRRecoveryUnsafeError(
            "HSR 外部脚本版本不可识别，不能跳过安装恢复"
        )
    _assert_idle(root)
    confirm_snapshot(root, snapshot)
    if any(p.exists() or p.is_symlink() for p in (stage, backup)):
        raise HSRRecoveryUnsafeError("HSR 安装备份在确认期间出现，拒绝跳过")

    # 应用数据中的独立恢复证据，不放在会被下一轮 apply_package 清理的工作目录。
    identity = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:24]
    store = Path.cwd() / "data" / "hsr_update" / "recovery" / identity
    store.mkdir(parents=True, exist_ok=True)
    archive = store / f"{engine}-{uuid4().hex}.json"
    temporary = archive.with_suffix(".tmp")
    try:
        temporary.write_bytes(snapshot)
        os.replace(temporary, archive)
        confirm_snapshot(root, snapshot)
        _assert_idle(root)
        journal_path(root).unlink()
    finally:
        temporary.unlink(missing_ok=True)
    logger.warning(f"用户确认 {engine} 已手动修复；旧事务记录已保留：{archive}")
    return version
