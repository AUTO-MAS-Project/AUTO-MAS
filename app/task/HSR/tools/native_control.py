"""HSR 原生配置与脚本直控的 old-dev 兼容层。

old-dev 只保存脚本 ``Info.M7APath``/``Info.SRAPath`` 和用户 ``Info`` 凭据。
本模块不启动原生编辑器；provider 仅负责检查、导出/导入快照以及运行直控
会话，外部配置文件的写回由 HSRManager 的备份/恢复区负责。

直控的两种配置来源：

- **活配置（默认）**：``Direct.{engine}Config`` 为空时，直接用脚本当前的原生
  配置运行——SRA 把 ``--inline run`` 指向真实 profile 文件，三月七助手以真实
  安装根目录启动。不建临时目录、不复制任何东西，用户在脚本 GUI 里改什么
  下次就跑什么。这是 ``mas-script-specialized-adapter`` 里「直控＝直接使用
  脚本原有配置、由原生 GUI 维护」的口径。
- **快照（可选覆盖）**：用户显式导入过快照时，把快照写进隔离目录再运行，
  只服务「一个脚本挂多个游戏账号、各 MAS 用户要跑不同计划」的场景。快照
  冻结在导入那一刻，不跟随脚本里的后续改动。
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from app.utils.io import atomic_write

from .m7a_runtime import M7ARunner
from .sra_runtime import (
    SRAProcessRegistry,
    get_sra_app_data_dir,
    resolve_sra_profile,
    run_sra_config,
)

HSREngine = Literal["SRA", "M7A"]

# 引擎回落顺序与 HSRTaskModule.supported_scripts 保持一致
_HSR_ENGINE_ORDER: tuple[HSREngine, ...] = ("M7A", "SRA")


@dataclass(frozen=True, slots=True)
class HSRNativeControlSnapshot:
    """脚本级的直控就绪诊断，不看任何用户配置。

    ``import_ready``：原生配置文件当前存在，可以把它固定成用户快照。
    ``direct_run_ready``：可执行文件与原生配置文件都存在，未导入快照的用户
    此刻就能按活配置跑。已导入快照的用户不受原生配置缺失影响，那一层判断
    在 ``HSRManager.check`` 里按用户做。
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
    native_result: Any = None

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
                native_result=result,
            )
        return cls(
            status="failed",
            error=str(getattr(result, "error", "") or default_error),
            returncode=int(getattr(result, "returncode", 0) or 0),
            native_result=result,
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


def resolve_user_control(
    user_config: Any,
    *,
    script_config: Any | None = None,
) -> "HSRUserControlSettings":
    """Resolve per-user managed/direct mode, accepting old ConfigBase records."""

    raw_mode = str(_config_value(user_config, "Control", "Mode", "managed"))
    mode: Literal["managed", "direct"] = (
        "direct" if raw_mode.strip().lower() == "direct" else "managed"
    )
    engines: tuple[HSREngine, ...] = tuple(
        engine
        for engine in ("SRA", "M7A")
        if bool(_config_value(user_config, "Control", engine, False))
    )  # type: ignore[assignment]
    return HSRUserControlSettings(
        mode=mode,
        engines=engines,
        timeout_seconds=120 * 60,
    )


@dataclass(frozen=True, slots=True)
class HSRUserControlSettings:
    mode: Literal["managed", "direct"]
    engines: tuple[HSREngine, ...]
    timeout_seconds: int


def get_user_direct_config(user_config: Any, engine: HSREngine) -> str:
    """Return one imported native snapshot without logging its contents.

    空串表示该用户没有快照，直控按活配置运行。
    """

    value = _config_value(user_config, "Direct", f"{engine}Config", "")
    return str(value or "")


def has_user_direct_snapshot(user_config: Any, engine: HSREngine) -> bool:
    """该用户是否为此引擎导入过快照（决定直控走隔离快照还是活配置）。"""

    return bool(get_user_direct_config(user_config, engine).strip())


def _discard_isolated_root(isolated_root: Path | None) -> None:
    """尽力删除隔离启动目录。

    外部脚本被中止后可能仍占用目录内的文件句柄，删除隔离目录只是收尾动作，
    失败时把目录留给系统临时目录回收，不应让整个用户任务失败。
    """

    if isolated_root is not None:
        shutil.rmtree(isolated_root, ignore_errors=True)


class SRADirectControlSession:
    """一次 SRA 直控运行。

    ``isolated_root`` 为 ``None`` 表示 ``config_path`` 指向脚本当前的活 profile，
    收尾时没有任何目录要清；非 ``None`` 时 ``config_path`` 是写在隔离目录里的
    用户快照，``close()`` 会尽力删掉整个目录。
    """

    def __init__(
        self,
        executable: Path,
        config_path: Path,
        isolated_root: Path | None,
        log,
    ) -> None:
        self._executable = executable
        self._config_path = config_path
        self._isolated_root: Path | None = isolated_root
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
        _discard_isolated_root(self._isolated_root)
        self._isolated_root = None
        self._closed = True


class SRANativeControlProvider:
    engine: HSREngine = "SRA"

    def _root(self, script_config: Any) -> Path:
        return Path(_script_path(script_config, "SRA"))

    def native_config_path(self, script_config: Any) -> Path:
        """脚本当前选中的 SRA profile 文件；活配置直控与快照导入都读它。"""

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
                # 活配置直控和快照导入都要读这份文件；没有它两条路都走不通。
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

    def export_config(self, script_config: Any) -> tuple[Path, str]:
        selected_path = self.native_config_path(script_config)
        if not selected_path.is_file():
            raise RuntimeError(f"SRA 原生配置不存在：{selected_path.stem}")
        content = selected_path.read_text(encoding="utf-8-sig")
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError(f"SRA 原生配置顶层必须是对象：{selected_path}")
        return selected_path, content

    async def open_direct_session(
        self, *, script_config: Any, config_content: str, session_id: str, log
    ) -> SRADirectControlSession:
        root = self._root(script_config)
        executable = root / "SRA-cli.exe"
        if not executable.is_file():
            raise FileNotFoundError(f"SRA 路径中未找到 SRA-cli.exe：{executable}")

        if not config_content.strip():
            # 活配置：SRA 的 --inline run 本来就接任意 config 路径，直接指向
            # 用户在 SRA GUI 里维护的 profile，不复制、不建临时目录。
            profile_path = self.native_config_path(script_config)
            if not profile_path.is_file():
                raise FileNotFoundError(
                    f"SRA 原生配置不存在：{profile_path}，"
                    "请先在 SRA 中保存一次设置，或为该用户导入配置快照"
                )
            log(
                f"SRA 将直接执行脚本当前的原生配置「{profile_path.stem}」"
                f"（{profile_path}）；MAS 只负责外部进程生命周期"
            )
            return SRADirectControlSession(executable, profile_path, None, log)

        try:
            parsed = json.loads(config_content)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"SRA 用户快照不是有效 JSON：{exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("SRA 用户快照顶层必须是对象")
        safe_id = re.sub(r"[^A-Za-z0-9_-]+", "-", session_id).strip("-") or "user"
        isolated_root = Path(tempfile.mkdtemp(prefix=f"automas-sra-{safe_id[:32]}-"))
        config_path = isolated_root / "config.json"
        atomic_write(config_path, config_content.encode("utf-8"))
        log(
            "SRA 将原样执行当前用户导入的隔离配置快照（不跟随 SRA 中的后续改动）；"
            "MAS 只负责外部进程生命周期"
        )
        return SRADirectControlSession(executable, config_path, isolated_root, log)


class M7ADirectControlSession:
    """一次三月七助手直控运行。

    ``config_content`` 为空时直接以真实安装根目录启动，跑的就是用户在助手
    GUI 里维护的 ``config.yaml``；非空时才建隔离目录、把快照写成
    ``config.yaml`` 后以隔离目录为根启动。
    """

    def __init__(self, root: Path, config_content: str, session_id: str, log) -> None:
        self._source_root = root
        self._config_content = config_content
        self._session_id = session_id
        self._log = log
        self._isolated_root: Path | None = None
        self._runner: M7ARunner | None = None
        self._closed = False

    def _create_isolated_root(self) -> Path:
        try:
            config = yaml.safe_load(self._config_content) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"三月七助手用户快照不是有效 YAML：{exc}") from exc
        if not isinstance(config, dict):
            raise ValueError("三月七助手用户快照顶层必须是对象")
        safe_id = re.sub(r"[^A-Za-z0-9_-]+", "-", self._session_id).strip("-") or "user"
        isolated_root = Path(tempfile.mkdtemp(prefix=f"automas-m7a-{safe_id[:32]}-"))
        self._isolated_root = isolated_root
        try:
            for source in self._source_root.iterdir():
                if source.name.casefold() == "config.yaml":
                    continue
                target = isolated_root / source.name
                if source.is_dir():
                    try:
                        target.symlink_to(source.resolve(), target_is_directory=True)
                    except OSError:
                        shutil.copytree(source, target)
                elif source.is_file():
                    shutil.copy2(source, target)
            atomic_write(
                isolated_root / "config.yaml", self._config_content.encode("utf-8")
            )
        except Exception:
            self._isolated_root = None
            _discard_isolated_root(isolated_root)
            raise
        return isolated_root

    @property
    def uses_snapshot(self) -> bool:
        return bool(self._config_content.strip())

    async def run(self, timeout_seconds: int) -> HSRRunResult:
        if self.uses_snapshot:
            run_root = self._create_isolated_root()
            self._log(
                "三月七助手将从隔离启动目录原样读取当前用户导入的 config.yaml 快照"
                "（不跟随助手中的后续改动）；MAS 只负责外部进程生命周期"
            )
        else:
            run_root = self._source_root
            self._log(
                f"三月七助手将直接使用脚本当前的原生配置运行"
                f"（{run_root / 'config.yaml'}）；MAS 只负责外部进程生命周期"
            )
        self._runner = M7ARunner(run_root, log_callback=self._log)
        result = await self._runner.run_task("main", timeout=timeout_seconds)
        return HSRRunResult.from_native(
            result,
            default_summary="三月七助手原生配置执行完成",
            default_error="三月七助手原生配置执行失败",
        )

    async def cancel(self) -> None:
        if self._runner is not None:
            await self._runner.terminate_current_process()

    async def close(self) -> None:
        if self._closed:
            return
        await self.cancel()
        _discard_isolated_root(self._isolated_root)
        self._isolated_root = None
        self._closed = True


