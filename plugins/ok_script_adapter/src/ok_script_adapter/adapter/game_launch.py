#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ok-script 游戏启动和清理生命周期。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.services import System
from app.utils.ProcessManager import ProcessInfo, ProcessManager, is_process_running

from ..common.provider import GameLaunchDescriptor, GamePathResolution


class GameProcessManager(Protocol):
    """游戏生命周期使用的最小宿主进程管理接口。"""

    async def open_process(
        self,
        program: Path | str,
        *args: str,
        **kwargs: object,
    ) -> None: ...

    async def open_protocol(
        self,
        protocol_url: str,
        target_process: ProcessInfo,
    ) -> None: ...

    async def kill(self) -> None: ...


@dataclass(frozen=True, slots=True)
class GameLaunchResult:
    """一次游戏启动或附着的结果。"""

    successful: bool
    status: str
    owner: str


@dataclass(frozen=True, slots=True)
class GameCleanupResult:
    """一次游戏清理的完整结果，即使部分目标失败也会继续尝试。"""

    attempted: bool
    errors: tuple[str, ...] = ()


class GameLaunchController:
    """根据 provider 的启动 descriptor 调用宿主游戏进程能力。"""

    def __init__(
        self,
        *,
        display_name: str,
        descriptor: GameLaunchDescriptor,
        resolution: GamePathResolution,
        process_manager: GameProcessManager | None,
        process_running: Callable[[str], bool] = is_process_running,
        kill_process: Callable[[Path], Awaitable[None]] = System.kill_process,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.display_name = display_name
        self.descriptor = descriptor
        self.resolution = resolution
        self.process_manager = process_manager
        self.process_running = process_running
        self.kill_process = kill_process
        self.sleep = sleep
        self._cleanup_result: GameCleanupResult | None = None

    def should_cleanup(
        self,
        *,
        manual_stop: bool,
        close_on_manual_stop: bool,
    ) -> bool:
        """判断本轮结束是否应执行独立于启动所有权的游戏清理。"""

        policy = self.descriptor.cleanup_policy
        if policy == "never":
            return False
        if manual_stop:
            return close_on_manual_stop
        if policy == "manual-stop":
            return False
        return bool(self.resolution.cleanup_paths) or self.process_manager is not None

    async def start(
        self,
        *,
        arguments: list[str],
        fallback_wait_seconds: float,
    ) -> GameLaunchResult:
        """启动、附着或明确交由脚本启动游戏。"""

        self._cleanup_result = None
        mode = self.descriptor.mode
        if mode == "script-managed":
            return GameLaunchResult(
                successful=True,
                status="MAS 已跳过游戏启动，游戏启动由 ok-script 负责",
                owner="script",
            )

        ready_process_name = self._ready_process_name()
        if mode == "attach":
            if not ready_process_name:
                return GameLaunchResult(
                    successful=False,
                    status=f"{self.display_name} 未声明可附着的游戏进程",
                    owner="none",
                )
            if not self.process_running(ready_process_name):
                return GameLaunchResult(
                    successful=False,
                    status=(
                        f"请先启动 {self.display_name} 游戏进程 "
                        f"{ready_process_name}"
                    ),
                    owner="none",
                )
            return GameLaunchResult(
                successful=True,
                status=(
                    f"检测到 {self.display_name} 游戏已运行，"
                    "已附着到现有游戏进程"
                ),
                owner="external",
            )

        existing_result = await self._handle_existing_process(ready_process_name)
        if existing_result is not None:
            return existing_result

        if self.descriptor.launch_kind == "executable":
            return await self._start_executable(
                arguments=arguments,
                fallback_wait_seconds=fallback_wait_seconds,
            )
        if self.descriptor.launch_kind == "uri":
            return await self._start_uri(
                fallback_wait_seconds=fallback_wait_seconds,
            )
        return GameLaunchResult(
            successful=False,
            status=f"{self.display_name} 未声明可启动的游戏目标",
            owner="none",
        )

    async def cleanup(self) -> GameCleanupResult:
        """依次清理宿主跟踪目标和所有 provider 声明的兜底路径。"""

        if self._cleanup_result is not None:
            return self._cleanup_result

        errors: list[str] = []
        if self.process_manager is not None:
            try:
                await self.process_manager.kill()
            except Exception as exc:
                errors.append(f"通过进程管理器关闭游戏失败: {exc}")

        for path in self.resolution.cleanup_paths:
            try:
                await self.kill_process(path)
            except Exception as exc:
                errors.append(f"关闭游戏进程 {path.name} 失败: {exc}")

        self._cleanup_result = GameCleanupResult(
            attempted=True,
            errors=tuple(errors),
        )
        return self._cleanup_result

    async def _handle_existing_process(
        self,
        ready_process_name: str,
    ) -> GameLaunchResult | None:
        if not ready_process_name or not self.process_running(ready_process_name):
            return None

        policy = self.descriptor.already_running_policy
        if policy == "attach":
            return GameLaunchResult(
                successful=True,
                status=(
                    f"检测到 {self.display_name} 游戏已在运行，"
                    "跳过由 MAS 重复启动游戏"
                ),
                owner="external",
            )
        if policy == "error":
            return GameLaunchResult(
                successful=False,
                status=(
                    f"检测到 {self.display_name} 游戏已在运行，"
                    "请关闭游戏后重试或改用附着策略"
                ),
                owner="external",
            )

        cleanup_result = await self.cleanup()
        if cleanup_result.errors:
            return GameLaunchResult(
                successful=False,
                status="无法关闭已运行的游戏，不能安全重启",
                owner="external",
            )
        self._cleanup_result = None
        return None

    async def _start_executable(
        self,
        *,
        arguments: list[str],
        fallback_wait_seconds: float,
    ) -> GameLaunchResult:
        launch_path = self.resolution.launch_path
        if launch_path is None or not launch_path.is_file():
            return GameLaunchResult(
                successful=False,
                status=f"请设置 {self.display_name} 游戏启动程序路径",
                owner="none",
            )

        manager = self._require_process_manager()
        try:
            await manager.open_process(
                launch_path,
                *arguments,
                target_process=self._target_process(),
            )
        except Exception as exc:
            return GameLaunchResult(
                successful=False,
                status=f"{self.display_name} 游戏启动失败: {exc}",
                owner="none",
            )
        await self._wait_after_ready(fallback_wait_seconds)

        if self.descriptor.mode == "launcher":
            status = (
                f"MAS 已启动 {self.display_name} 启动器，"
                "并已等到游戏本体进程"
            )
        else:
            status = f"MAS 已启动 {self.display_name} 游戏"
        return GameLaunchResult(successful=True, status=status, owner="mas")

    async def _start_uri(
        self,
        *,
        fallback_wait_seconds: float,
    ) -> GameLaunchResult:
        target_process = self._target_process()
        if not self.descriptor.launch_uri or target_process is None:
            return GameLaunchResult(
                successful=False,
                status=f"{self.display_name} 未声明可跟踪的 URI 启动目标",
                owner="none",
            )

        manager = self._require_process_manager()
        try:
            await manager.open_protocol(self.descriptor.launch_uri, target_process)
        except Exception as exc:
            return GameLaunchResult(
                successful=False,
                status=f"{self.display_name} 游戏 URI 启动失败: {exc}",
                owner="none",
            )
        await self._wait_after_ready(fallback_wait_seconds)
        return GameLaunchResult(
            successful=True,
            status=f"MAS 已通过 URI 启动 {self.display_name} 游戏",
            owner="mas",
        )

    def _ready_process_name(self) -> str:
        return (
            self.descriptor.ready_process_name.strip()
            or (self.resolution.ready_path.name if self.resolution.ready_path else "")
            or (self.resolution.launch_path.name if self.resolution.launch_path else "")
        )

    def _target_process(self) -> ProcessInfo | None:
        process_name = self._ready_process_name()
        executable = self.resolution.ready_path or self.resolution.launch_path
        if not process_name and executable is None:
            return None
        return ProcessInfo(
            name=process_name or None,
            exe=str(executable) if executable else None,
        )

    def _require_process_manager(self) -> GameProcessManager:
        if self.process_manager is None:
            self.process_manager = ProcessManager()
        return self.process_manager

    async def _wait_after_ready(self, fallback_wait_seconds: float) -> None:
        if fallback_wait_seconds > 0:
            await self.sleep(fallback_wait_seconds)
