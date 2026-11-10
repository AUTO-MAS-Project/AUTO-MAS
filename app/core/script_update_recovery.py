#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""通用安装失败自动恢复的决策层：不运行一条龙，不直接删除安装标记。

脚本适配器只提供只读检查、安全确认清理、官方修复回调；
公用入口严格决定能否继续并将恢复结果交回任务级汇总。
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.services import script_install
from app.services.script_install import InstallUnsafeError
from app.services.script_install_backup import ManagedInstallBackup


@dataclass(frozen=True)
class InstallInspection:
    """适配器确认的安装状态；所有 true 均须在安装锁下经过真实检查。

    healthy 不等同于可清除未完成安装标记。
    updated_confirmed 只能在新版本与资源已被可靠证明安装完整时为真；
    previous_confirmed 只能在旧版有完整性依据、所有写入已停止且无 pending 时为真。
    """

    pending: bool
    healthy: bool
    installed_version: str | None = None
    target_version: str | None = None
    updated_confirmed: bool = False
    previous_confirmed: bool = False


@dataclass(frozen=True)
class RecoveryIncident:
    script_id: str
    script_type: str
    install_root: str
    outcome: Literal[
        "verified", "reinstalled", "old_version", "blocked", "installed", "deferred"
    ]
    installed_version: str | None = None
    source: str | None = None
    reason: str = ""


class DownloadRetryFailed(RuntimeError):
    """仅可由未修改安装目录的下载/准备阶段抛出，不能包装安装期失败。"""

    def __init__(self, *, source: str, reason: str) -> None:
        super().__init__(reason)
        self.source = source
        # 适配器提供固定的用户可见原因，不透传可能含 token 的完整下载 URL。
        self.reason = reason[:240]


def _safe_previous(state: InstallInspection) -> bool:
    return not state.pending and state.healthy and state.previous_confirmed


async def reconcile_installation(
    *,
    script_id: str,
    script_type: str,
    install_root: Path,
    inspect: Callable[[], Awaitable[InstallInspection]],
    acknowledge: Callable[[], Awaitable[None]],
    reinstall: Callable[[], Awaitable[None]],
    report: Callable[[RecoveryIncident], None],
) -> Literal["no_pending", "verified", "reinstalled", "old_version"]:
    """根据原安装实际状态自动恢复；不能仅凭版本号清除未完成事务。

    inspect/acknowledge/reinstall 的调用方持有原脚本安装锁。acknowledge
    自己核验同一记录并清除、复核；出现竞态应抛错并保留或恢复原标记。
    """
    before: InstallInspection | None = None

    def emit(
        outcome: Literal["verified", "reinstalled", "old_version", "blocked"],
        *,
        reason: str = "",
        source: str | None = None,
        version: str | None = None,
    ) -> None:
        report(
            RecoveryIncident(
                script_id=script_id,
                script_type=script_type,
                install_root=str(install_root.resolve()),
                outcome=outcome,
                installed_version=version
                or (before.installed_version if before else None),
                source=source,
                reason=reason,
            )
        )

    try:
        before = await inspect()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        emit("blocked", reason=f"初始安装检查异常（{type(error).__name__}）")
        raise
    if not before.pending:
        return "no_pending"

    if before.healthy and before.updated_confirmed:
        try:
            await acknowledge()
            after = await inspect()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            emit("blocked", reason=f"安装确认或复核异常（{type(error).__name__}）")
            raise
        if after.pending or not after.healthy:
            emit("blocked", reason="安装确认后复核失败")
            raise InstallUnsafeError("安装记录清除后复核失败；拒绝启动脚本")
        emit("verified", version=after.installed_version)
        return "verified"

    try:
        await reinstall()
    except asyncio.CancelledError:
        raise
    except DownloadRetryFailed as error:
        # 只有下载/准备阶段失败才允许考虑保留旧版；真正改写安装时
        # 失败不允许包装为 DownloadRetryFailed。
        try:
            after = await inspect()
        except Exception:
            emit("blocked", source=error.source, reason="下载失败且无法确认原安装")
            raise
        if _safe_previous(after):
            emit(
                "old_version",
                reason=error.reason,
                source=error.source,
                version=after.installed_version,
            )
            return "old_version"
        emit(
            "blocked",
            reason=f"下载异常：{error.reason}；原安装未通过安全检查",
            source=error.source,
        )
        raise InstallUnsafeError(
            "恢复包再次下载失败，原安装或未完成事务尚未确认安全，禁止启动"
        ) from error
    except Exception as error:
        emit("blocked", reason=f"安装恢复失败（{type(error).__name__}）")
        raise

    try:
        after = await inspect()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        emit("blocked", reason=f"重装后复核异常（{type(error).__name__}）")
        raise
    if after.pending or not after.healthy:
        emit("blocked", reason="重装后完整性或安装标记检查失败")
        raise InstallUnsafeError("恢复安装后状态仍未确认，拒绝启动脚本")
    emit("reinstalled", version=after.installed_version)
    return "reinstalled"


