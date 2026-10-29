from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.task.MaaFW.tools.core.interface.agent_entry import (
    CFA_FALLBACK_AGENT_ENTRY,
    describe_cfa_agent_entry_fallback,
    flattened_entry_path,
    is_python_entry_arg,
    is_relative_entry_path,
)
from app.task.MaaFW.tools.core.interface.models import MaaFWAgent
from app.task.MaaFW.tools.core.runtime_pool._shared import (
    venv_base_python_missing as _venv_base_python_missing,
)

from .models import MaaFWAgentCommandPlan
from .venv_share import AGENT_VENV_DIR_PREFIX as AGENT_VENV_DIR_PREFIX
from .venv_share import (
    collect_orphan_agent_venvs as _collect_orphan_agent_venvs,
)
from .venv_share import (
    legacy_isolated_venv_name,
    read_venv_ref,
    resolve_agent_venv_root,
    shared_venv_key_inputs,
    shared_venv_name,
)


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


def planned_shared_venv_name(
    base_dir: str | Path, *, runner_maafw_version: str | None = None
) -> str:
    """按依赖清单 + maafw requirement + 宿主身份算出的共用目录名（见 ``venv_share``）。"""

    return shared_venv_name(
        shared_venv_key_inputs(base_dir, runner_maafw_version=runner_maafw_version)
    )


def compute_isolated_venv_path(
    base_dir: str | Path,
    *,
    managed_env_root: str | Path | None = None,
    runner_maafw_version: str | None = None,
) -> Path:
    """该项目的 Python agent 用的隔离 venv。

    不再按项目路径哈希：按依赖清单、maafw 版本与宿主身份跨视图共用（``venv_share``）。
    建计划时还不知道 runner 这次的 maafw 版本（``runner_maafw_version`` 为空），项目没自带
    原生库的那种算出来的键可能与准备时不同；所以先看本视图的引用记录——它记着上次准备
    实际用的目录和当时建计划算出的键，键对得上就用它。准备时再按确切版本定一次、改写计划
    （``env.prepare_agent_envs``）。依赖清单读不了时退回老规则的目录名，准备那一步会照原样
    报出读不了的原因。
    """

    resolved_base_dir = Path(base_dir).resolve()
    root = resolve_agent_venv_root(managed_env_root)
    try:
        plan_name = planned_shared_venv_name(
            resolved_base_dir, runner_maafw_version=runner_maafw_version
        )
    except Exception:  # noqa: BLE001 - 准备时再按同样的读法报错
        return root / legacy_isolated_venv_name(resolved_base_dir)
    if runner_maafw_version is None:
        ref = read_venv_ref(root, resolved_base_dir)
        if ref is not None and ref.get("planKey") == plan_name:
            return root / str(ref["venv"])
    return root / plan_name


def collect_orphan_agent_venvs(
    root: str | Path,
    live_project_paths: Iterable[str | Path],
) -> list[Path]:
    """列出已无存活视图引用的隔离 venv。

    venv 跨视图共用之后目录名不再能由项目路径推出，存活集合按各视图的引用记录算，
    再加上建计划时会算出的目录（引用记录丢了也保得住）与升级前按路径建的老目录（还没
    准备过的视图第一跑要沿用它），规则见 ``venv_share.collect_orphan_agent_venvs``。
    存活视图的引用记录读不出来时抛 ``VenvRefError``、整轮不回收：**存活视图在用的
    venv 永远不会落进结果里**——这仍是这个实现最重要的性质。

    覆盖的情形：用户删了脚本、项目升级后依赖变了（旧键没人用了）、升级前按路径建的老目录
    在视图改用共用目录之后（实测残留过一份指向 ``Maa_bbb-win-x86_64-v1.12.10`` 的 venv，
    而用户早已升到 v1.12.14）、重建时改名待删的 ``*.trash-*``。
    """

    def plan_name_for(project: Path) -> str | None:
        return planned_shared_venv_name(project)

    return _collect_orphan_agent_venvs(
        root, live_project_paths, plan_name_for=plan_name_for
    )


def venv_python_exe(venv_path: str | Path) -> Path:
    path = Path(venv_path)
    if os.name == "nt":
        return path / "Scripts" / "python.exe"
    return path / "bin" / "python"


def venv_base_python_missing(venv_path: str | Path) -> bool:
    """venv 自己的文件都在，但 pyvenv.cfg 里 home 指向的基解释器已经不存在。

    运行池的 base venv 用同一个判据（实现在 ``runtime_pool._shared``），见那里的说明。
    """

    return _venv_base_python_missing(venv_path)


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
    # interface.models，使得缓存 interface 携带的旧 MaaFWAgent
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
    raw_args = [str(arg) for arg in agent_config.child_args or []]
    child_args = [_replace_project_dir(arg, base_dir) for arg in raw_args]
    # 要在 _resolve_executable 之前：自带 Python 的判定会看入口参数在不在。
    child_args, entry_fallback_reason = _apply_cfa_agent_entry_fallback(
        base_dir, child_args, raw_args
    )
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

    fallback_reason = (
        "; ".join(
            reason
            for reason in (entry_fallback_reason, executable["fallback_reason"])
            if reason
        )
        or None
    )
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
        timeout=agent_config.timeout,
        embedded=False,
    )


