from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.task.MaaFW.tools.core.automas_maafw_interface.models import MaaFWAgent

from .models import MaaFWAgentCommandPlan


class MaaFWAgentEnvError(RuntimeError):
    """Raised when MaaFW agent command plans or environments are invalid."""


def build_maafw_agent_command_plans(
    base_dir: str | Path,
    raw_agent: MaaFWAgent
    | list[MaaFWAgent]
    | dict[str, Any]
    | list[dict[str, Any]]
    | None,
    *,
    managed_env_root: str | Path | None = None,
) -> list[MaaFWAgentCommandPlan]:
    resolved_base_dir = Path(base_dir).resolve()
    agent_configs = _coerce_agent_configs(raw_agent)
    return [
        _build_agent_command_plan(
            resolved_base_dir,
            agent_config,
            managed_env_root=managed_env_root,
        )
        for agent_config in agent_configs
    ]


def compute_isolated_venv_path(
    base_dir: str | Path,
    *,
    managed_env_root: str | Path | None = None,
) -> Path:
    resolved_base_dir = Path(base_dir).resolve()
    key = str(resolved_base_dir)
    if os.name == "nt":
        key = key.lower()
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    root = (
        Path(managed_env_root)
        if managed_env_root is not None
        else Path.cwd() / "config" / "maafw_agent_venvs"
    )
    return root.resolve() / f"maafw_venv_{digest}"


AGENT_VENV_DIR_PREFIX = "maafw_venv_"


def collect_orphan_agent_venvs(
    root: str | Path,
    live_project_paths: Iterable[str | Path],
) -> list[Path]:
    """列出已无脚本引用的隔离 venv。

    目录名就是项目路径的哈希（见 ``compute_isolated_venv_path``），所以判定
    孤儿不需要读目录内的清单：把所有仍被脚本引用的项目路径算成目录名，
    剩下的即孤儿。这样即使清单损坏或缺失也不会误判，而**存活项目的 venv
    永远不会落进结果里**——这是这个实现最重要的性质。

    覆盖三种情形：用户删了脚本、改了项目路径、项目升级换了目录
    （实测残留过一份指向 ``Maa_bbb-win-x86_64-v1.12.10`` 的 venv，
    而用户早已升到 v1.12.14）。
    """

    root_path = Path(root).resolve()
    expected = {
        compute_isolated_venv_path(path, managed_env_root=root_path).name
        for path in live_project_paths
    }
    try:
        entries = sorted(root_path.iterdir())
    except OSError:
        return []
    return [
        entry
        for entry in entries
        if entry.is_dir()
        and entry.name.startswith(AGENT_VENV_DIR_PREFIX)
        and entry.name not in expected
    ]


def venv_python_exe(venv_path: str | Path) -> Path:
    path = Path(venv_path)
    if os.name == "nt":
        return path / "Scripts" / "python.exe"
    return path / "bin" / "python"


def venv_base_python_missing(venv_path: str | Path) -> bool:
    """venv 自己的文件都在，但 pyvenv.cfg 里 home 指向的基解释器已经不存在。

    venv 的 python.exe（Windows 上）在启动时要靠 pyvenv.cfg 的 home 才能定位
    标准库/DLL 所在目录，不是自包含的——home 目录被删掉后 venv 会静默失效，
    即使 venv 自己的文件一个没少。这种情况出现在：引导用的基解释器本身是另
    一个 venv（比如受管模式下落到 sys.executable 的那个监督器管理的
    venv），而它之后被整个删掉重建过。

    home 行缺失或读不出时不判定失效，交给调用方已有的结构完整性检查处理。
    """

    try:
        text = (Path(venv_path) / "pyvenv.cfg").read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return False

    home: str | None = None
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip().casefold() == "home":
            home = value.strip()
    if not home:
        return False

    exe_name = "python.exe" if os.name == "nt" else "python"
    return not (Path(home) / exe_name).is_file()


def _coerce_agent_configs(
    raw_agent: MaaFWAgent
    | list[MaaFWAgent]
    | dict[str, Any]
    | list[dict[str, Any]]
    | None,
) -> list[MaaFWAgent]:
    if raw_agent is None:
        return []
    if isinstance(raw_agent, (list, tuple)):
        return [_coerce_single_agent(item) for item in raw_agent]
    return [_coerce_single_agent(raw_agent)]


def _coerce_single_agent(item: Any) -> MaaFWAgent:
    # 不用 isinstance(item, MaaFWAgent) 直接判定：dev HMR 会重载
    # automas_maafw_interface.models，使得缓存 interface 携带的旧 MaaFWAgent
    # 类与本模块 import 的新类实例判定失败。改为按 dict / 任意 pydantic 模型
    # 归一化（与 runner._coerce_interface 的 model_dump 兜底同源）。
    if isinstance(item, MaaFWAgent):
        return item
    if isinstance(item, dict):
        return MaaFWAgent.model_validate(item)
    if hasattr(item, "model_dump"):
        return MaaFWAgent.model_validate(item.model_dump())
    raise MaaFWAgentEnvError("agent declaration must be an object or list")


