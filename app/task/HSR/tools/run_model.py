#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Literal

from app.models.config import HSRUserConfig
from app.models.task import UserItem
from app.utils import ProcessManager

from .m7a_runtime import M7ARunner
from .sra_runtime import SRAProcessRegistry

HSRPhase = Literal["daily", "weekly", "monthly"]
HSRScriptRunner = Literal["M7A", "SRA"]
HSRLoginMode = Literal["sra_switch", "sra_remembered", "m7a_fallback"]
HSRModuleResultStatus = Literal["completed", "failed", "incomplete", "skipped"]


@dataclass(frozen=True)
class HSRLoginPlan:
    """HSR 用户本轮进入游戏/登录策略。"""

    mode: HSRLoginMode
    sra_exe_path: Path

    @property
    def uses_sra_start_game(self) -> bool:
        """是否需要在队列中插入 SRA StartGame。"""

        return self.mode in ("sra_switch", "sra_remembered")

    @property
    def needs_account_switch(self) -> bool:
        """是否需要按切号流程重启游戏。"""

        return self.mode == "sra_switch"


@dataclass
class CompletionWriteback:
    """真实执行成功后需要写回用户 Data 的完成态"""

    user_id: str
    user_name: str
    reason: str
    fields: list[tuple[str, str, object]]


@dataclass
class HSRModuleResult:
    """单用户单模块的最终执行结果，用于调度台日志和通知汇总。"""

    user_id: str
    user_name: str
    module_key: str
    module_name: str
    script: HSRScriptRunner | str
    status: HSRModuleResultStatus
    reason: str = ""


@dataclass
class HSRRunItem:
    """HSR 队列中的一个真实执行项。"""

    user_item: UserItem
    user_cfg: HSRUserConfig
    user_name: str
    user_id: str
    phase: HSRPhase
    module_key: str
    module_name: str
    script: HSRScriptRunner
    description: str
    timeout_seconds: int
    run: Callable[[], Awaitable[object]]
    on_success: Callable[[object], None] | None = None
    last_error: str = ""
    attempts: int = 0


class HSRRetryableTaskError(RuntimeError):
    """外部脚本已启动但业务执行失败，可在本轮末尾补跑。"""

    def __init__(
        self,
        message: str,
        *,
        result: object | None = None,
    ) -> None:
        super().__init__(message)
        self.result = result


@dataclass
class HSRRuntimeState:
    """HSR 单次运行中跨用户共享的外部脚本状态。"""

    log_lines: list[str]
    completion_writebacks: list[CompletionWriteback]
    module_results: list[HSRModuleResult] = field(default_factory=list)
    m7a_runner: M7ARunner | None = None
    sra_process_registry: SRAProcessRegistry = field(default_factory=SRAProcessRegistry)
    game_process_manager: ProcessManager = field(default_factory=ProcessManager)
    game_launch_checked: bool = False
    game_started_by_mas: bool = False
    game_exe_path: Path | None = None
    last_external_script: HSRScriptRunner | None = None
    game_session_clean: bool = False
    game_transitioning: bool = False

    def record_module_result(self, result: HSRModuleResult) -> None:
        """记录模块最终态；同一用户同一模块以后写入为准。"""

        self.module_results = [
            item
            for item in self.module_results
            if not (
                item.user_id == result.user_id
                and item.module_key == result.module_key
            )
        ]
        self.module_results.append(result)


def external_result_failure_summary(result: object) -> str:
    """提取外部脚本结果中的失败摘要，避免整段日志刷屏。"""

    if result is None:
        return "未知错误"
    error = str(getattr(result, "error", "") or "").strip()
    output = str(getattr(result, "output", "") or "").strip()
    returncode = getattr(result, "returncode", None)
    text = error or output
    if not text and returncode not in (None, 0):
        text = f"进程退出码：{returncode}"
    if not text:
        text = "未知错误"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 8:
        lines = lines[-8:]
    return "\n".join(lines)
