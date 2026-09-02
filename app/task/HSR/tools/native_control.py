"""HSR 原生配置与脚本直控的 old-dev 兼容层。

old-dev 只保存脚本 ``Info.M7APath``/``Info.SRAPath`` 和用户 ``Info`` 凭据。
本模块不启动原生编辑器；provider 仅负责检查、导出/导入快照以及运行直控
会话，外部配置文件的写回由 HSRManager 的备份/恢复区负责。
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
    """Return one imported native snapshot without logging its contents."""

    value = _config_value(user_config, "Direct", f"{engine}Config", "")
    return str(value or "")


def _discard_isolated_root(isolated_root: Path | None) -> None:
    """尽力删除隔离启动目录。

    外部脚本被中止后可能仍占用目录内的文件句柄，删除隔离目录只是收尾动作，
    失败时把目录留给系统临时目录回收，不应让整个用户任务失败。
    """

    if isolated_root is not None:
        shutil.rmtree(isolated_root, ignore_errors=True)


class SRADirectControlSession:
    def __init__(
        self, executable: Path, config_path: Path, isolated_root: Path, log
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

    def inspect(self, script_config: Any) -> HSRNativeControlSnapshot:
        raw_root = _script_path(script_config, "SRA")
        root = self._root(script_config)
        cli = root / "SRA-cli.exe"
        config_root = get_sra_app_data_dir() / "configs"
        if not raw_root:
            import_reason = "请先设置 SRA 路径"
            direct_reason = "请先设置 SRA 路径"
        else:
            selected_id, selected_profile = resolve_sra_profile(
                script_config,
                config_root=config_root,
            )
            import_reason = ""
            if not selected_profile.is_file():
                import_reason = f"SRA 原生配置不存在：{selected_id}"
            if not cli.is_file():
                direct_reason = f"SRA 路径中未找到 SRA-cli.exe：{cli}"
            else:
                direct_reason = ""
        return HSRNativeControlSnapshot(
            engine="SRA",
            import_ready=not import_reason,
            import_reason=import_reason,
            direct_run_ready=not direct_reason,
            direct_run_reason=direct_reason,
        )

    def export_config(self, script_config: Any) -> tuple[Path, str]:
        config_root = get_sra_app_data_dir() / "configs"
        _selected_id, selected_path = resolve_sra_profile(
            script_config,
            config_root=config_root,
        )
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
        log("SRA 将原样执行当前用户导入的隔离配置快照；MAS 只负责外部进程生命周期")
        return SRADirectControlSession(executable, config_path, isolated_root, log)


class M7ADirectControlSession:
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

    async def run(self, timeout_seconds: int) -> HSRRunResult:
        isolated_root = self._create_isolated_root()
        self._runner = M7ARunner(isolated_root, log_callback=self._log)
        self._log(
            "三月七助手将从隔离启动目录原样读取当前用户 config.yaml；MAS 只负责外部进程生命周期"
        )
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

    def inspect(self, script_config: Any) -> HSRNativeControlSnapshot:
        raw_root = _script_path(script_config, "M7A")
        root = self._root(script_config)
        executable = root / "March7th Assistant.exe"
        config_path = root / "config.yaml"
        if not raw_root:
            import_reason = "请先设置三月七助手路径"
            direct_reason = "请先设置三月七助手路径"
        else:
            import_reason = (
                ""
                if config_path.is_file()
                else f"三月七助手原生配置不存在：{config_path}"
            )
            if not executable.is_file():
                direct_reason = (
                    f"三月七助手路径中未找到 March7th Assistant.exe：{executable}"
                )
            else:
                direct_reason = ""
        return HSRNativeControlSnapshot(
            engine="M7A",
            import_ready=not import_reason,
            import_reason=import_reason,
            direct_run_ready=not direct_reason,
            direct_run_reason=direct_reason,
        )

    def export_config(self, script_config: Any) -> tuple[Path, str]:
        path = self._root(script_config) / "config.yaml"
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
            raise ValueError("当前用户尚未导入三月七助手 config.yaml 快照")
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
    "native_provider",
    "resolve_configured_engines",
    "resolve_script_path",
    "resolve_user_control",
]