def _build_agent_command_plan(
    base_dir: Path,
    agent_config: MaaFWAgent,
    *,
    managed_env_root: str | Path | None,
) -> MaaFWAgentCommandPlan:
    child_args = [
        _replace_project_dir(arg, base_dir) for arg in agent_config.child_args or []
    ]
    embedded_requested = agent_config.embedded is True
    executable = _resolve_executable(
        base_dir,
        agent_config.child_exec,
        child_args=child_args,
        managed_env_root=managed_env_root,
    )
    if (
        embedded_requested
        and executable["runtime_kind"] != "project_binary"
        and not _has_python_entry_arg(child_args)
    ):
        child_args = ["-u", str((base_dir / "agent" / "main.py").resolve())]

    fallback_reason = executable["fallback_reason"]
    if embedded_requested:
        isolation_reason = (
            "embedded agent 已切换为隔离子进程，避免污染 AUTO-MAS 主进程 Python 环境"
        )
        fallback_reason = (
            f"{isolation_reason}; {fallback_reason}"
            if fallback_reason
            else isolation_reason
        )

    command = [executable["command"], *child_args, "<socket_id>"]
    return MaaFWAgentCommandPlan(
        childExec=agent_config.child_exec,
        executable=executable["command"],
        executableExists=executable["exists"],
        fallbackReason=fallback_reason,
        runtimeKind=executable["runtime_kind"],
        isolatedVenvPath=executable["isolated_venv_path"],
        childArgs=child_args,
        command=command,
        cwd=str(base_dir),
        identifier=agent_config.identifier,
        embedded=False,
    )


def _resolve_executable(
    base_dir: Path,
    child_exec: str,
    *,
    child_args: list[str],
    managed_env_root: str | Path | None,
) -> dict[str, Any]:
    replaced = _replace_project_dir(child_exec, base_dir)
    if not _looks_like_project_path(replaced):
        return {
            "command": replaced,
            "exists": None,
            "fallback_reason": None,
            "runtime_kind": "external",
            "isolated_venv_path": None,
        }

    resolved_path = _resolve_project_executable_path(base_dir, replaced)
    if resolved_path.is_file():
        return {
            "command": str(resolved_path),
            "exists": True,
            "fallback_reason": None,
            "runtime_kind": _classify_existing_project_executable(resolved_path),
            "isolated_venv_path": None,
        }

    if _is_bundled_python_pattern(child_exec, child_args, base_dir):
        venv_path = compute_isolated_venv_path(
            base_dir,
            managed_env_root=managed_env_root,
        )
        venv_python = venv_python_exe(venv_path)
        return {
            "command": str(venv_python),
            "exists": venv_python.exists(),
            "fallback_reason": (
                f"项目声明的解释器不存在: {resolved_path}，"
                f"将使用该项目专属隔离 venv: {venv_path}"
            ),
            "runtime_kind": "isolated_venv",
            "isolated_venv_path": str(venv_path),
        }

    return {
        "command": str(resolved_path),
        "exists": False,
        "fallback_reason": f"声明的可执行文件不存在: {resolved_path}",
        "runtime_kind": "external",
        "isolated_venv_path": None,
    }


def _resolve_project_executable_path(base_dir: Path, raw_path: str) -> Path:
    resolved_path = _resolve_project_path(base_dir, raw_path)
    if resolved_path.exists() or os.name != "nt" or resolved_path.suffix:
        return resolved_path

    exe_candidate = resolved_path.with_suffix(".exe")
    if (
        _is_within_base_dir(exe_candidate.resolve(), base_dir)
        and exe_candidate.is_file()
    ):
        return exe_candidate.resolve()
    return resolved_path


def _classify_existing_project_executable(resolved_path: Path) -> str:
    if resolved_path.name.lower() in {"python", "python.exe", "pythonw", "pythonw.exe"}:
        return "project_python"
    return "project_binary"


def _is_bundled_python_pattern(
    child_exec: str,
    child_args: list[str],
    base_dir: Path,
) -> bool:
    normalized = child_exec.replace("\\", "/").lower()
    if not normalized.endswith("python/python.exe"):
        return False

    python_entries = [
        str(arg) for arg in child_args if str(arg).lower().endswith(".py")
    ]
    if python_entries:
        return any(
            _is_safe_existing_python_entry(base_dir, entry) for entry in python_entries
        )
    return (base_dir / "agent" / "main.py").is_file()


def _is_safe_existing_python_entry(base_dir: Path, raw_path: str) -> bool:
    try:
        resolved_path = _resolve_project_path(base_dir, raw_path)
    except MaaFWAgentEnvError:
        return False
    return resolved_path.is_file() and resolved_path.suffix.lower() == ".py"


def _replace_project_dir(value: str, base_dir: Path) -> str:
    return value.replace("{PROJECT_DIR}", str(base_dir))


def _has_python_entry_arg(child_args: list[str]) -> bool:
    return any(str(arg).lower().endswith(".py") for arg in child_args)


def _looks_like_project_path(value: str) -> bool:
    if value.startswith("."):
        return True
    if "/" in value or "\\" in value:
        return True
    return Path(value).is_absolute()


def _resolve_project_path(base_dir: Path, raw_path: str) -> Path:
    replaced = _replace_project_dir(raw_path, base_dir)
    candidate = Path(replaced)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    resolved_path = candidate.resolve()
    if not _is_within_base_dir(resolved_path, base_dir):
        raise MaaFWAgentEnvError(
            f"路径越界，禁止访问项目目录之外的 agent 文件: {raw_path}"
        )
    return resolved_path


def _is_within_base_dir(path: Path, base_dir: Path) -> bool:
    try:
        path.relative_to(base_dir)
        return True
    except ValueError:
        return False
