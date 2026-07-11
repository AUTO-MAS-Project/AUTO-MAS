from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .models import MaaFWAgentCommandPlan, MaaFWAgentEnvPrepareResult
from .planner import MaaFWAgentEnvError, venv_python_exe


AGENT_BOOTSTRAP_PACKAGE = "json-with-comments"
AGENT_ENV_MANIFEST_NAME = ".auto_mas_agent_env.json"
AGENT_COMPAT_SHIM_DIR_NAME = ".auto_mas_shims"
PIP_HEALTH_CHECK_TIMEOUT = 15
PIP_INSTALL_TIMEOUT = 120


def prepare_agent_envs(
    project_path: str | Path,
    plans: list[MaaFWAgentCommandPlan],
    *,
    send_log: Callable[[str], None] | None = None,
    bootstrap_python: str | None = None,
    install_dependencies: bool = True,
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
    for plan in plans:
        python_exe = plan.command[0] if plan.command else plan.executable
        resolved_python = _safe_resolve_python(python_exe)
        if resolved_python in checked_python:
            log(f"[Python环境] 已检查过该 Python，跳过重复检查: {python_exe}")
            continue

        runtime_kind = plan.runtimeKind or "external"
        log(f"[Python环境] Agent {plan.childExec} 使用 {runtime_kind}: {python_exe}")
        if runtime_kind == "isolated_venv":
            prepared_path = _prepare_isolated_venv_env(
                plan,
                resolved_project_path,
                log,
                bootstrap_python=bootstrap_python,
                install_dependencies=install_dependencies,
            )
            prepared_venvs.append(str(prepared_path))
            checked_python.add(resolved_python)
            continue

        if runtime_kind == "project_python":
            _prepare_project_python_env(python_exe, resolved_project_path, log)
            checked_python.add(resolved_python)
            continue

        skipped.append(plan.childExec)
        log(f"[Python环境] 跳过外部或非 Python 环境检测: {python_exe}")

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
    (shim_dir / "sitecustomize.py").write_text(
        "\n".join(
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
        ),
        encoding="utf-8",
    )
    return shim_dir


def _prepare_project_python_env(
    python_exe: str,
    project_path: Path,
    log: Callable[[str], None],
) -> None:
    log(f"[Python环境] 检测项目 Python: {python_exe}")
    test_env = _build_agent_env_for_pip(project_path)
    if _check_pip_health(python_exe, cwd=str(project_path), env=test_env, log=log):
        return

    raise MaaFWAgentEnvError(
        "项目 Python 环境 pip 不可用，请手动修复后重试：\n"
        f"  Python 路径: {python_exe}\n"
        "  处理建议:\n"
        "    方法1: 重新下载并解压完整 MaaFW 项目包\n"
        "    方法2: 在项目目录中手动修复该项目自带 Python 的 pip 环境\n"
        "  AUTO-MAS 不会自动修改项目 release 目录。"
    )


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
    python_exe = agent_plan.command[0] if agent_plan.command else str(venv_python_exe(venv_path))

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
        if not _pip_install(python_exe, packages, cwd=str(project_path), env=test_env, log=log):
            raise MaaFWAgentEnvError(f"隔离 venv 依赖安装失败: {python_exe}")
    else:
        log("[Python环境] 当前调用禁用依赖安装，仅写入隔离 venv manifest")

    _write_isolated_venv_manifest(venv_path, project_path)
    return venv_path


def _is_valid_venv_path(venv_path: Path) -> bool:
    return venv_python_exe(venv_path).is_file() and (venv_path / "pyvenv.cfg").is_file()


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
    python = bootstrap_python or _venv_bootstrap_python()
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


def _should_rebuild_isolated_venv(
    venv_path: Path,
    project_path: Path,
    log: Callable[[str], None],
) -> bool:
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
    if venv_path.parent.name != "maafw_agent_venvs" or not venv_path.name.startswith("maafw_venv_"):
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
        json.dumps(build_agent_env_manifest(project_path), ensure_ascii=False, indent=2),
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
            log(f"[Python环境] pip --version 失败 (exit={result.returncode}): {detail[:500]}")
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
            log(f"[Python环境] pip install 检测失败 (exit={install_check.returncode}): {detail[:500]}")
        return False
    except subprocess.TimeoutExpired:
        log(f"[Python环境] pip 检测超时 ({PIP_HEALTH_CHECK_TIMEOUT}s)")
        return False
    except Exception as exc:
        log(f"[Python环境] pip 检测异常: {exc}")
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
        if result.returncode == 0 and _check_pip_health(python_exe, cwd=cwd, env=env, log=log):
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


def _venv_bootstrap_python() -> str:
    portable_python = Path.cwd() / "environment" / "python" / "python.exe"
    if portable_python.is_file():
        return str(portable_python)
    return sys.executable


def _safe_resolve_python(path: str) -> str:
    try:
        return str(Path(path).resolve())
    except Exception:
        return path
