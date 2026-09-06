from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Callable

from ..automas_maafw_runtime_pool import runtime_managed_uv_executable
from .models import MaaFWAgentCommandPlan, MaaFWAgentEnvPrepareResult
from .planner import MaaFWAgentEnvError, venv_base_python_missing, venv_python_exe

AGENT_BOOTSTRAP_PACKAGE = "json-with-comments"
AGENT_ENV_MANIFEST_NAME = ".auto_mas_agent_env.json"
AGENT_COMPAT_SHIM_DIR_NAME = ".auto_mas_shims"
PIP_HEALTH_CHECK_TIMEOUT = 15
PROJECT_PYTHON_HEALTH_TIMEOUT = 15
PIP_INSTALL_TIMEOUT = 120
VENV_PROBE_TIMEOUT = 30
# uv 兜底可能需要下载 managed Python,给足余量
UV_VENV_TIMEOUT = 300

_ISOLATED_VENV_LOCKS_GUARD = threading.Lock()
_ISOLATED_VENV_LOCKS: dict[str, threading.RLock] = {}


def prepare_agent_envs(
    project_path: str | Path,
    plans: list[MaaFWAgentCommandPlan],
    *,
    send_log: Callable[[str], None] | None = None,
    bootstrap_python: str | None = None,
    install_dependencies: bool = True,
    progress: Callable[[dict[str, object]], None] | None = None,
) -> MaaFWAgentEnvPrepareResult:
    resolved_project_path = Path(project_path).resolve()
    messages: list[str] = []
    prepared_venvs: list[str] = []
    skipped: list[str] = []

    def log(message: str) -> None:
        messages.append(message)
        if send_log is not None:
            send_log(message)

    for path_name in ("debug", "logs", "temp"):
        (resolved_project_path / path_name).mkdir(exist_ok=True)

    checked_python: set[str] = set()
    total_plans = len(plans)
    _report_agent_progress(
        progress,
        status="running",
        message=f"准备 {total_plans} 个 MaaFW Agent 环境",
        percent=0.0,
        completed=0,
        total=total_plans,
    )

    def report_plan_complete(index: int, plan: MaaFWAgentCommandPlan) -> None:
        _report_agent_progress(
            progress,
            status="running",
            message=f"Agent 环境准备完成: {plan.childExec}",
            percent=((index + 1) * 100.0 / total_plans if total_plans else 100.0),
            completed=index + 1,
            total=total_plans,
        )

    for index, plan in enumerate(plans):
        _report_agent_progress(
            progress,
            status="running",
            message=f"正在准备 Agent: {plan.childExec}",
            percent=(index * 100.0 / total_plans if total_plans else 100.0),
            completed=index,
            total=total_plans,
        )
        python_exe = plan.command[0] if plan.command else plan.executable
        resolved_python = _safe_resolve_python(python_exe)
        if resolved_python in checked_python:
            log(f"[Python环境] 已检查过该 Python，跳过重复检查: {python_exe}")
            report_plan_complete(index, plan)
            continue

        runtime_kind = plan.runtimeKind or "external"
        log(f"[Python环境] Agent {plan.childExec} 使用 {runtime_kind}: {python_exe}")
        if runtime_kind == "isolated_venv":
            with _isolated_venv_lock(Path(plan.isolatedVenvPath or python_exe)):
                prepared_path = _prepare_isolated_venv_env(
                    plan,
                    resolved_project_path,
                    log,
                    bootstrap_python=bootstrap_python,
                    install_dependencies=install_dependencies,
                )
            prepared_venvs.append(str(prepared_path))
            checked_python.add(resolved_python)
            report_plan_complete(index, plan)
            continue

        if runtime_kind == "project_python":
            _prepare_project_python_env(python_exe, resolved_project_path, log)
            checked_python.add(resolved_python)
            report_plan_complete(index, plan)
            continue

        if runtime_kind == "shared_runtime":
            if not Path(resolved_python).is_file():
                raise MaaFWAgentEnvError(
                    f"共享 MaaFW runtime Python 不存在或不可用：{python_exe}"
                )
            checked_python.add(resolved_python)
            log(f"[Python环境] 共享 MaaFW runtime Python 已就绪: {python_exe}")
            report_plan_complete(index, plan)
            continue

        skipped.append(plan.childExec)
        log(f"[Python环境] 跳过外部或非 Python 环境检测: {python_exe}")

        report_plan_complete(index, plan)

    _report_agent_progress(
        progress,
        status="ready",
        message="MaaFW Agent 环境准备完成",
        percent=100.0,
        completed=total_plans,
        total=total_plans,
    )

    return MaaFWAgentEnvPrepareResult(
        projectPath=str(resolved_project_path),
        plans=plans,
        preparedVenvs=prepared_venvs,
        skipped=skipped,
        messages=messages,
    )