class M7ANativeControlProvider:
    engine: HSREngine = "M7A"

    def _root(self, script_config: Any) -> Path:
        return Path(_script_path(script_config, "M7A"))

    def native_config_path(self, script_config: Any) -> Path:
        """三月七助手安装根目录下的 config.yaml；活配置直控与快照导入都读它。"""

        return self._root(script_config) / "config.yaml"

    def inspect(self, script_config: Any) -> HSRNativeControlSnapshot:
        raw_root = _script_path(script_config, "M7A")
        root = self._root(script_config)
        executable = root / "March7th Assistant.exe"
        config_path = self.native_config_path(script_config)
        if not raw_root:
            import_reason = "请先设置三月七助手路径"
            direct_reason = "请先设置三月七助手路径"
        else:
            import_reason = ""
            direct_reason = ""
            if not config_path.is_file():
                # 活配置直控和快照导入都要读这份文件；没有它两条路都走不通。
                import_reason = f"三月七助手原生配置不存在：{config_path}"
                direct_reason = (
                    f"三月七助手原生配置不存在：{config_path}，"
                    "请先在三月七助手中保存一次设置"
                )
            if not executable.is_file():
                direct_reason = (
                    f"三月七助手路径中未找到 March7th Assistant.exe：{executable}"
                )
        return HSRNativeControlSnapshot(
            engine="M7A",
            import_ready=not import_reason,
            import_reason=import_reason,
            direct_run_ready=not direct_reason,
            direct_run_reason=direct_reason,
        )

    def export_config(self, script_config: Any) -> tuple[Path, str]:
        path = self.native_config_path(script_config)
        if not path.is_file():
            raise RuntimeError(f"三月七助手原生配置不存在：{path}")
        content = path.read_text(encoding="utf-8-sig")
        parsed = yaml.safe_load(content) or {}
        if not isinstance(parsed, dict):
            raise ValueError(f"三月七助手原生配置顶层必须是对象：{path}")
        return path, content

    async def open_direct_session(
        self, *, script_config: Any, config_content: str, session_id: str, log
    ) -> M7ADirectControlSession:
        root = self._root(script_config)
        executable = root / "March7th Assistant.exe"
        if not executable.is_file():
            raise FileNotFoundError(
                f"三月七助手路径中未找到 March7th Assistant.exe：{executable}"
            )
        if not config_content.strip():
            # 活配置：以真实安装根目录启动 main，跑的就是助手 GUI 里的 config.yaml。
            config_path = self.native_config_path(script_config)
            if not config_path.is_file():
                raise FileNotFoundError(
                    f"三月七助手原生配置不存在：{config_path}，"
                    "请先在三月七助手中保存一次设置，或为该用户导入配置快照"
                )
        return M7ADirectControlSession(root, config_content, session_id, log)


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
    "HSRRunResult",
    "HSRUserControlSettings",
    "M7ADirectControlSession",
    "M7ANativeControlProvider",
    "SRADirectControlSession",
    "SRANativeControlProvider",
    "get_user_direct_config",
    "has_user_direct_snapshot",
    "native_provider",
    "resolve_configured_engines",
    "resolve_script_path",
    "resolve_user_control",
]
