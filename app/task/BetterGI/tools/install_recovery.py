#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""BetterGI 未确认本体安装的交互恢复。

等待选择时持有专项原有安装锁；没有前端、超时、取消或连接丢失都不默认放行。
本模块只收集一次显式决定，实际清除标记及重新安装仍由专项执行并复核。
"""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.core import Dispatcher, Publisher
from app.core.ws import protocol
from app.services import script_install
from app.utils import get_logger

from . import program_update

logger = get_logger("BetterGI 安装恢复")
_PROMPT_TIMEOUT_SECONDS = 120


async def ask_install_recovery(
    task_id: str,
    root: Path,
    *,
    channel: str,
    takeover_enabled: bool,
) -> tuple[str, bytes]:
    """返回 (retry/skip, 原标记字节)，让后续操作对同一份安装记录做乐观校验。"""
    marker = script_install.workspace(root) / "bgi-install.json"
    if marker.is_symlink() or not marker.is_file():
        raise script_install.InstallUnsafeError(
            "BetterGI 安装恢复记录不是普通文件，请保留现场"
        )
    snapshot = await asyncio.to_thread(marker.read_bytes)
    if len(snapshot) > 64 * 1024:
        raise script_install.InstallUnsafeError(
            "BetterGI 安装标记异常，请手动检查安装状态"
        )
    try:
        content = json.loads(snapshot)
        target = (
            str(content.get("target", "未知"))[:64]
            if isinstance(content, dict)
            else "未知"
        )
    except (ValueError, UnicodeDecodeError):
        target = "未知"

    try:
        installed = str(await asyncio.to_thread(program_update.read_version, root))
    except Exception as error:
        # 元数据不可读时仍允许用户选择重试；跳过阶段才严格校验。
        logger.warning(f"读取 BetterGI 当前版本失败，恢复提示显示未知：{error}")
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
        protocol.ID_TASK_MANAGER, protocol.BETTERGI_INSTALL_DECISION, receive
    )
    try:
        sent = await Publisher.send(
            id=protocol.ID_TASK_MANAGER,
            type=protocol.BETTERGI_INSTALL_PROMPT,
            data={
                "requestId": request_id,
                "taskId": task_id,
                "channel": channel,
                "takeoverEnabled": takeover_enabled,
                "installedVersion": installed,
                "targetVersion": target,
            },
        )
        if not sent:
            raise script_install.InstallUnsafeError(
                "BetterGI 上次安装未确认；未连接主界面，无法获取恢复选择，请打开 MAS 界面重试"
            )
        logger.warning(
            f"BetterGI 安装未确认，等待用户选择：当前={installed}，"
            f"原目标={target}，通道={channel}，自动接管={takeover_enabled}"
        )
        try:
            action = await asyncio.wait_for(future, timeout=_PROMPT_TIMEOUT_SECONDS)
        except TimeoutError as error:
            raise script_install.InstallUnsafeError(
                "BetterGI 安装恢复选择超时，本次任务已停止；未修改安装标记"
            ) from error
        if action == "stop":
            raise script_install.InstallUnsafeError(
                "用户取消 BetterGI 安装恢复，本次任务已停止；未修改安装标记"
            )
        if (
            marker.is_symlink()
            or not marker.is_file()
            or await asyncio.to_thread(marker.read_bytes) != snapshot
        ):
            raise script_install.InstallUnsafeError(
                "BetterGI 安装状态在等待选择时发生变化，本次任务已停止，请重新检查"
            )
        logger.warning(f"用户选择 BetterGI 安装恢复操作：{action}")
        return action, snapshot
    finally:
        unregister()
        # 让超时、手动停止及任务取消的旧弹窗失效；迟到回复不会再被接受。
        try:
            await Publisher.send(
                id=protocol.ID_TASK_MANAGER,
                type=protocol.BETTERGI_INSTALL_PROMPT_CLOSED,
                data={"requestId": request_id},
            )
        except Exception:
            logger.warning("发送 BetterGI 安装恢复弹窗关闭通知失败")


async def skip_unconfirmed_install(root: Path, snapshot: bytes) -> str:
    """在用户明确确认后跳过一次残留安装；先核查程序，最后清除同一份标记。

    只允许拥有安装锁的 BetterGIManager 调用。无法证明进程停止、标记未变、
    当前可执行文件版本/架构可识别时，不能清理标记。
    """
    from packaging.version import Version

    marker = script_install.workspace(root) / "bgi-install.json"
    try:
        record = json.loads(snapshot)
        if not isinstance(record, dict) or not isinstance(record.get("target"), str):
            raise ValueError("安装标记格式不正确")
        Version(record["target"])
    except (ValueError, TypeError) as error:
        raise script_install.InstallUnsafeError(
            "BetterGI 安装标记内容异常，不能直接跳过，请使用官方安装器修复"
        ) from error

    # 不能只看安装目录：官方安装器可能从用户的下载文件夹启动。
    await asyncio.to_thread(program_update.assert_idle, root)
    if (
        marker.is_symlink()
        or not marker.is_file()
        or await asyncio.to_thread(marker.read_bytes) != snapshot
    ):
        raise script_install.InstallUnsafeError(
            "BetterGI 安装恢复记录已经变化，本次不清理，请重新检查"
        )
    try:
        version = await asyncio.to_thread(program_update.read_version, root)
        arch = await asyncio.to_thread(
            script_install.read_pe_architecture, root / "BetterGI.exe"
        )
        if arch != "x86_64":
            raise ValueError("程序架构不可识别")
    except Exception as error:
        raise script_install.InstallUnsafeError(
            "BetterGI 当前程序版本或架构不可识别，不能跳过，请先手动修复"
        ) from error

    # 版本及架构检查不保证所有附属文件完整；这是用户主动接受的风险。
    await asyncio.to_thread(program_update.assert_idle, root)
    if (
        marker.is_symlink()
        or not marker.is_file()
        or await asyncio.to_thread(marker.read_bytes) != snapshot
    ):
        raise script_install.InstallUnsafeError("BetterGI 安装记录已变化，拒绝跳过")
    marker.unlink()
    try:
        await program_update.confirm_current_install(root)
    except BaseException:
        # 最后的退出/版本复核失败时，尽可能恢复原标记，避免失去安全门禁。
        if not marker.exists():
            try:
                marker.write_bytes(snapshot)
            except OSError as error:
                logger.error(f"BetterGI 无法恢复安装保护标记：{error}")
        raise
    logger.warning(
        f"用户确认跳过 BetterGI 未完成安装，已清除原标记；当前版本={version}"
    )
    return str(version)