def build_agent_env_manifest(project_path: str | Path) -> dict[str, object]:
    resolved_project_path = Path(project_path).resolve()
    return {
        "schemaVersion": 1,
        "projectPath": str(resolved_project_path),
        "interfaceHash": _project_interface_hash(resolved_project_path),
        "requirementsHash": _project_agent_requirements_hash(resolved_project_path),
        "requirements": _load_project_agent_requirements(resolved_project_path),
    }


def write_agent_compat_shims(venv_path: str | Path) -> Path:
    shim_dir = Path(venv_path) / AGENT_COMPAT_SHIM_DIR_NAME
    shim_dir.mkdir(parents=True, exist_ok=True)
    shim_path = shim_dir / "sitecustomize.py"
    content = "\n".join(
        [
            "def _patch_legacy_maafw_resource():",
            "    try:",
            "        import maa.resource as maa_resource_module",
            "        if hasattr(maa_resource_module, 'resource'):",
            "            return",
            "        from maa.agent.agent_server import AgentServer",
            "        maa_resource_module.resource = AgentServer",
            "    except Exception:",
            "        pass",
            "",
            "_patch_legacy_maafw_resource()",
            "",
        ]
    )
    try:
        if shim_path.read_text(encoding="utf-8") == content:
            return shim_dir
    except (FileNotFoundError, OSError, UnicodeError):
        pass

    temporary_path = shim_path.with_name(f"{shim_path.name}.tmp-{uuid.uuid4().hex}")
    try:
        temporary_path.write_text(content, encoding="utf-8")
        temporary_path.replace(shim_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return shim_dir


def _prepare_project_python_env(
    python_exe: str,
    project_path: Path,
    log: Callable[[str], None],
) -> None:
    log(f"[Python环境] 检测项目 Python: {python_exe}")
    test_env = _build_agent_env_for_pip(project_path)
    if _check_project_python_health(
        python_exe,
        cwd=str(project_path),
        env=test_env,
        log=log,
    ):
        return

    raise MaaFWAgentEnvError(
        "项目 Python 或 MaaFW Agent 模块不可用，请修复项目包后重试：\n"
        f"  Python 路径: {python_exe}\n"
        "  处理建议:\n"
        "    方法1: 重新下载并解压完整 MaaFW 项目包\n"
        "    方法2: 检查项目自带 Python 是否能导入 maa.agent.agent_server\n"
        "  项目 Python 属于 release 内容，AUTO-MAS 不要求其提供 pip，"
        "也不会自动修改该目录。"
    )


def _isolated_venv_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve())).casefold()
    with _ISOLATED_VENV_LOCKS_GUARD:
        return _ISOLATED_VENV_LOCKS.setdefault(key, threading.RLock())


def _report_agent_progress(
    callback: Callable[[dict[str, object]], None] | None,
    *,
    status: str,
    message: str,
    percent: float,
    completed: int,
    total: int,
) -> None:
    if callback is None:
        return
    try:
        callback(
            {
                "stage": "preparing_agents",
                "status": status,
                "message": message,
                "percent": percent,
                "completed": completed,
                "total": total,
            }
        )
    except Exception:
        return


