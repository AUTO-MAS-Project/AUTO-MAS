from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


RUNNER_ENV_MANIFEST_NAME = ".auto_mas_maafw_runner_env.json"
RUNNER_DEFAULT_PACKAGES = (
    "maafw",
    "pydantic==2.11.7",
    "json5==0.14.0",
)
RUNNER_ENV_TIMEOUT = 300
REQUIREMENT_NAME_RE = re.compile(
    r"^\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"\s*(?:\[[^\]]+\])?\s*(?:===|[<>=!~]=?|@|;|\s|$)"
)


@dataclass(frozen=True)
class MaaFWRunnerEnvironment:
    python_executable: Path
    venv_path: Path
    env: dict[str, str]
    packages: tuple[str, ...]
    maafw_version: str | None


def prepare_runner_environment(
    project_path: str | Path,
    *,
    managed_env_root: str | Path | None = None,
    import_paths: Iterable[str | Path] = (),
    send_log: Callable[[str], None] | None = None,
) -> MaaFWRunnerEnvironment:
    """Prepare a project-scoped runner whose dependencies follow the project."""

    project = Path(project_path).resolve()
    root = (
        Path(managed_env_root).resolve()
        if managed_env_root is not None
        else (Path.cwd() / "config" / "maafw_runner_venvs").resolve()
    )
    venv_path = root / _runner_env_name(project)
    if venv_path.exists() and not _is_valid_venv(venv_path):
        _reset_managed_venv(venv_path, root)

    if not _is_valid_venv(venv_path):
        venv_path.parent.mkdir(parents=True, exist_ok=True)
        bootstrap_python = _venv_bootstrap_python()
        _send_log(
            send_log,
            f"[MaaFW Runner] 创建项目隔离 venv: {venv_path} "
            f"(引导 Python: {bootstrap_python})",
        )
        _run_setup_command(
            [bootstrap_python, "-m", "venv", str(venv_path)],
            cwd=Path.cwd(),
        )

    python_executable = _venv_python(venv_path)
    packages = tuple(build_runner_packages(project))
    manifest = _build_manifest(project, packages)
    manifest_path = venv_path / RUNNER_ENV_MANIFEST_NAME
    env = build_runner_environment(venv_path, import_paths=import_paths)
    if not _manifest_matches(manifest_path, manifest):
        _send_log(
            send_log,
            f"[MaaFW Runner] 安装项目运行依赖: {', '.join(packages)}",
        )
        _run_setup_command(
            [
                str(python_executable),
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--disable-pip-version-check",
                "--quiet",
                *packages,
            ],
            cwd=project,
            env=env,
        )
        _write_manifest(manifest_path, manifest)
        _send_log(send_log, f"[MaaFW Runner] 项目运行依赖已准备: {venv_path}")
    else:
        _send_log(send_log, f"[MaaFW Runner] 项目隔离 venv 已就绪: {venv_path}")

    maafw_version = _installed_maafw_version(python_executable, env)
    if maafw_version:
        _send_log(send_log, f"[MaaFW Runner] 使用项目 MaaFW: v{maafw_version}")

    return MaaFWRunnerEnvironment(
        python_executable=python_executable,
        venv_path=venv_path,
        env=env,
        packages=packages,
        maafw_version=maafw_version,
    )


def build_runner_packages(project_path: str | Path) -> list[str]:
    project_packages = _load_requirements(Path(project_path).resolve())
    project_distribution_names = {
        name
        for requirement in project_packages
        if (name := requirement_distribution_name(requirement)) is not None
    }
    packages = [
        package
        for package in RUNNER_DEFAULT_PACKAGES
        if requirement_distribution_name(package) not in project_distribution_names
    ]
    packages.extend(project_packages)
    return packages


def requirement_distribution_name(requirement: str) -> str | None:
    match = REQUIREMENT_NAME_RE.match(requirement)
    if match is None:
        return None
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def build_runner_environment(
    venv_path: str | Path,
    *,
    import_paths: Iterable[str | Path] = (),
) -> dict[str, str]:
    env = os.environ.copy()
    for name in (
        "PYTHONHOME",
        "PYTHONUSERBASE",
        "PIP_TARGET",
        "PIP_PREFIX",
        "PIP_USER",
    ):
        env.pop(name, None)

    venv = Path(venv_path).resolve()
    scripts_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    resolved_import_paths = [
        str(Path(path).resolve())
        for path in import_paths
        if Path(path).exists()
    ]
    existing_python_path = env.get("PYTHONPATH", "")
    if existing_python_path:
        resolved_import_paths.append(existing_python_path)

    env["VIRTUAL_ENV"] = str(venv)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PATH"] = f"{scripts_dir}{os.pathsep}{env.get('PATH', '')}"
    if resolved_import_paths:
        env["PYTHONPATH"] = os.pathsep.join(resolved_import_paths)
    else:
        env.pop("PYTHONPATH", None)
    return env