def _apply_cfa_agent_entry_fallback(
    base_dir: Path, child_args: list[str], raw_args: list[str]
) -> tuple[list[str], str | None]:
    """第一个 Python 入口脚本是相对写法、经 ``..`` 越出项目目录，而 CFA 的兜底入口在时，
    换成兜底入口的绝对路径（见 ``interface.agent_entry``）；其余参数原样。返回
    ``(参数, 说明)``。``raw_args`` 是替换 ``{PROJECT_DIR}`` 之前的原参数（与 ``child_args``
    逐项对应）：绝对写法按它判断，替换后的 ``{PROJECT_DIR}`` 本身就是绝对路径。"""

    for position, arg in enumerate(child_args):
        if not is_python_entry_arg(arg):
            continue
        if not is_relative_entry_path(raw_args[position]):
            # 绝对路径 / 盘符：原样交给解释器，不改跑兜底入口。
            return child_args, None
        try:
            _resolve_project_path(base_dir, arg)
            return child_args, None
        except MaaFWAgentEnvError:
            pass
        # 源码形态平铺后入口在项目根上的同一路径（``./../agent/main.py`` → ``agent/main.py``），
        # CFA 的固定兜底 ``agent/main.py`` 是它的特例。
        for candidate in (
            flattened_entry_path(raw_args[position]),
            CFA_FALLBACK_AGENT_ENTRY,
        ):
            if candidate is None:
                continue
            fallback = (base_dir / candidate).resolve()
            if _is_within_base_dir(fallback, base_dir) and fallback.is_file():
                replaced = list(child_args)
                replaced[position] = str(fallback)
                return replaced, describe_cfa_agent_entry_fallback(arg, str(fallback))
        return child_args, None
    return child_args, None


def _resolve_executable(
    base_dir: Path,
    child_exec: str,
    *,
    child_args: list[str],
    managed_env_root: str | Path | None,
) -> dict[str, Any]:
    replaced = _replace_project_dir(child_exec, base_dir)
    if not _looks_like_project_path(replaced):
        if _is_bare_python_command(replaced):
            return _isolated_venv_executable(
                base_dir,
                managed_env_root=managed_env_root,
                fallback_reason=(
                    f"项目声明从 PATH 查找解释器 {replaced!r}，"
                    "AUTO-MAS 不依赖宿主 Python"
                ),
            )
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
        return _isolated_venv_executable(
            base_dir,
            managed_env_root=managed_env_root,
            fallback_reason=f"项目声明的解释器不存在: {resolved_path}",
        )

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


def _isolated_venv_executable(
    base_dir: Path,
    *,
    managed_env_root: str | Path | None,
    fallback_reason: str,
) -> dict[str, Any]:
    venv_path = compute_isolated_venv_path(
        base_dir,
        managed_env_root=managed_env_root,
    )
    venv_python = venv_python_exe(venv_path)
    return {
        "command": str(venv_python),
        "exists": venv_python.exists(),
        "fallback_reason": (
            f"{fallback_reason}，将使用隔离 venv（依赖清单、maafw 版本相同的项目共用）:"
            f" {venv_path}"
        ),
        "runtime_kind": "isolated_venv",
        "isolated_venv_path": str(venv_path),
    }


#: interface.json 里「从 PATH 找解释器」的写法（PI v2 协议示例就是裸的 ``python``）。
BARE_PYTHON_COMMANDS: frozenset[str] = frozenset(
    {"python", "python3", "pythonw", "python.exe", "python3.exe", "pythonw.exe"}
)


def _is_bare_python_command(child_exec: str) -> bool:
    """裸的 ``python`` 不能原样交给 PATH 去找。

    worker 跑在运行池的 venv 里，而 Windows 上 venv 的 ``python.exe`` 只是个
    启动器，真正的进程是基解释器；``CreateProcess`` 找可执行文件先看「父进程
    所在目录」再看 PATH，且看的是父进程自己的 PATH，不是传给子进程的 ``env``。
    于是裸 ``python`` 永远落到运行池的基解释器上——那里没有 ``maa``，agent 一起
    就 ``ModuleNotFoundError``，用户 PATH 里有没有 Python 都一样。项目自带解释器
    走 ``project_python``；这种没带的按隔离 venv 处理，和「声明了自带 Python 但
    文件不存在」同一条路。
    """

    return child_exec.strip().lower() in BARE_PYTHON_COMMANDS


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