def _prepare_isolated_venv_env(
    agent_plan: MaaFWAgentCommandPlan,
    project_path: Path,
    log: Callable[[str], None],
    *,
    bootstrap_python: str | None,
    install_dependencies: bool,
) -> Path:
    if not agent_plan.isolatedVenvPath:
        raise MaaFWAgentEnvError("隔离 venv 路径未提供，无法创建隔离环境")

    venv_path = Path(agent_plan.isolatedVenvPath).resolve()
    python_exe = (
        agent_plan.command[0] if agent_plan.command else str(venv_python_exe(venv_path))
    )

    log(f"[Python环境] 准备隔离 venv: {venv_path}")
    had_valid_venv = _is_valid_venv_path(venv_path)
    if _should_rebuild_isolated_venv(venv_path, project_path, log):
        _reset_isolated_venv(venv_path, log)
        had_valid_venv = False
    _ensure_isolated_venv(venv_path, log, bootstrap_python=bootstrap_python)
    write_agent_compat_shims(venv_path)

    test_env = _build_agent_env_for_pip(project_path)
    test_env["PYTHONPATH"] = str(project_path)

    if not _check_pip_health(python_exe, cwd=str(project_path), env=test_env, log=log):
        log("[Python环境] 隔离 venv pip 异常，尝试 ensurepip 修复...")
        if not _try_ensurepip(python_exe, cwd=str(project_path), env=test_env, log=log):
            raise MaaFWAgentEnvError(f"隔离 venv pip 无法自动修复: {python_exe}")

    if had_valid_venv and _is_isolated_venv_manifest_current(venv_path, project_path):
        log("[Python环境] 隔离 venv 依赖清单未变化，跳过 pip install")
        return venv_path

    if install_dependencies:
        packages = _load_project_agent_requirements(project_path)
        log(f"[Python环境] 隔离 venv 安装项目依赖: {', '.join(packages)}")
        if not _pip_install(
            python_exe, packages, cwd=str(project_path), env=test_env, log=log
        ):
            raise MaaFWAgentEnvError(f"隔离 venv 依赖安装失败: {python_exe}")
    else:
        log("[Python环境] 当前调用禁用依赖安装，仅写入隔离 venv manifest")

    _write_isolated_venv_manifest(venv_path, project_path)
    return venv_path


def _is_valid_venv_path(venv_path: Path) -> bool:
    if not (
        venv_python_exe(venv_path).is_file() and (venv_path / "pyvenv.cfg").is_file()
    ):
        return False
    # 文件都在不代表能用：引导用的基解释器（受管模式下常是 sys.executable
    # 所在的监督器管理 venv）事后被删掉重建过的话，这个 venv 也已经失效。
    return not venv_base_python_missing(venv_path)


