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

from app.services.script_install import InstallUnsafeError


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
    outcome: Literal["verified", "reinstalled", "old_version", "blocked"]
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
    before = await inspect()
    if not before.pending:
        return "no_pending"

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
                installed_version=version or before.installed_version,
                source=source,
                reason=reason,
            )
        )

    if before.healthy and before.updated_confirmed:
        await acknowledge()
        after = await inspect()
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

    after = await inspect()
    if after.pending or not after.healthy:
        emit("blocked", reason="重装后完整性或安装标记检查失败")
        raise InstallUnsafeError("恢复安装后状态仍未确认，拒绝启动脚本")
    emit("reinstalled", version=after.installed_version)
    return "reinstalled"