class InstallReportedFailure(RuntimeError):
    """官方安装器明确退出并报告失败；不可用于运行中或状态不明的超时。"""


class InstallTimedOut(TimeoutError):
    """安装结果不明，必须保存快照到下一轮；不代表进程已停写。"""


async def run_managed_installation(
    *,
    script_id: str,
    script_type: str,
    install_root: Path,
    inspect: Callable[[], Awaitable[InstallInspection]],
    acknowledge: Callable[[], Awaitable[None]],
    install: Callable[[], Awaitable[None]],
    ensure_idle: Callable[[], Awaitable[None]],
    after_rollback: Callable[[], Awaitable[None]],
    report: Callable[[RecoveryIncident], None],
) -> Literal["installed", "verified", "old_version"]:
    """安装与故障恢复均经此入口收发，专项只返回可验证状态和执行原生命令。

    入口调用方必须持有同一目录的跨进程安装锁；整个执行期间不能释放。
    ensure_idle 要保证子进程、下载器、安装线程以及外部安装程序全部停写。
    after_rollback 只能清理本次 MAS 安装留下的事务标记，不触碰上游自有记录。
    所有副作用均由公共层发起；取消绝不自动覆盖正在写入的安装目录。
    """
    backup = ManagedInstallBackup(
        install_root, script_id=script_id, script_type=script_type
    )
    state = backup.read()

    def emit(
        outcome: Literal["installed", "verified", "old_version", "blocked", "deferred"],
        reason: str = "",
        version: str | None = None,
        source: str | None = None,
    ) -> None:
        report(
            RecoveryIncident(
                script_id=script_id,
                script_type=script_type,
                install_root=str(install_root.resolve()),
                outcome=outcome,
                installed_version=version,
                source=source,
                reason=reason,
            )
        )

    async def verify_new() -> InstallInspection:
        """确认后台已停写且新安装健康，才可删除旧版备份。"""
        await ensure_idle()
        result = await inspect()
        if not result.healthy or not result.updated_confirmed:
            raise InstallUnsafeError("新版本健康状态或安装完整性未确认")
        if result.pending:
            await acknowledge()
            result = await inspect()
        if result.pending or not result.healthy or not result.updated_confirmed:
            raise InstallUnsafeError("清理标记后新版本仍未通过完整性复核")
        await ensure_idle()
        return result

    async def restore_previous(
        reason: str, *, source: str | None = None
    ) -> Literal["old_version"]:
        try:
            await ensure_idle()
            current = backup.read()
            if current is None:
                raise InstallUnsafeError("恢复事务丢失，无法安全回滚")
            if current["phase"] == "restored":
                if not await script_install_backup_verified(backup):
                    raise InstallUnsafeError("旧版本恢复记录不匹配")
            else:
                await backup.restore()
            # 标记操作仍由专项验证身份，但清理时机由公共层掌控。
            await after_rollback()
            previous = await inspect()
            if (
                previous.pending
                or not previous.healthy
                or not previous.previous_confirmed
                or not await script_install_backup_verified(backup)
            ):
                raise InstallUnsafeError("回退后旧版未通过完整性或标记检查")
            await backup.finish_restore()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            emit("blocked", f"自动回退未能安全完成（{type(error).__name__}）")
            raise
        emit(
            "old_version",
            f"{reason}；已从更新前备份恢复旧版，继续执行原有任务",
            previous.installed_version,
            source=source,
        )
        return "old_version"

    async def retry_previous() -> Literal["installed", "verified", "old_version"]:
        """仅在下次运行时执行；超时当次不尝试覆盖或放行。"""
        try:
            await ensure_idle()
            current = backup.read()
            if current is None:
                raise InstallUnsafeError("安装备份已被外部修改")
            if current["phase"] in {"restoring", "restored"}:
                return await restore_previous("上次安装回退中断")
            observed = await inspect()
            if observed.healthy and observed.updated_confirmed:
                verified = await verify_new()
                await backup.finish_success()
                emit(
                    "verified",
                    "上次安装实际已成功，清理残留备份",
                    verified.installed_version,
                )
                return "verified"
            if current["phase"] == "installed":
                raise InstallUnsafeError("已提交的安装未通过复核，保留恢复现场")
            backup.set_phase("retrying")
            await install()
            verified = await verify_new()
            await backup.finish_success()
            emit(
                "installed", "上次未确认安装已自动重试成功", verified.installed_version
            )
            return "installed"
        except asyncio.CancelledError:
            raise
        except DownloadRetryFailed as error:
            return await restore_previous(
                f"恢复时再次下载失败：{error.reason}", source=error.source
            )
        except Exception as error:
            # 仅当恢复所依赖的写盘者已经确认停止，才有资格还原快照。
            # 超时重试即使抛 TimeoutError，也不能假设安装进程退出。
            return await restore_previous(
                f"上次安装的自动重试失败（{type(error).__name__}）"
            )

    if state is not None:
        return await retry_previous()

    # 新安装：只读检查、备份、再更新。备份失败之前绝不能修改原目录。
    try:
        await ensure_idle()
        original = await inspect()
        if original.pending or not original.healthy:
            raise InstallUnsafeError("原脚本已有未确认安装或不健康，不能建立新备份")
        await backup.create(original.installed_version)
        backup.set_phase("installing")
    except asyncio.CancelledError:
        raise
    except Exception as error:
        emit("blocked", f"准备更新备份失败（{type(error).__name__}）")
        raise

    try:
        await install()
    except asyncio.CancelledError:
        backup.set_phase("timed_out")
        raise
    except (TimeoutError, InstallTimedOut) as error:
        backup.set_phase("timed_out")
        emit(
            "deferred",
            f"本次安装超时，结果尚未确认（{type(error).__name__}）；保留备份",
        )
        raise InstallUnsafeError(
            "安装超时，已保留旧版备份，下一次运行自动检查"
        ) from error
    except InstallReportedFailure:
        return await restore_previous("安装器明确报告失败")
    except DownloadRetryFailed as error:
        return await restore_previous(
            f"更新包下载失败：{error.reason}", source=error.source
        )
    except Exception as error:
        backup.set_phase("timed_out")
        emit("deferred", f"安装结果无法判断（{type(error).__name__}），保留备份")
        raise

    try:
        updated = await verify_new()
    except asyncio.CancelledError:
        backup.set_phase("timed_out")
        raise
    except Exception as error:
        return await restore_previous(
            f"安装返回成功但健康检查失败（{type(error).__name__}）"
        )
    try:
        await backup.finish_success()
    except Exception as error:
        emit("blocked", f"新安装已验证，但清理备份失败（{type(error).__name__}）")
        raise
    emit("installed", "更新成功，已删除旧版备份", updated.installed_version)
    return "installed"


async def script_install_backup_verified(backup: ManagedInstallBackup) -> bool:
    """回退后的深度哈希校验由可取消工作线程执行，避免堵塞调度循环。"""
    from app.services import script_install

    return await script_install.run_worker(
        lambda cancelled: (
            backup._hashes(backup.root, cancelled) == backup.read()["files"]
        )
    )