def _ensure_isolated_venv(
    venv_path: Path,
    log: Callable[[str], None],
    *,
    bootstrap_python: str | None,
) -> None:
    if _is_valid_venv_path(venv_path):
        log(f"[Python环境] 隔离 venv 已存在: {venv_path}")
        return

    if venv_path.exists():
        _reset_isolated_venv(venv_path, log)

    venv_path.parent.mkdir(parents=True, exist_ok=True)
    python = bootstrap_python if bootstrap_python else _venv_bootstrap_python()
    if python is not None and bootstrap_python and not _python_supports_venv(python):
        # 调用方指定的引导解释器（如便携 embeddable Python）缺 venv，回退到自动挑选
        log(f"[Python环境] 指定引导 Python 缺少 venv 模块，改为自动挑选: {python}")
        python = _venv_bootstrap_python()

    if python is None:
        _create_venv_with_uv(venv_path, log)
    else:
        log(f"[Python环境] 创建隔离 venv: {venv_path} (引导 Python: {python})")
        try:
            result = subprocess.run(
                [python, "-m", "venv", str(venv_path)],
                capture_output=True,
                timeout=PIP_INSTALL_TIMEOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            raise MaaFWAgentEnvError(
                f"创建隔离 venv 超时 ({PIP_INSTALL_TIMEOUT}s): {venv_path}"
            ) from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise MaaFWAgentEnvError(
                f"创建隔离 venv 失败 (exit={result.returncode}): {detail[:500]}"
            )
    if not _is_valid_venv_path(venv_path):
        raise MaaFWAgentEnvError(f"创建隔离 venv 后结构不完整: {venv_path}")
    log(f"[Python环境] 隔离 venv 创建成功: {venv_path}")


def _create_venv_with_uv(venv_path: Path, log: Callable[[str], None]) -> None:
    """所有候选解释器都缺 venv 时的兜底：用 uv 建环境（必要时自取 managed Python）。"""
    uv_exe = _find_uv_executable()
    if uv_exe is None:
        raise MaaFWAgentEnvError(
            "创建隔离 venv 失败：可用的 Python 均不含 venv 模块（便携版通常为 "
            "embeddable 发行版），且未找到 uv 兜底。请安装完整 Python 或提供 uv。"
        )

    log(f"[Python环境] 引导 Python 均缺少 venv 模块，改用 uv 创建: {venv_path}")
    try:
        result = subprocess.run(
            [uv_exe, "venv", "--seed", str(venv_path)],
            capture_output=True,
            timeout=UV_VENV_TIMEOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        raise MaaFWAgentEnvError(
            f"uv 创建隔离 venv 超时 ({UV_VENV_TIMEOUT}s): {venv_path}"
        ) from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise MaaFWAgentEnvError(
            f"uv 创建隔离 venv 失败 (exit={result.returncode}): {detail[:500]}"
        )


def _should_rebuild_isolated_venv(
    venv_path: Path,
    project_path: Path,
    log: Callable[[str], None],
) -> bool:
    if venv_path.exists() and venv_base_python_missing(venv_path):
        log(
            f"[Python环境] 隔离 venv 的基解释器已不存在（pyvenv.cfg 的 home 已"
            f"失效），将重建: {venv_path}"
        )
        return True
    if venv_path.exists() and not _is_valid_venv_path(venv_path):
        log("[Python环境] 隔离 venv 不完整，将重建")
        return True
    if not _is_valid_venv_path(venv_path):
        return False

    manifest_path = venv_path / AGENT_ENV_MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        log("[Python环境] 隔离 venv 缺少依赖清单，将重建")
        return True
    except Exception as exc:
        log(f"[Python环境] 隔离 venv 依赖清单异常，将重建: {exc}")
        return True

    expected = build_agent_env_manifest(project_path)
    if manifest.get("projectPath") != expected["projectPath"]:
        log("[Python环境] 隔离 venv 项目路径已变化，将重建")
        return True
    if manifest.get("interfaceHash") != expected["interfaceHash"]:
        log("[Python环境] MaaFW 项目 interface 已变化，将重建隔离 venv")
        return True
    if manifest.get("requirementsHash") != expected["requirementsHash"]:
        log("[Python环境] MaaFW 项目 requirements 已变化，将重建隔离 venv")
        return True
    return False


def _reset_isolated_venv(venv_path: Path, log: Callable[[str], None]) -> None:
    if venv_path.parent.name != "maafw_agent_venvs" or not venv_path.name.startswith(
        "maafw_venv_"
    ):
        raise MaaFWAgentEnvError(f"拒绝重建非托管隔离 venv: {venv_path}")
    shutil.rmtree(venv_path, ignore_errors=True)
    log(f"[Python环境] 已清理旧隔离 venv: {venv_path}")


def _is_isolated_venv_manifest_current(venv_path: Path, project_path: Path) -> bool:
    manifest_path = venv_path / AGENT_ENV_MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    expected = build_agent_env_manifest(project_path)
    return (
        manifest.get("projectPath") == expected["projectPath"]
        and manifest.get("interfaceHash") == expected["interfaceHash"]
        and manifest.get("requirementsHash") == expected["requirementsHash"]
    )


def _write_isolated_venv_manifest(venv_path: Path, project_path: Path) -> None:
    manifest_path = venv_path / AGENT_ENV_MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(
            build_agent_env_manifest(project_path), ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )


def _load_project_agent_requirements(project_path: Path) -> list[str]:
    requirements_path = project_path / "requirements.txt"
    packages: list[str] = []
    try:
        with requirements_path.open("r", encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                packages.append(line)
    except FileNotFoundError:
        pass

    normalized = {item.split(";", 1)[0].strip().lower() for item in packages}
    if not any(item.startswith(AGENT_BOOTSTRAP_PACKAGE) for item in normalized):
        packages.append(AGENT_BOOTSTRAP_PACKAGE)
    return packages


def _project_agent_requirements_hash(project_path: Path) -> str:
    payload = json.dumps(
        _load_project_agent_requirements(project_path),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _project_interface_hash(project_path: Path) -> str:
    for name in ("interface.json", "interface.jsonc"):
        path = project_path / name
        if path.is_file():
            return hashlib.sha256(path.read_bytes()).hexdigest()
    return ""


def _build_agent_env_for_pip(project_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONUSERBASE", None)
    env.pop("PIP_TARGET", None)
    env.pop("PIP_PREFIX", None)
    env.pop("PIP_USER", None)
    env["PYTHONPATH"] = str(project_path)
    return env


def _check_pip_health(
    python_exe: str,
    *,
    cwd: str | None,
    env: dict[str, str],
    log: Callable[[str], None],
) -> bool:
    try:
        result = subprocess.run(
            [python_exe, "-m", "pip", "--version"],
            capture_output=True,
            timeout=PIP_HEALTH_CHECK_TIMEOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            log(
                f"[Python环境] pip --version 失败 (exit={result.returncode}): {detail[:500]}"
            )
            return False

        install_check = subprocess.run(
            [
                python_exe,
                "-c",
                "from pip._internal.commands.install import InstallCommand; print('install command OK')",
            ],
            capture_output=True,
            timeout=PIP_HEALTH_CHECK_TIMEOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
        )
        if install_check.returncode == 0:
            log(f"[Python环境] pip 健康: {result.stdout.strip()}")
            return True

        detail = (install_check.stderr or install_check.stdout or "").strip()
        if "backports.zstd" in detail or "ZstdError" in detail:
            log("[Python环境] pip install 子命令加载失败（backports.zstd 冲突）")
        else:
            log(
                f"[Python环境] pip install 检测失败 (exit={install_check.returncode}): {detail[:500]}"
            )
        return False
    except subprocess.TimeoutExpired:
        log(f"[Python环境] pip 检测超时 ({PIP_HEALTH_CHECK_TIMEOUT}s)")
        return False
    except Exception as exc:
        log(f"[Python环境] pip 检测异常: {exc}")
        return False


def _check_project_python_health(
    python_exe: str,
    *,
    cwd: str | None,
    env: dict[str, str],
    log: Callable[[str], None],
) -> bool:
    """Probe a project-owned Agent runtime without requiring or invoking pip."""

    probe = (
        "import sys; "
        "from maa.agent.agent_server import AgentServer; "
        "print(f'Python {sys.version_info.major}.{sys.version_info.minor}; MaaFW Agent OK')"
    )
    try:
        result = subprocess.run(
            [python_exe, "-c", probe],
            capture_output=True,
            timeout=PROJECT_PYTHON_HEALTH_TIMEOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
        )
    except subprocess.TimeoutExpired:
        log(
            "[Python环境] 项目 Python/Agent 健康检查超时 "
            f"({PROJECT_PYTHON_HEALTH_TIMEOUT}s)"
        )
        return False
    except Exception as exc:
        log(f"[Python环境] 项目 Python/Agent 健康检查异常: {exc}")
        return False

    if result.returncode == 0:
        detail = (result.stdout or "").strip()
        log(f"[Python环境] 项目 Python/Agent 健康: {detail or python_exe}")
        return True

    detail = (result.stderr or result.stdout or "").strip()
    log(
        "[Python环境] 项目 Python/Agent 健康检查失败 "
        f"(exit={result.returncode}): {detail[:500]}"
    )
    return False


def _try_ensurepip(
    python_exe: str,
    *,
    cwd: str | None,
    env: dict[str, str],
    log: Callable[[str], None],
) -> bool:
    log("[Python环境] 修复策略 A (ensurepip)...")
    try:
        result = subprocess.run(
            [python_exe, "-m", "ensurepip", "--upgrade"],
            capture_output=True,
            timeout=PIP_INSTALL_TIMEOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
        )
        if result.returncode == 0 and _check_pip_health(
            python_exe, cwd=cwd, env=env, log=log
        ):
            log("[Python环境] ensurepip 修复成功")
            return True
        detail = (result.stderr or result.stdout or "").strip()
        log(f"[Python环境] ensurepip 未成功: {detail[:300]}")
    except subprocess.TimeoutExpired:
        log(f"[Python环境] ensurepip 超时 ({PIP_INSTALL_TIMEOUT}s)")
    except Exception as exc:
        log(f"[Python环境] ensurepip 执行异常: {exc}")
    return False


def _pip_install(
    python_exe: str,
    packages: list[str],
    *,
    cwd: str | None,
    env: dict[str, str],
    log: Callable[[str], None],
) -> bool:
    try:
        result = subprocess.run(
            [python_exe, "-m", "pip", "install", "--quiet", *packages],
            capture_output=True,
            timeout=PIP_INSTALL_TIMEOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
        )
        if result.returncode == 0:
            log(f"[Python环境] pip install 完成: {', '.join(packages)}")
            return True
        detail = (result.stderr or result.stdout or "").strip()
        log(f"[Python环境] pip install 未成功: {detail[:300]}")
    except subprocess.TimeoutExpired:
        log(f"[Python环境] pip install 超时 ({PIP_INSTALL_TIMEOUT}s)")
    except Exception as exc:
        log(f"[Python环境] pip install 异常: {exc}")
    return False


def _python_supports_venv(python: str) -> bool:
    """探测解释器是否带 venv/ensurepip 标准库。

    便携目录常见 embeddable 发行版（python3xx._pth），不带 venv 模块，
    直接 `-m venv` 会报 "No module named venv"，必须先探测再用作引导。
    """
    try:
        result = subprocess.run(
            [python, "-c", "import venv, ensurepip"],
            capture_output=True,
            timeout=VENV_PROBE_TIMEOUT,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _find_uv_executable() -> str | None:
    # 受管模式（AUTO-MAS-Runtime 监督后端）下没有便携 Python，监督器改为
    # 用 AUTO_MAS_UV_EXE 注入它已校验过的 uv 路径，也不会把这个 uv 加进
    # PATH——优先信它，找不到再退回便携路径与 PATH 查找。
    configured_uv = os.environ.get("AUTO_MAS_UV_EXE")
    if configured_uv:
        configured_path = Path(configured_uv)
        if configured_path.is_file():
            return str(configured_path.resolve())

    portable_uv = Path.cwd() / "environment" / "python" / "Scripts" / "uv.exe"
    if portable_uv.is_file():
        return str(portable_uv)

    # 用户从受管模式回退到旧链路时监督器不再注入变量，但 Runtime 早已把 uv 装在
    # runtime/tools/uv 下；和运行池共用同一份查找逻辑，免得两处各认一半。
    runtime_uv = runtime_managed_uv_executable()
    if runtime_uv is not None:
        return runtime_uv
    return shutil.which("uv")


def _venv_bootstrap_python() -> str | None:
    """返回第一个带 venv 模块的引导 Python；全部不可用时返回 None（改走 uv 兜底）。"""
    candidates: list[str] = []
    portable_python = Path.cwd() / "environment" / "python" / "python.exe"
    if portable_python.is_file():
        candidates.append(str(portable_python))
    candidates.append(sys.executable)
    path_python = shutil.which("python")
    if path_python:
        candidates.append(path_python)
    for candidate in candidates:
        if _python_supports_venv(candidate):
            return candidate
    return None


def _safe_resolve_python(path: str) -> str:
    try:
        return str(Path(path).resolve())
    except Exception:
        return path