def prefer_active_venv_site_packages(
    site_packages: str | Path | None = None,
) -> Path | None:
    """Keep the project Runner packages ahead of shared plugin dependencies."""

    raw_path = site_packages or sysconfig.get_path("purelib")
    if not raw_path:
        return None

    active_site_packages = Path(raw_path).resolve()
    normalized_path = str(active_site_packages)
    sys.path[:] = [
        item
        for item in sys.path
        if _normalized_sys_path(item) != normalized_path
    ]
    sys.path.insert(0, normalized_path)
    return active_site_packages


def _load_requirements(project_path: Path) -> list[str]:
    requirements_path = project_path / "requirements.txt"
    packages: list[str] = []
    try:
        for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            packages.append(line)
    except FileNotFoundError:
        pass
    return packages


def _runner_env_name(project_path: Path) -> str:
    key = str(project_path)
    if os.name == "nt":
        key = key.casefold()
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return f"maafw_runner_{digest}"


def _build_manifest(project_path: Path, packages: tuple[str, ...]) -> dict[str, object]:
    requirements_path = project_path / "requirements.txt"
    interface_path = next(
        (
            project_path / file_name
            for file_name in ("interface.json", "interface.jsonc")
            if (project_path / file_name).is_file()
        ),
        None,
    )
    requirements_hash = (
        hashlib.sha256(requirements_path.read_bytes()).hexdigest()
        if requirements_path.is_file()
        else ""
    )
    interface_hash = (
        hashlib.sha256(interface_path.read_bytes()).hexdigest()
        if interface_path is not None
        else ""
    )
    return {
        "schemaVersion": 4,
        "projectPath": str(project_path),
        "requirementsHash": requirements_hash,
        "interfaceHash": interface_hash,
        "packages": list(packages),
        "pythonVersion": f"{sys.version_info.major}.{sys.version_info.minor}",
    }


def _manifest_matches(manifest_path: Path, expected: dict[str, object]) -> bool:
    try:
        current = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    return current == expected


def _write_manifest(manifest_path: Path, manifest: dict[str, object]) -> None:
    temporary_path = manifest_path.with_suffix(f"{manifest_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(manifest_path)


def _run_setup_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=RUNNER_ENV_TIMEOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"MaaFW Runner 环境准备超时: {command[:3]}") from exc

    if result.returncode == 0:
        return
    detail = (result.stderr or result.stdout or "").strip()
    raise RuntimeError(
        f"MaaFW Runner 环境准备失败 (exit={result.returncode}): {detail[:800]}"
    )


def _installed_maafw_version(
    python_executable: Path,
    env: dict[str, str],
) -> str | None:
    probe_env = env.copy()
    probe_env.pop("PYTHONPATH", None)
    try:
        result = subprocess.run(
            [
                str(python_executable),
                "-c",
                "import importlib.metadata as m; print(m.version('maafw'))",
            ],
            capture_output=True,
            timeout=15,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=probe_env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    version = result.stdout.strip()
    return version or None


def _normalized_sys_path(path: str) -> str:
    try:
        return str(Path(path).resolve())
    except (OSError, RuntimeError):
        return path


def _reset_managed_venv(venv_path: Path, managed_root: Path) -> None:
    resolved_venv = venv_path.resolve()
    if (
        resolved_venv.parent != managed_root.resolve()
        or not resolved_venv.name.startswith("maafw_runner_")
    ):
        raise RuntimeError(f"拒绝重建非托管 MaaFW Runner venv: {venv_path}")
    shutil.rmtree(resolved_venv, ignore_errors=True)


def _venv_python(venv_path: Path) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _is_valid_venv(venv_path: Path) -> bool:
    return _venv_python(venv_path).is_file() and (venv_path / "pyvenv.cfg").is_file()


def _venv_bootstrap_python() -> str:
    portable_python = Path.cwd() / "environment" / "python" / "python.exe"
    if portable_python.is_file():
        return str(portable_python)
    return sys.executable


def _send_log(send_log: Callable[[str], None] | None, message: str) -> None:
    if send_log is not None:
        send_log(message)
