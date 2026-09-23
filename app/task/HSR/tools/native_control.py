"""HSR 原生配置与脚本直控的 old-dev 兼容层。

old-dev 只保存脚本 ``Info.M7APath``/``Info.SRAPath`` 和用户 ``Info`` 凭据。
本模块不启动原生编辑器；provider 仅负责检查与运行直控会话，外部配置文件
的写回由 HSRManager 的备份/恢复区负责。

直控只有一种形态：直接用脚本当前的原生配置运行——SRA 把 ``--inline run``
指向真实 profile 文件，三月七以真实安装根目录启动。不建临时目录、不复制
任何东西，用户在脚本 GUI 里改什么下次就跑什么。这是
``mas-script-specialized-adapter`` 里「直控＝直接使用脚本原有配置、由原生
GUI 维护」的口径。一个脚本挂多个账号、各跑不同计划的需求由「用户」来源
承担（每用户一份计划叠在活配置上），不再有直控快照。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .m7a_runtime import M7ARunner
from .run_model import HSRPhase
from .sra_runtime import (
    SRAProcessRegistry,
    get_sra_app_data_dir,
    resolve_sra_profile,
    run_sra_config,
)

HSREngine = Literal["SRA", "M7A"]

# 引擎回落顺序与 HSRTaskModule.supported_scripts 保持一致
_HSR_ENGINE_ORDER: tuple[HSREngine, ...] = ("M7A", "SRA")

# 各周期的超时配置键与默认值（分钟），默认值须与 HSRConfig.Run_*TimeLimit 一致。
# 托管队列按模块所属周期取值；直控整轮跑原生配置，取两者之和。
PHASE_TIMEOUT_CONFIG: dict[HSRPhase, tuple[str, int]] = {
    "daily": ("DailyTimeLimit", 20),
    "weekly": ("WeeklyTimeLimit", 60),
}


@dataclass(frozen=True, slots=True)
class HSRNativeControlSnapshot:
    """脚本级的直控就绪诊断，不看任何用户配置。

    ``import_ready``：原生配置文件当前存在（字段名沿用旧契约）。
    ``direct_run_ready``：可执行文件与原生配置文件都存在，直控此刻就能跑。
    """

    engine: HSREngine
    import_ready: bool
    import_reason: str
    direct_run_ready: bool
    direct_run_reason: str

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HSRRunResult:
    status: Literal["completed", "failed", "incomplete", "skipped"]
    summary: str = ""
    error: str = ""
    returncode: int = 0

    @property
    def success(self) -> bool:
        return self.status == "completed"

    @classmethod
    def from_native(
        cls,
        result: Any,
        *,
        default_summary: str,
        default_error: str,
    ) -> "HSRRunResult":
        if bool(getattr(result, "success", False)):
            return cls(
                status="completed",
                summary=str(getattr(result, "output", "") or default_summary),
                returncode=int(getattr(result, "returncode", 0) or 0),
            )
        return cls(
            status="failed",
            error=str(getattr(result, "error", "") or default_error),
            returncode=int(getattr(result, "returncode", 0) or 0),
        )


def _config_value(config: Any, group: str, key: str, default: Any = None) -> Any:
    """Read one value from old-dev ConfigBase or a plain mapping."""

    if config is None:
        return default
    if isinstance(config, dict):
        section = config.get(group)
        if isinstance(section, dict):
            value = section.get(key, default)
            return default if value is None else value
        return default
    try:
        value = config.get(group, key)
    except (AttributeError, KeyError, TypeError):
        value = default
    return default if value is None else value


def _script_path(config: Any, engine: HSREngine) -> str:
    """Resolve an engine root from the old-dev script Info group only."""

    return str(_config_value(config, "Info", f"{engine}Path", "") or "").strip()


def resolve_phase_timeout_minutes(script_config: Any, phase: HSRPhase) -> int:
    """读取某个周期的超时上限（分钟），至少 1 分钟。

    ``script_config`` 为 ``None`` 或字段缺失/非法时回落到默认值，与前端和
    ``RangeValidator(1, 9999)`` 的下界保持一致。
    """

    key, default = PHASE_TIMEOUT_CONFIG[phase]
    raw = _config_value(script_config, "Run", key, default)
    try:
        minutes = int(raw or default)
    except (TypeError, ValueError):
        minutes = default
    return max(1, minutes)


def resolve_script_path(config: Any, engine: HSREngine) -> str:
    """Public path resolver shared by old HSR manager/tools and API adapters."""

    return _script_path(config, engine)


def resolve_configured_engines(config: Any) -> tuple[HSREngine, ...]:
    """Resolve ``effective_engines``: the engines whose root path is configured.

    The capability snapshot, ``HSRManager.check`` and the auto-proxy queue all
    read this one contract, so the engine badge shown by the edit pages stays
    the engine that actually runs.
    """

    return tuple(engine for engine in _HSR_ENGINE_ORDER if _script_path(config, engine))


HSRPlanOwner = Literal["script", "user"]


def resolve_plan_owner(user_config: Any) -> HSRPlanOwner | None:
    """按 ``Info.Mode`` 决定该用户的任务计划挂在谁身上。

    - 「脚本」→ ``"script"``：本脚本下所有脚本来源用户共用 ``HSRConfig`` 上的
      同名组（TaskSwitch / Stage / TaskOpt / Managed.Options / TaskMapping）；
    - 「用户」→ ``"user"``：该用户 ``HSRUserConfig`` 上自己的一份；
    - 「直控」→ ``None``：没有 MAS 计划，原样运行原生配置。

    账号密码、剩余天数、完成态（``Data``）与通知恒按用户，不随 owner 变化。
    非法值由 ``UserDirectConfigModeValidator`` 在加载时纠成「脚本」，这里对
    空值（如未指定用户的接口调用）同样按「脚本」处理。
    """

    mode = str(_config_value(user_config, "Info", "Mode", "") or "").strip()
    if mode == "直控":
        return None
    if mode == "用户":
        return "user"
    return "script"


def resolve_plan(user_config: Any, script_config: Any) -> Any | None:
    """返回该用户实际生效的任务计划对象；直控返回 ``None``。

    两份计划组名、键名完全相同（``declare_hsr_plan_items``），调用方只需把
    返回值当作「读计划键的对象」传下去：读计划键用它，读 ``Info`` / ``Data`` /
    ``Notify`` / ``Control`` 仍用 ``user_config``——脚本配置上没有这些用户键，
    ``ConfigBase.get`` 缺项直接抛 ``AttributeError``，两者不能混用。
    """

    owner = resolve_plan_owner(user_config)
    if owner is None:
        return None
    return script_config if owner == "script" else user_config


def resolve_user_control(
    user_config: Any,
    *,
    script_config: Any | None = None,
) -> "HSRUserControlSettings":
    """Resolve per-user managed/direct mode from ``Info.Mode``.

    ``Info.Mode`` 是唯一的模式轴：「直控」→ ``direct``，「脚本」/「用户」都是
    MAS 托管（区别只在计划 owner，见 :func:`resolve_plan_owner`）。直控跑哪些
    引擎由 ``Control.{engine}`` 决定，一个都没勾时回落到已配置脚本路径的引擎
    （否则会「直控但什么都不跑」）。

    ``Info.IfQuickConfig``：HSR **明确声明不支持快速配置**——SRA/M7A 的原生
    配置由脚本 GUI 维护，MAS 侧托管字段（每日关卡等）的写入深度耦合托管
    运行器（临时配置覆盖而非直接写原生文件），不存在可独立下发的快速配置
    子集，故开关不产生任何行为差异；前端不渲染该开关（死开关）。
    """

    direct = resolve_plan_owner(user_config) is None
    mode: Literal["managed", "direct"] = "direct" if direct else "managed"
    engines: tuple[HSREngine, ...] = tuple(
        engine
        for engine in ("SRA", "M7A")
        if bool(_config_value(user_config, "Control", engine, False))
    )  # type: ignore[assignment]
    if direct and not engines and script_config is not None:
        # 直控但未勾选引擎：回落到「配了脚本路径」的引擎，与脚本管理页展示的
        # effective_engines 同源，避免用户选了直控却什么都不跑。
        engines = resolve_configured_engines(script_config)
    return HSRUserControlSettings(
        mode=mode,
        engines=engines,
        daily_limit_minutes=resolve_phase_timeout_minutes(script_config, "daily"),
        weekly_limit_minutes=resolve_phase_timeout_minutes(script_config, "weekly"),
    )


@dataclass(frozen=True, slots=True)
class HSRUserControlSettings:
    """一个用户的托管/直控设置。

    直控把整份原生配置交给 ``SRA-cli run`` / ``M7A main`` 一次跑完，日常与周常
    没有边界，所以单个引擎的运行上限取脚本「日常 + 周常」两项超时之和，而不是
    托管队列那样按模块分别计时。此前这里写死 120 分钟，用户改超时设置对直控
    完全无效（issue #933）。
    """

    mode: Literal["managed", "direct"]
    engines: tuple[HSREngine, ...]
    daily_limit_minutes: int
    weekly_limit_minutes: int

    @property
    def timeout_minutes(self) -> int:
        return self.daily_limit_minutes + self.weekly_limit_minutes

    @property
    def timeout_seconds(self) -> int:
        return self.timeout_minutes * 60


class SRADirectControlSession:
    """一次 SRA 直控运行：``config_path`` 指向脚本当前的活 profile。"""

    def __init__(self, executable: Path, config_path: Path, log) -> None:
        self._executable = executable
        self._config_path = config_path
        self._log = log
        self._process_registry = SRAProcessRegistry()
        self._closed = False

    async def run(self, timeout_seconds: int) -> HSRRunResult:
        result = await run_sra_config(
            self._executable,
            self._config_path,
            timeout=timeout_seconds,
            process_registry=self._process_registry,
            log_callback=self._log,
        )
        return HSRRunResult.from_native(
            result,
            default_summary="SRA 原生配置执行完成",
            default_error="SRA 原生配置执行失败",
        )

    async def cancel(self) -> None:
        await self._process_registry.terminate_current_process()

    async def close(self) -> None:
        if self._closed:
            return
        await self.cancel()
        await self._process_registry.clear()
        self._closed = True


class SRANativeControlProvider:
    engine: HSREngine = "SRA"

    def _root(self, script_config: Any) -> Path:
        return Path(_script_path(script_config, "SRA"))

    def native_config_path(self, script_config: Any) -> Path:
        """脚本当前选中的 SRA profile 文件，直控直接运行它。"""

        _selected_id, selected_path = resolve_sra_profile(
            script_config,
            config_root=get_sra_app_data_dir() / "configs",
        )
        return selected_path

    def inspect(self, script_config: Any) -> HSRNativeControlSnapshot:
        raw_root = _script_path(script_config, "SRA")
        root = self._root(script_config)
        cli = root / "SRA-cli.exe"
        if not raw_root:
            import_reason = "请先设置 SRA 路径"
            direct_reason = "请先设置 SRA 路径"
        else:
            selected_profile = self.native_config_path(script_config)
            import_reason = ""
            direct_reason = ""
            if not selected_profile.is_file():
                # 直控直接运行这份文件，没有它就跑不了。
                import_reason = f"SRA 原生配置不存在：{selected_profile.stem}"
                direct_reason = (
                    f"SRA 原生配置不存在：{selected_profile}，请先在 SRA 中保存一次设置"
                )
            if not cli.is_file():
                direct_reason = f"SRA 路径中未找到 SRA-cli.exe：{cli}"
        return HSRNativeControlSnapshot(
            engine="SRA",
            import_ready=not import_reason,
            import_reason=import_reason,
            direct_run_ready=not direct_reason,
            direct_run_reason=direct_reason,
        )

    async def open_direct_session(
        self, *, script_config: Any, log
    ) -> SRADirectControlSession:
        root = self._root(script_config)
        executable = root / "SRA-cli.exe"
        if not executable.is_file():
            raise FileNotFoundError(f"SRA 路径中未找到 SRA-cli.exe：{executable}")

        # SRA 的 --inline run 本来就接任意 config 路径，直接指向用户在 SRA GUI
        # 里维护的 profile，不复制、不建临时目录。
        profile_path = self.native_config_path(script_config)
        if not profile_path.is_file():
            raise FileNotFoundError(
                f"SRA 原生配置不存在：{profile_path}，请先在 SRA 中保存一次设置"
            )
        log(
            f"SRA 将直接执行脚本当前的原生配置「{profile_path.stem}」"
            f"（{profile_path}）；MAS 只负责外部进程生命周期"
        )
        return SRADirectControlSession(executable, profile_path, log)


class M7ADirectControlSession:
    """一次三月七直控运行：以真实安装根目录启动，跑三月七 GUI 里的 config.yaml。"""

    def __init__(self, root: Path, log) -> None:
        self._root = root
        self._log = log
        self._runner: M7ARunner | None = None
        self._closed = False

    async def run(self, timeout_seconds: int) -> HSRRunResult:
        self._log(
            f"三月七将直接使用脚本当前的原生配置运行"
            f"（{self._root / 'config.yaml'}）；MAS 只负责外部进程生命周期"
        )
        self._runner = M7ARunner(self._root, log_callback=self._log)
        result = await self._runner.run_task("main", timeout=timeout_seconds)
        return HSRRunResult.from_native(
            result,
            default_summary="三月七原生配置执行完成",
            default_error="三月七原生配置执行失败",
        )

    async def cancel(self) -> None:
        if self._runner is not None:
            await self._runner.terminate_current_process()

    async def close(self) -> None:
        if self._closed:
            return
        await self.cancel()
        self._closed = True


class M7ANativeControlProvider:
    engine: HSREngine = "M7A"

    def _root(self, script_config: Any) -> Path:
        return Path(_script_path(script_config, "M7A"))

    def native_config_path(self, script_config: Any) -> Path:
        """三月七安装根目录下的 config.yaml，直控直接运行它。"""

        return self._root(script_config) / "config.yaml"

    def inspect(self, script_config: Any) -> HSRNativeControlSnapshot:
        raw_root = _script_path(script_config, "M7A")
        root = self._root(script_config)
        executable = root / "March7th Assistant.exe"
        config_path = self.native_config_path(script_config)
        if not raw_root:
            import_reason = "请先设置三月七路径"
            direct_reason = "请先设置三月七路径"
        else:
            import_reason = ""
            direct_reason = ""
            if not config_path.is_file():
                # 直控直接运行这份文件，没有它就跑不了。
                import_reason = f"三月七原生配置不存在：{config_path}"
                direct_reason = (
                    f"三月七原生配置不存在：{config_path}，请先在三月七中保存一次设置"
                )
            if not executable.is_file():
                direct_reason = (
                    f"三月七路径中未找到 March7th Assistant.exe：{executable}"
                )
        return HSRNativeControlSnapshot(
            engine="M7A",
            import_ready=not import_reason,
            import_reason=import_reason,
            direct_run_ready=not direct_reason,
            direct_run_reason=direct_reason,
        )

    async def open_direct_session(
        self, *, script_config: Any, log
    ) -> M7ADirectControlSession:
        root = self._root(script_config)
        executable = root / "March7th Assistant.exe"
        if not executable.is_file():
            raise FileNotFoundError(
                f"三月七路径中未找到 March7th Assistant.exe：{executable}"
            )
        config_path = self.native_config_path(script_config)
        if not config_path.is_file():
            raise FileNotFoundError(
                f"三月七原生配置不存在：{config_path}，请先在三月七中保存一次设置"
            )
        return M7ADirectControlSession(root, log)


def native_provider(engine: str):
    normalized = str(engine or "").strip().upper()
    if normalized == "SRA":
        return SRANativeControlProvider()
    if normalized == "M7A":
        return M7ANativeControlProvider()
    raise ValueError(f"不支持的 HSR 原生引擎：{engine!r}")


__all__ = [
    "HSREngine",
    "HSRNativeControlSnapshot",
    "HSRPlanOwner",
    "HSRRunResult",
    "HSRUserControlSettings",
    "PHASE_TIMEOUT_CONFIG",
    "M7ADirectControlSession",
    "M7ANativeControlProvider",
    "SRADirectControlSession",
    "SRANativeControlProvider",
    "native_provider",
    "resolve_configured_engines",
    "resolve_phase_timeout_minutes",
    "resolve_plan",
    "resolve_plan_owner",
    "resolve_script_path",
    "resolve_user_control",
]
