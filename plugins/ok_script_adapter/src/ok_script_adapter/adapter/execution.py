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

"""ok-script 不可变执行计划与纯结果判态。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from ..common.events import (
    OkScriptRunEvent,
    OkScriptRunFailure,
    format_partial_success_status,
)
from ..common.provider import OkScriptProvider
from ..shell.descriptor import (
    PROTOCOL_LEGACY_EXE,
    OkProjectDescriptor,
)
from ..shell.runtime import OkShellRunner, OkShellRuntimeError


WHOLE_RUN_RETRY_SCOPE = "whole-run"


@dataclass(frozen=True, slots=True)
class ProcessTargetSpec:
    """宿主 ProcessManager 需要追踪的目标进程描述。"""

    name: str = ""
    executable: str = ""


@dataclass(frozen=True, slots=True)
class TaskInvocation:
    """一轮 ok-script 任务的确定启动参数。"""

    task_index: int
    task_selector: str
    protocol: str
    command: tuple[str, ...]
    cwd: Path
    environment: tuple[tuple[str, str], ...]
    target_process: ProcessTargetSpec | None = None

    def environment_dict(self) -> dict[str, str]:
        """为宿主进程 API 返回独立的可变环境副本。"""

        return dict(self.environment)


@dataclass(frozen=True, slots=True)
class RunObservationPolicy:
    """provider 已验证的文本日志判态规则。"""

    display_name: str
    running_status: str
    fatal_patterns: tuple[tuple[str, str], ...]
    success_patterns: tuple[str, ...]
    log_time_range: tuple[int, int]
    log_time_format: str


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """一位用户的一次完整运行计划；不保存任何实时状态。"""

    invocation: TaskInvocation
    observation: RunObservationPolicy
    log_path: Path
    event_path: Path
    attempt_limit: int
    run_timeout_seconds: float
    retry_delay_seconds: float
    log_start_timeout_seconds: float = 60.0
    exit_wait_timeout_seconds: float = 10.0
    retry_scope: str = WHOLE_RUN_RETRY_SCOPE


@dataclass(frozen=True, slots=True)
class RunObservation:
    """ResultObserver 输出的一项终态判定。"""

    status: str
    successful: bool
    user_status: str
    source: str
    failures: tuple[OkScriptRunFailure, ...] = ()


class ExecutionPlanner:
    """把 descriptor、provider 与用户选择编译为纯执行计划。"""

    def __init__(
        self,
        descriptor: OkProjectDescriptor,
        provider: OkScriptProvider,
        *,
        provider_registered: bool,
    ) -> None:
        self.descriptor = descriptor
        self.provider = provider
        self.provider_registered = provider_registered

    def build(
        self,
        *,
        task_index: int,
        available_protocols: tuple[str, ...],
        attempt_limit: int,
        run_timeout_minutes: int,
        retry_delay_seconds: float = 10.0,
    ) -> ExecutionPlan:
        """生成一份不启动进程、不读取日志的完整运行计划。"""

        if not available_protocols:
            raise OkShellRuntimeError("没有可用于执行计划的运行协议")
        if attempt_limit <= 0:
            raise OkShellRuntimeError("整轮运行次数必须大于 0")
        if run_timeout_minutes <= 0:
            raise OkShellRuntimeError("运行超时必须大于 0")
        if retry_delay_seconds < 0:
            raise OkShellRuntimeError("重试等待时间不能小于 0")

        task_descriptor = next(
            (
                task
                for task in self.descriptor.tasks
                if task.index == task_index
            ),
            None,
        )
        if self.descriptor.tasks and task_descriptor is None:
            raise OkShellRuntimeError(
                f"任务序号不属于当前项目 descriptor: {task_index}"
            )

        selected_protocol = available_protocols[0]
        command_builder = OkShellRunner(self.descriptor)
        launch_spec = command_builder.build_launch_spec(
            str(task_index),
            protocol=selected_protocol,
            available_protocols=available_protocols,
        )
        target_process = self._target_process(launch_spec.protocol)
        task_selector = (
            task_descriptor.selector
            if task_descriptor is not None
            else str(task_index)
        )

        return ExecutionPlan(
            invocation=TaskInvocation(
                task_index=task_index,
                task_selector=task_selector,
                protocol=launch_spec.protocol,
                command=launch_spec.command,
                cwd=launch_spec.cwd,
                environment=tuple(sorted(launch_spec.environment.items())),
                target_process=target_process,
            ),
            observation=RunObservationPolicy(
                display_name=self.provider.display_name,
                running_status=self.provider.running_status,
                fatal_patterns=self.provider.fatal_patterns,
                success_patterns=self.provider.success_patterns,
                log_time_range=self.provider.log_time_range,
                log_time_format=self.provider.log_time_format,
            ),
            log_path=self.descriptor.log_path,
            event_path=self.descriptor.log_path.with_name(
                self.provider.event_log_name
            ),
            attempt_limit=attempt_limit,
            run_timeout_seconds=float(run_timeout_minutes * 60),
            retry_delay_seconds=float(retry_delay_seconds),
        )

    def _target_process(self, protocol: str) -> ProcessTargetSpec | None:
        if not (
            self.provider_registered
            and protocol == PROTOCOL_LEGACY_EXE
        ):
            return None

        process_name = self.provider.track_process_name.strip()
        pythonw_path = self.provider.pythonw_path.strip()
        executable = (
            str(self.provider.track_process_path(self.descriptor.root_path))
            if pythonw_path
            else ""
        )
        if not process_name and not executable:
            return None
        return ProcessTargetSpec(
            name=process_name,
            executable=executable,
        )


class ResultObserver:
    """集中处理事件 v1 与旧文本的终态优先级。"""

    def __init__(self, policy: RunObservationPolicy) -> None:
        self.policy = policy
        self.event_protocol_active = False
        self.event_terminal_received = False
        self.failures: list[OkScriptRunFailure] = []
        self.terminal_observation: RunObservation | None = None

    def observe_event(self, event: OkScriptRunEvent) -> RunObservation | None:
        """消费一项 v1 事件；非终态事件仅更新诊断状态。"""

        if self.terminal_observation is not None:
            return None

        self.event_protocol_active = True
        if event.failures:
            self.failures = list(event.failures)
        if event.event == "task_failed":
            if not event.failures:
                self.failures.append(
                    OkScriptRunFailure(
                        task=event.task or "未命名任务",
                        message=event.message or "未提供失败原因",
                    )
                )
            return None

        if event.event == "run_failed" or (
            event.event == "run_completed" and event.success is False
        ):
            self.event_terminal_received = True
            return self._set_terminal(
                self.failure(
                    event.message or f"{self.policy.display_name} 运行失败",
                    source="event",
                )
            )

        if event.event != "run_completed":
            return None

        self.event_terminal_received = True
        failures = tuple(self.failures)
        status = format_partial_success_status(failures) if failures else "Success!"
        return self._set_terminal(
            RunObservation(
                status=status,
                successful=True,
                user_status="完成",
                source="event",
                failures=failures,
            )
        )

    def observe_text(self, text: str, *, source: str) -> RunObservation | None:
        """在尚无结构化终态时按 provider 文本规则判态。"""

        if self.terminal_observation is not None or self.event_terminal_received:
            return None

        for needle, message in self.policy.fatal_patterns:
            if needle in text:
                return self._set_terminal(
                    self.failure(message, source=source)
                )

        text_lower = text.lower()
        if any(
            success.lower() in text_lower
            for success in self.policy.success_patterns
        ):
            return self._set_terminal(
                RunObservation(
                    status="Success!",
                    successful=True,
                    user_status="完成",
                    source=source,
                )
            )
        return None

    def observe_legacy_log(
        self,
        log_content: list[str],
        *,
        process_running: bool,
        latest_time: datetime,
        now: datetime,
        run_timeout_seconds: float,
    ) -> RunObservation | None:
        """消费传统日志快照，并在无文本终态时检查退出与超时。"""

        observation = self.observe_text("".join(log_content), source="legacy-log")
        if observation is not None:
            return observation
        if self.terminal_observation is not None or self.event_terminal_received:
            return None
        if not process_running:
            return self._set_terminal(
                self.failure(
                    f"{self.policy.display_name} 在完成任务前退出",
                    source="legacy-log",
                )
            )
        if now - latest_time > timedelta(seconds=run_timeout_seconds):
            return self._set_terminal(
                self.failure(
                    f"{self.policy.display_name} 运行超时",
                    source="timeout",
                )
            )
        return None

    def observe_process_exit(
        self,
        *,
        return_code: int | None,
        protocol: str,
    ) -> RunObservation | None:
        """进程退出只提供失败证据，不能凭退出码推定成功。"""

        if self.terminal_observation is not None:
            return self.terminal_observation
        if protocol == PROTOCOL_LEGACY_EXE or return_code is None:
            return None
        if return_code == 0:
            status = (
                f"{self.policy.display_name} 进程已退出，"
                "但未收到成功日志或结构化完成事件"
            )
        else:
            status = (
                f"{self.policy.display_name} 异常退出，退出码 {return_code}"
            )
        return self._set_terminal(
            self.failure(status, source="process-exit")
        )

    def failure(self, status: str, *, source: str) -> RunObservation:
        """构造一项失败观察；由调用方决定是否固定为本轮终态。"""

        return RunObservation(
            status=status,
            successful=False,
            user_status="异常",
            source=source,
            failures=tuple(self.failures),
        )

    def set_failure(self, status: str, *, source: str) -> RunObservation:
        """把控制器边界错误固定为本轮终态。"""

        return self._set_terminal(self.failure(status, source=source))

    def _set_terminal(self, observation: RunObservation) -> RunObservation:
        self.terminal_observation = observation
        return observation
