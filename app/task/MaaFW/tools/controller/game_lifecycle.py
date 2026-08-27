"""Safe PC-game launch, detection, and cleanup for MaaFW desktop controllers.

The launch target and the client used for readiness detection are deliberately
separate.  Cleanup only uses process identities captured by this module; a
configured process name is never used as a global kill selector.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import sys
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import psutil

GameLaunchMode = Literal["AttachOnly", "DirectExe", "LauncherExe", "URL"]
_MODES = {"AttachOnly", "DirectExe", "LauncherExe", "URL"}
_URL_SCHEMES = {
    "http",
    "https",
    "steam",
    "steamlink",
    "com.epicgames.launcher",
    "battlenet",
    "blizzard",
    "ms-windows-store",
    "wegame",
}


@dataclass(frozen=True)
class MaaFWGameLaunchSpec:
    mode: GameLaunchMode
    launch_path: Path | None = None
    launch_url: str = ""
    arguments: tuple[str, ...] = ()
    process_path: Path | None = None
    process_name: str = ""
    wait_time: int = 60
    close_on_finish: bool = True
    legacy_path: Path | None = None

    @property
    def detection_path(self) -> Path | None:
        if self.process_path is not None:
            return self.process_path
        if self.process_name:
            return None
        return self.launch_path if self.mode == "DirectExe" else None


@dataclass
class MaaFWOwnedGameProcess:
    """Identity of a process started by this MAS invocation."""

    pid: int
    create_time: float
    executable: str = ""
    descendants: set[tuple[int, float]] = field(default_factory=set)
    url_launch: bool = False
    client_identity: tuple[int, float] | None = None
    preexisting: set[tuple[int, float]] = field(default_factory=set)


def _get(config: Any, group: str, name: str, default: Any = None) -> Any:
    try:
        return config.get(group, name)
    except (AttributeError, KeyError, TypeError):
        return default


def _path(value: Any) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return Path(raw)


def _args(value: Any) -> tuple[str, ...]:
    raw = str(value or "").strip()
    if not raw:
        return ()
    try:
        return tuple(shlex.split(raw, posix=False))
    except ValueError as exc:
        raise ValueError(f"游戏启动参数无法解析: {exc}") from exc


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def resolve_game_launch_spec(config: Any) -> MaaFWGameLaunchSpec:
    """Resolve Config v1 fields, accepting legacy ``Game.Path`` on read."""

    legacy = _path(_get(config, "Game", "Path", ""))
    launch_path = _path(_get(config, "Game", "LaunchPath", ""))
    launch_url = str(_get(config, "Game", "LaunchURL", "") or "").strip()
    process_path = _path(_get(config, "Game", "ProcessPath", ""))
    process_name = str(_get(config, "Game", "ProcessName", "") or "").strip()
    raw_mode = str(_get(config, "Game", "LaunchMode", "") or "").strip()

    # A v1 record has no LaunchMode/LaunchPath.  A legacy Path is an explicit
    # direct executable target; otherwise the new default is attach-only.
    if raw_mode not in _MODES:
        raw_mode = "DirectExe" if legacy is not None else "AttachOnly"
    # ConfigBase supplies the new default ``AttachOnly`` even for an old
    # record.  Only infer DirectExe when there is no new exact client selector;
    # an explicitly configured AttachOnly + ProcessPath/ProcessName must win.
    if (
        raw_mode == "AttachOnly"
        and launch_path is None
        and legacy is not None
        and not (process_path or process_name)
    ):
        raw_mode = "DirectExe"

    return MaaFWGameLaunchSpec(
        mode=raw_mode,  # type: ignore[arg-type]
        launch_path=launch_path or (legacy if raw_mode == "DirectExe" else None),
        launch_url=launch_url,
        arguments=_args(_get(config, "Game", "Arguments", "")),
        process_path=process_path,
        process_name=process_name,
        wait_time=max(0, int(_get(config, "Game", "WaitTime", 60) or 0)),
        close_on_finish=_bool(_get(config, "Game", "CloseOnFinish", True), True),
        legacy_path=legacy,
    )


def validate_game_launch_spec(spec: MaaFWGameLaunchSpec) -> None:
    if spec.mode in {"DirectExe", "LauncherExe"}:
        if spec.launch_path is None or not spec.launch_path.is_file():
            raise ValueError("MaaFW PC 启动模式需要有效的 LaunchPath")
    elif spec.mode == "URL":
        parsed = urlsplit(spec.launch_url)
        if (
            not spec.launch_url
            or parsed.scheme.casefold() not in _URL_SCHEMES
            or any(char in spec.launch_url for char in "\r\n\x00")
            or (
                parsed.scheme.casefold() in {"http", "https"}
                and not parsed.hostname
            )
        ):
            raise ValueError("MaaFW URL 启动模式需要有效的 LaunchURL")
    if spec.mode in {"AttachOnly", "LauncherExe", "URL"} and not (
        spec.process_path or spec.process_name
    ):
        raise ValueError(
            f"MaaFW {spec.mode} 模式必须配置 ProcessPath 或 ProcessName 用于精确检测客户端"
        )


def _same_process(proc: psutil.Process, identity: tuple[int, float]) -> bool:
    try:
        return proc.pid == identity[0] and abs(proc.create_time() - identity[1]) < 1.0
    except (psutil.Error, OSError):
        return False


def _snapshot_descendants(root: psutil.Process) -> set[tuple[int, float]]:
    result: set[tuple[int, float]] = set()
    try:
        children = root.children(recursive=True)
    except (psutil.Error, OSError):
        return result
    for child in children:
        try:
            result.add((child.pid, child.create_time()))
        except (psutil.Error, OSError):
            continue
    return result


def snapshot_matching_processes(spec: MaaFWGameLaunchSpec) -> set[tuple[int, float]]:
    """Capture exact identities before launch to reject pre-existing clients."""

    result: set[tuple[int, float]] = set()
    for proc in psutil.process_iter(["pid", "name", "exe", "create_time"]):
        if process_matches_spec(proc, spec):
            try:
                result.add((proc.pid, proc.create_time()))
            except (psutil.Error, OSError):
                continue
    return result


async def launch_game(
    spec: MaaFWGameLaunchSpec,
    *,
    preexisting: set[tuple[int, float]] | None = None,
) -> MaaFWOwnedGameProcess | None:
    """Start only the configured target and return an attributable identity."""

    validate_game_launch_spec(spec)
    if spec.mode == "AttachOnly":
        return None
    if spec.mode == "URL":
        if sys.platform != "win32":
            raise RuntimeError("MaaFW URL 游戏启动仅支持 Win32 系统协议处理")
        await asyncio.to_thread(os.startfile, spec.launch_url)  # type: ignore[attr-defined]
        # Protocol handlers are external applications.  They are intentionally
        # not guessed or killed on task completion.
        return MaaFWOwnedGameProcess(
            0,
            0.0,
            url_launch=True,
            preexisting=set(preexisting or ()),
        )

    assert spec.launch_path is not None
    process = await asyncio.create_subprocess_exec(
        str(spec.launch_path),
        *spec.arguments,
        cwd=str(spec.launch_path.parent),
        creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
    )
    try:
        create_time = await asyncio.to_thread(
            lambda: psutil.Process(process.pid).create_time()
        )
    except (psutil.Error, OSError) as exc:
        with suppress(Exception):
            process.terminate()
        raise RuntimeError("MaaFW 启动目标进程身份无法确认，已拒绝继续") from exc
    identity = MaaFWOwnedGameProcess(
        pid=process.pid,
        create_time=create_time,
        executable=str(spec.launch_path),
        preexisting=set(preexisting or ()),
    )
    # LauncherExe may spawn the client asynchronously; descendants are added
    # again by ``refresh_owned_descendants`` before cleanup.
    try:
        identity.descendants.update(_snapshot_descendants(psutil.Process(process.pid)))
    except (psutil.Error, OSError):
        pass
    return identity


def refresh_owned_descendants(identity: MaaFWOwnedGameProcess | None) -> None:
    if identity is None or identity.url_launch or identity.pid <= 0:
        return
    try:
        root = psutil.Process(identity.pid)
    except (psutil.Error, OSError):
        return
    identity.descendants.update(_snapshot_descendants(root))


def process_matches_spec(proc: psutil.Process, spec: MaaFWGameLaunchSpec) -> bool:
    # When both selectors are present they are constraints, not alternatives:
    # accepting a same-named executable from another directory would defeat
    # the ownership and pre-launch snapshot guarantees.
    try:
        if spec.process_path is not None:
            raw_executable = proc.exe()
            if not raw_executable:
                return False
            executable = Path(raw_executable).resolve()
            if executable != spec.process_path:
                return False
    except (psutil.Error, OSError, RuntimeError, TypeError, ValueError):
        return False
    if spec.process_name:
        try:
            process_name = str(proc.name() or "")
            if process_name.casefold() != spec.process_name.casefold():
                return False
        except (psutil.Error, OSError, TypeError, ValueError):
            return False
    return spec.process_path is not None or bool(spec.process_name)


def find_client_process(spec: MaaFWGameLaunchSpec) -> psutil.Process | None:
    for proc in psutil.process_iter(["pid", "name", "exe", "create_time"]):
        if process_matches_spec(proc, spec):
            return proc
    return None


def wait_for_client(
    spec: MaaFWGameLaunchSpec,
    timeout: float,
    *,
    preexisting: set[tuple[int, float]] | None = None,
    poll_interval: float = 0.25,
) -> psutil.Process | None:
    """Poll exact path/name and return the newly observed client identity."""

    excluded = preexisting or set()
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        for proc in psutil.process_iter(["pid", "name", "exe", "create_time"]):
            if not process_matches_spec(proc, spec):
                continue
            try:
                identity = (proc.pid, proc.create_time())
            except (psutil.Error, OSError):
                continue
            if identity not in excluded:
                return proc
        if time.monotonic() >= deadline:
            return None
        time.sleep(min(poll_interval, max(0.01, deadline - time.monotonic())))


def close_owned_game(identity: MaaFWOwnedGameProcess | None, *, timeout: float = 5.0) -> bool:
    """Terminate only processes whose PID/create-time identity we captured."""

    if identity is None or identity.url_launch or identity.pid <= 0:
        return False
    refresh_owned_descendants(identity)
    identities = sorted(identity.descendants, key=lambda item: item[0], reverse=True)
    if identity.client_identity and identity.client_identity not in identity.preexisting:
        identities.append(identity.client_identity)
    identities.append((identity.pid, identity.create_time))
    closed = False
    for pid, create_time in identities:
        try:
            proc = psutil.Process(pid)
            if not _same_process(proc, (pid, create_time)):
                continue
            proc.terminate()
            closed = True
        except (psutil.Error, OSError):
            continue
    deadline = time.monotonic() + timeout
    while closed and time.monotonic() < deadline:
        alive = False
        for pid, create_time in identities:
            try:
                proc = psutil.Process(pid)
                if _same_process(proc, (pid, create_time)) and proc.is_running():
                    alive = True
                    break
            except (psutil.Error, OSError):
                continue
        if not alive:
            break
        time.sleep(0.05)
    return closed
