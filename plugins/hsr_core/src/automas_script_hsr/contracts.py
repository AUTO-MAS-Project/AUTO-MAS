from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Awaitable, Callable, Literal, Protocol, runtime_checkable


HSREngine = Literal["SRA", "M7A"]
HSRPhase = Literal["daily", "weekly"]
HSRRunStatus = Literal["completed", "failed", "incomplete", "skipped"]
HSRLogCallback = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class HSRTaskDescriptor:
    """适配器声明的规范化 HSR 任务。"""

    key: str
    name: str
    phase: HSRPhase
    description: str
    default_enabled: bool = False
    strategy_lines: tuple[str, ...] = ()
    native_tasks: tuple[str, ...] = ()

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HSRAdapterDescriptor:
    """HSR 引擎适配器的静态能力描述。"""

    engine: HSREngine
    display_name: str
    version: str
    tasks: tuple[HSRTaskDescriptor, ...]
    supported_modes: tuple[str, ...] = ("AutoProxy",)
    capabilities: frozenset[str] = frozenset()

    def asdict(self) -> dict[str, Any]:
        data = asdict(self)
        data["capabilities"] = sorted(self.capabilities)
        return data


@dataclass(frozen=True, slots=True)
class HSRStageOption:
    """统一阶段选项。"""

    id: str
    label: str
    detail: str = ""
    cost: int | None = None
    max_count: int | None = None
    native_payload: dict[str, Any] = field(default_factory=dict)

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HSRStageCategory:
    """统一阶段分类。"""

    key: str
    label: str
    options: tuple[HSRStageOption, ...]

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HSRRunRequest:
    """控制器执行一个规范任务所需的上下文。"""

    script_id: str
    user_id: str
    user_name: str
    task: HSRTaskDescriptor
    timeout_seconds: int
    script_config: Any
    user_config: Any
    log: HSRLogCallback
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HSRRunResult:
    """控制器返回的规范化结果。"""

    status: HSRRunStatus
    summary: str = ""
    completion_evidence: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    native_result: Any = field(default=None, repr=False, compare=False)

    @property
    def success(self) -> bool:
        return self.status == "completed"

    def asdict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "completion_evidence": dict(self.completion_evidence),
            "error": self.error,
        }


@runtime_checkable
class HSRTaskCatalogProvider(Protocol):
    """任务获取服务契约。"""

    descriptor: HSRAdapterDescriptor

    def list_tasks(self) -> tuple[HSRTaskDescriptor, ...]: ...

    def list_stage_options(
        self,
        *,
        script_config: Any,
        user_config: Any | None,
        slot: str,
    ) -> tuple[HSRStageCategory, ...] | Awaitable[tuple[HSRStageCategory, ...]]: ...

@runtime_checkable
class HSRControllerSession(Protocol):
    """单次控制器运行会话。"""

    async def run(self, request: HSRRunRequest) -> HSRRunResult: ...

    async def cancel(self) -> None: ...

    async def close(self) -> None: ...


@runtime_checkable
class HSRController(Protocol):
    """外部脚本控制器契约。"""

    descriptor: HSRAdapterDescriptor

    def probe(self, script_config: Any) -> tuple[bool, str]: ...

    async def open_session(
        self,
        *,
        script_id: str,
        script_config: Any,
        log: HSRLogCallback,
        coordinator: Any,
    ) -> HSRControllerSession: ...


@dataclass(frozen=True, slots=True)
class HSRAdapterGroup:
    """同一插件原子提供的任务目录与控制器。"""

    owner: str
    task_catalog: HSRTaskCatalogProvider
    controller: HSRController

    @property
    def descriptor(self) -> HSRAdapterDescriptor:
        return self.task_catalog.descriptor


@dataclass(frozen=True, slots=True)
class HSRCapabilitySnapshot:
    """前端和运行时共享的 HSR 能力快照。"""

    revision: int
    available: bool
    unavailable_reason: str | None
    candidate_engines: tuple[HSREngine, ...]
    configured_engines: tuple[HSREngine, ...]
    effective_engines: tuple[HSREngine, ...]
    supported_modes: tuple[str, ...]
    adapters: tuple[dict[str, Any], ...]
    tasks: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...] = ()

    def asdict(self) -> dict[str, Any]:
        return asdict(self)
