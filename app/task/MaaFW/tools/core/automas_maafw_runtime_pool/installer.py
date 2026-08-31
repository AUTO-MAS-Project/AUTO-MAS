from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version


RUNTIME_INSTALL_TIMEOUT_SECONDS = 300
RUNTIME_AUDIT_TIMEOUT_SECONDS = 60
VENV_PROBE_TIMEOUT_SECONDS = 30
# uv 兜底可能需要下载 managed Python，给足余量。
UV_VENV_TIMEOUT_SECONDS = 300
UV_PYTHON_INSTALL_TIMEOUT_SECONDS = 300
UV_CACHE_RELATIVE_PATH = Path("cache") / "uv"
UV_PYTHON_RELATIVE_PATH = Path("python")
UV_LINK_MODE = "hardlink"
AUTO_MAS_UV_INDEX_URL_ENV = "AUTO_MAS_UV_INDEX_URL"
# 解释器下载镜像。包索引早就有 AUTO_MAS_UV_INDEX_URL，但 uv 下载 CPython 走的是
# 另一条路（python-build-standalone 的 GitHub Release），此前没有任何镜像开关——
# 受限网络下这一步要么慢到超时，要么拿到不完整的解释器。UV_* 不在
# _clean_process_environment 的剔除名单里，所以显式设置的 UV_PYTHON_INSTALL_MIRROR
# 优先，本变量只作兜底。
AUTO_MAS_UV_PYTHON_INSTALL_MIRROR_ENV = "AUTO_MAS_UV_PYTHON_INSTALL_MIRROR"
RUNTIME_POOL_STAGING_DIRECTORY_NAME = ".staging"
SUPPORTED_CPYTHON_MINORS = ((3, 12), (3, 13))

# 探针里必须真的 import ctypes：MaaFW 的 Python 绑定第一行就是 ``import ctypes``，
# 而 ABI 那几项（version/soabi/platform）全部来自解释器二进制，标准库那一半坏了
# 照样报得一模一样。真机上就这么漏过去过——探测全绿，worker 起来才在
# ``maa/library.py`` 第 1 行炸掉，抛出的还是 ctypes 内部的天书。放在同一个子进程
# 里做，零额外开销。
_IDENTITY_PROBE_SCRIPT = (
    "import ctypes,json,platform,sys,sysconfig;"
    "print(json.dumps({"
    "'implementation': getattr(sys.implementation, 'name', 'python'),"
    "'cacheTag': getattr(sys.implementation, 'cache_tag', None) or 'unknown',"
    "'soabi': str(sysconfig.get_config_var('SOABI') or 'unknown'),"
    "'version': '.'.join(str(part) for part in sys.version_info[:3]),"
    "'shortVersion': f'{sys.version_info.major}.{sys.version_info.minor}',"
    "'platform': sysconfig.get_platform() or sys.platform,"
    "'architecture': platform.machine() or 'unknown',"
    "}))"
)


def resolve_python_interpreter(
    pool_root: str | Path,
    python_request: Mapping[str, Any],
    *,
    allow_install: bool,
) -> dict[str, Any] | None:
    """Resolve one exact interpreter for an explicit Python constraint.

    Resolution never silently crosses ABI boundaries.  The host interpreter
    is reused when it satisfies the request.  Otherwise an explicitly
    configured interpreter or a uv-managed interpreter under ``pool/python``
    is used.  Only ``allow_install=True`` may download a missing interpreter.
    """

    implementation = (
        str(python_request.get("implementation") or "cpython").strip().casefold()
    )
    if implementation != "cpython":
        raise RuntimeError("MaaFW runtime currently supports only CPython interpreters")
    constraint = _normalize_python_constraint(python_request.get("constraint"))
    specifier = _parse_python_constraint(constraint)
    target_versions = _matching_supported_python_minors(specifier)
    if not target_versions:
        raise RuntimeError(
            "MaaFW runtime Python constraint has no supported CPython target "
            f"(supported: 3.12, 3.13): {constraint}"
        )

    host_probe = probe_python_identity(Path(sys.executable))
    if _python_probe_satisfies(host_probe, implementation, specifier):
        return {
            "executable": str(Path(sys.executable).resolve()),
            "identity": host_probe,
            "source": "host",
            "constraint": constraint,
        }

    exact_patch_target = _exact_python_patch_target(specifier)
    target_requests = [
        (
            exact_patch_target
            if exact_patch_target is not None
            and exact_patch_target.startswith(f"{target_version}.")
            else target_version
        )
        for target_version in target_versions
    ]

    for target_version in reversed(target_versions):
        configured = _configured_python_executable(target_version)
        if configured is None:
            continue
        probe = probe_python_identity(configured)
        if not _python_probe_satisfies(probe, implementation, specifier):
            raise RuntimeError(
                "configured MaaFW runtime Python does not satisfy the request: "
                f"path={configured}, constraint={constraint}, "
                f"actual={probe.get('implementation')} {probe.get('version')}"
            )
        return {
            "executable": str(configured.resolve()),
            "identity": probe,
            "source": "configured",
            "constraint": constraint,
        }

    root = Path(pool_root).resolve()
    root, python_root, cache_dir = _canonicalize_pool_paths(
        root,
        root / UV_PYTHON_RELATIVE_PATH,
        root / UV_CACHE_RELATIVE_PATH,
    )
    uv_executable = _find_uv_executable(sys.executable)
    if uv_executable is None:
        if allow_install:
            raise RuntimeError(
                "MaaFW runtime requires a different Python ABI, but uv was not found"
            )
        return None

    for target_version in reversed(target_requests):
        executable = _find_pool_managed_python(
            uv_executable,
            target_version,
            pool_root=root,
            python_root=python_root,
            cache_dir=cache_dir,
        )
        if executable is None:
            continue
        probe = probe_python_identity(executable)
        if _python_probe_satisfies(probe, implementation, specifier):
            return {
                "executable": str(executable),
                "identity": probe,
                "source": "pool-managed",
                "constraint": constraint,
            }

    if not allow_install:
        if exact_patch_target is not None or all(
            _minor_family_fully_satisfies(specifier, target_version)
            for target_version in target_versions
        ):
            return None
        installed_target = _select_uv_python_version(
            uv_executable,
            specifier,
            target_versions,
            pool_root=root,
            python_root=python_root,
            cache_dir=cache_dir,
            only_installed=True,
        )
        if installed_target is None:
            return None
        executable = _find_pool_managed_python(
            uv_executable,
            installed_target,
            pool_root=root,
            python_root=python_root,
            cache_dir=cache_dir,
        )
        if executable is None:
            return None
        probe = probe_python_identity(executable)
        if not _python_probe_satisfies(probe, implementation, specifier):
            return None
        return {
            "executable": str(executable),
            "identity": probe,
            "source": "pool-managed",
            "constraint": constraint,
        }

    target_version = target_requests[-1]
    if exact_patch_target is None and not _minor_family_fully_satisfies(
        specifier, target_versions[-1]
    ):
        selected_download = _select_uv_python_version(
            uv_executable,
            specifier,
            target_versions,
            pool_root=root,
            python_root=python_root,
            cache_dir=cache_dir,
            only_installed=False,
        )
        if selected_download is None:
            raise RuntimeError(
                "uv has no downloadable CPython satisfying the MaaFW runtime "
                f"constraint: {constraint}"
            )
        target_version = selected_download
    python_root.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    _install_pool_managed_python(
        uv_executable,
        target_version,
        pool_root=root,
        python_root=python_root,
        cache_dir=cache_dir,
    )
    executable = _find_pool_managed_python(
        uv_executable,
        target_version,
        pool_root=root,
        python_root=python_root,
        cache_dir=cache_dir,
    )
    if executable is None:
        raise RuntimeError(
            f"uv installed CPython {target_version}, but it was not found in the pool"
        )
    probe = probe_python_identity(executable)
    if not _python_probe_satisfies(probe, implementation, specifier):
        raise RuntimeError(
            "uv installed MaaFW runtime Python with an incompatible ABI: "
            f"constraint={constraint}, actual={probe.get('version')}"
        )
    return {
        "executable": str(executable),
        "identity": probe,
        "source": "pool-managed",
        "constraint": constraint,
    }


def install_python_runtime(
    environment_path: Path,
    requirements: Sequence[str],
    identity: dict[str, Any],
    *,
    cwd: str | Path | None = None,
    bootstrap_python: str | Path | None = None,
    send_log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Install one isolated selector environment with a pool-local uv cache.

    Every canonical requirement set still owns an independent venv.  When uv
    is available, package downloads and unpacked wheels are shared through a
    cache located beside the pool's ``runtimes``/``.staging`` directories, and
    uv hardlinks cached package files into each venv.  A complete Python may
    fall back to stdlib ``venv`` + pip when uv is unavailable; an embeddable
    Python without ``venv``/``ensurepip`` cannot.
    """

    log = send_log or (lambda _: None)
    bootstrap = str(bootstrap_python or sys.executable)
    _verify_runtime_identity(Path(bootstrap), identity)
    resolved_cwd = Path(cwd).resolve() if cwd is not None else Path.cwd()
    pool_root = _runtime_pool_root(environment_path)
    uv_cache_dir = (pool_root / UV_CACHE_RELATIVE_PATH).resolve()
    uv_executable = _find_uv_executable(bootstrap)
    if uv_executable is not None:
        uv_cache_dir.mkdir(parents=True, exist_ok=True)
    environment_path.parent.mkdir(parents=True, exist_ok=True)
    log(f"[MaaFW Runtime Pool] 创建共享环境: {environment_path}")
    environment_installer = _create_environment(
        environment_path,
        bootstrap,
        uv_executable=uv_executable,
        uv_cache_dir=uv_cache_dir,
        cwd=resolved_cwd,
        log=log,
    )

    python_executable = _venv_python(environment_path)
    # 兜底路径可能换了解释器，manifest 里的 identity 取自宿主进程，
    # 必须在落盘前对账，避免声明的 ABI 与实际 runtime 不一致。
    probe = _verify_runtime_identity(python_executable, identity)
    log(f"[MaaFW Runtime Pool] 安装依赖: {', '.join(requirements)}")
    if uv_executable is not None:
        _install_requirements_with_uv(
            uv_executable,
            python_executable,
            requirements,
            cache_dir=uv_cache_dir,
            link_mode=UV_LINK_MODE,
            cwd=resolved_cwd,
        )
        dependency_installer = "uv-pip"
        resolved_requirements = _resolved_requirements_with_uv(
            uv_executable,
            python_executable,
            cache_dir=uv_cache_dir,
        )
    else:
        _install_requirements_with_pip(
            python_executable,
            requirements,
            cwd=resolved_cwd,
        )
        dependency_installer = "pip"
        resolved_requirements = _resolved_requirements(python_executable)
    version = _installed_maafw_version(python_executable)
    installer_name = "uv" if uv_executable is not None else "pip"
    installer_metadata = {
        "installer": {
            "name": installer_name,
            "version": (
                _uv_version(uv_executable)
                if uv_executable is not None
                else _pip_version(python_executable)
            ),
            "executable": (
                str(Path(uv_executable).resolve())
                if uv_executable is not None
                else str(python_executable)
            ),
            "environment": environment_installer,
            "dependencies": dependency_installer,
        },
        "cache": {
            "kind": "uv" if uv_executable is not None else "pip-default",
            "scope": "pool" if uv_executable is not None else "external",
            "shared": uv_executable is not None,
            "path": str(uv_cache_dir) if uv_executable is not None else None,
            "relativeToPool": (
                UV_CACHE_RELATIVE_PATH.as_posix() if uv_executable is not None else None
            ),
        },
        "link": {
            "mode": UV_LINK_MODE if uv_executable is not None else "pip-default",
        },
    }
    return {
        "pythonExecutable": str(python_executable),
        "pythonVersion": probe.get("version") or platform.python_version(),
        "maafwVersion": version,
        "resolvedRequirements": resolved_requirements,
        **installer_metadata,
    }


def _create_environment(
    environment_path: Path,
    bootstrap: str,
    *,
    uv_executable: str | None,
    uv_cache_dir: Path,
    cwd: Path,
    log: Callable[[str], None],
) -> str:
    """创建共享 runtime venv；引导解释器缺 venv 模块时回退到 uv。

    绿色免安装包随附的 environment/python 是 embeddable 发行版
    （python3xx._pth，不含 Lib/venv），`python.exe -m venv` 会直接报
    "No module named venv"。必须先探测，不合格再走 uv 兜底。
    """

    if _python_supports_venv(bootstrap):
        command = [bootstrap, "-m", "venv"]
        if uv_executable is not None:
            # uv installs and audits dependencies itself; avoid seeding a
            # private pip/setuptools copy into every selector environment.
            command.append("--without-pip")
        command.append(str(environment_path))
        _run(
            command,
            cwd=cwd,
            env=_clean_process_environment(),
        )
        return "stdlib-venv"
    log(
        "[MaaFW Runtime Pool] 引导 Python 缺少 venv 模块"
        "（便携版常见 embeddable 发行版），改用 uv 创建共享环境"
    )
    if uv_executable is None:
        raise RuntimeError(
            "MaaFW runtime 安装失败：引导 Python 不含 venv 模块"
            "（便携版常见 embeddable 发行版），且未找到 uv 兜底。"
            "请提供完整 Python 或在 environment/python/Scripts 下放置 uv。"
        )
    _create_environment_with_uv(
        environment_path,
        bootstrap=bootstrap,
        uv_executable=uv_executable,
        uv_cache_dir=uv_cache_dir,
        cwd=cwd,
        log=log,
    )
    return "uv-venv"


def _create_environment_with_uv(
    environment_path: Path,
    *,
    cwd: Path,
    bootstrap: str,
    uv_executable: str,
    uv_cache_dir: Path,
    log: Callable[[str], None],
) -> None:
    log(
        f"[MaaFW Runtime Pool] uv 创建共享环境 (python {bootstrap}): {environment_path}"
    )
    _run(
        [
            uv_executable,
            "venv",
            "--python",
            bootstrap,
            "--no-python-downloads",
            "--no-project",
            "--cache-dir",
            str(uv_cache_dir),
            "--link-mode",
            UV_LINK_MODE,
            str(environment_path),
        ],
        cwd=cwd,
        env=_uv_environment(uv_cache_dir, UV_LINK_MODE),
        timeout=UV_VENV_TIMEOUT_SECONDS,
    )


def _normalize_python_constraint(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise RuntimeError("MaaFW runtime python.constraint cannot be empty")
    if re.fullmatch(r"\d+\.\d+", normalized):
        return f"=={normalized}.*"
    return normalized


def _parse_python_constraint(value: str) -> SpecifierSet:
    try:
        return SpecifierSet(value)
    except InvalidSpecifier as exc:
        raise RuntimeError(f"invalid MaaFW runtime Python constraint: {value}") from exc


def _matching_supported_python_minors(specifier: SpecifierSet) -> list[str]:
    matches: list[str] = []
    for major, minor in SUPPORTED_CPYTHON_MINORS:
        if any(
            specifier.contains(
                Version(f"{major}.{minor}.{patch}"),
                prereleases=True,
            )
            for patch in range(1000)
        ):
            matches.append(f"{major}.{minor}")
    return matches


def _minor_family_fully_satisfies(
    specifier: SpecifierSet,
    target_minor: str,
) -> bool:
    return all(
        specifier.contains(
            Version(f"{target_minor}.{patch}"),
            prereleases=True,
        )
        for patch in range(1000)
    )


def _exact_python_patch_target(specifier: SpecifierSet) -> str | None:
    """Return one exact CPython patch requested by ``==``/``===``.

    Other range constraints continue to select a compatible supported minor
    and are verified against the interpreter probe.  Exact patch requests
    must be passed to uv unchanged; asking uv only for ``3.13`` could otherwise
    return a different installed patch and make the request impossible to
    satisfy deterministically.
    """

    targets: set[str] = set()
    for item in specifier:
        if item.operator not in {"==", "==="} or "*" in item.version:
            continue
        try:
            version = Version(item.version)
        except InvalidVersion:
            continue
        release = version.release
        if len(release) < 3:
            continue
        targets.add(".".join(str(part) for part in release[:3]))
    if len(targets) > 1:
        raise RuntimeError(
            "MaaFW runtime Python constraint contains conflicting exact patches: "
            + ", ".join(sorted(targets))
        )
    return next(iter(targets), None)


def _python_probe_satisfies(
    probe: Mapping[str, Any],
    implementation: str,
    specifier: SpecifierSet,
) -> bool:
    if str(probe.get("implementation") or "").strip().casefold() != implementation:
        return False
    try:
        version = Version(str(probe.get("version") or "").strip())
    except InvalidVersion:
        return False
    return specifier.contains(version, prereleases=True)


def _configured_python_executable(target_version: str) -> Path | None:
    version_key = target_version.replace(".", "_")
    for env_name in (
        f"AUTO_MAS_PYTHON_{version_key}_EXE",
        "AUTO_MAS_PYTHON_EXE",
    ):
        configured = str(os.environ.get(env_name) or "").strip()
        if not configured:
            continue
        path = Path(configured)
        if not path.is_file():
            raise RuntimeError(
                f"configured MaaFW runtime Python does not exist: {path}"
            )
        return path.resolve()
    return None


def _pool_python_environment(
    python_root: Path,
    cache_dir: Path,
) -> dict[str, str]:
    env = _uv_environment(cache_dir, UV_LINK_MODE)
    env["UV_PYTHON_INSTALL_DIR"] = str(python_root)
    if not str(env.get("UV_PYTHON_INSTALL_MIRROR") or "").strip():
        mirror = str(
            os.environ.get(AUTO_MAS_UV_PYTHON_INSTALL_MIRROR_ENV) or ""
        ).strip()
        if mirror:
            env["UV_PYTHON_INSTALL_MIRROR"] = mirror
    return env


def _find_pool_managed_python(
    uv_executable: str,
    target_version: str,
    *,
    pool_root: Path,
    python_root: Path,
    cache_dir: Path,
) -> Path | None:
    pool_root, python_root, cache_dir = _canonicalize_pool_paths(
        pool_root,
        python_root,
        cache_dir,
    )
    try:
        result = subprocess.run(
            [
                uv_executable,
                "python",
                "find",
                f"cpython-{target_version}",
                "--managed-python",
                "--no-project",
                "--no-python-downloads",
                "--resolve-links",
                "--cache-dir",
                str(cache_dir),
            ],
            capture_output=True,
            timeout=VENV_PROBE_TIMEOUT_SECONDS,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=pool_root,
            env=_pool_python_environment(python_root, cache_dir),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("MaaFW runtime pool-local Python lookup failed") from exc
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    if not output:
        return None
    executable = Path(output).resolve()
    try:
        common = os.path.commonpath(
            [os.path.normcase(str(executable)), os.path.normcase(str(python_root))]
        )
    except ValueError as exc:
        common = ""
        path_error = exc
    else:
        path_error = None
    if common != os.path.normcase(str(python_root)):
        raise RuntimeError(
            f"uv returned a managed Python outside the runtime pool: {executable}"
        ) from path_error
    if not executable.is_file():
        return None
    return executable


def _install_pool_managed_python(
    uv_executable: str,
    target_version: str,
    *,
    pool_root: Path,
    python_root: Path,
    cache_dir: Path,
) -> None:
    pool_root, python_root, cache_dir = _canonicalize_pool_paths(
        pool_root,
        python_root,
        cache_dir,
    )
    _run(
        [
            uv_executable,
            "python",
            "install",
            f"cpython-{target_version}",
            "--install-dir",
            str(python_root),
            "--no-bin",
            "--no-registry",
            "--cache-dir",
            str(cache_dir),
            "--no-progress",
        ],
        cwd=pool_root,
        env=_pool_python_environment(python_root, cache_dir),
        timeout=UV_PYTHON_INSTALL_TIMEOUT_SECONDS,
    )


def _select_uv_python_version(
    uv_executable: str,
    specifier: SpecifierSet,
    target_minors: Sequence[str],
    *,
    pool_root: Path,
    python_root: Path,
    cache_dir: Path,
    only_installed: bool,
) -> str | None:
    """Select the newest real uv catalog version satisfying a patch range."""

    pool_root, python_root, cache_dir = _canonicalize_pool_paths(
        pool_root,
        python_root,
        cache_dir,
    )

    scope_flag = "--only-installed" if only_installed else "--only-downloads"
    try:
        result = subprocess.run(
            [
                uv_executable,
                "python",
                "list",
                "cpython",
                "--all-versions",
                scope_flag,
                "--output-format",
                "json",
                "--managed-python",
                "--no-config",
                "--cache-dir",
                str(cache_dir),
            ],
            capture_output=True,
            timeout=VENV_PROBE_TIMEOUT_SECONDS,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=pool_root,
            env=_pool_python_environment(python_root, cache_dir),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("MaaFW runtime uv Python catalog lookup failed") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            "MaaFW runtime uv Python catalog lookup failed "
            f"(exit={result.returncode}): {detail[:800]}"
        )
    try:
        rows = json.loads(result.stdout)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "MaaFW runtime uv Python catalog returned invalid JSON"
        ) from exc
    if not isinstance(rows, list):
        raise RuntimeError("MaaFW runtime uv Python catalog must return a JSON array")

    allowed_minors = set(target_minors)
    candidates: list[Version] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("implementation") or "").casefold() != "cpython":
            continue
        raw_version = str(row.get("version") or "").strip()
        try:
            version = Version(raw_version)
        except InvalidVersion:
            continue
        release = version.release
        if len(release) < 2 or f"{release[0]}.{release[1]}" not in allowed_minors:
            continue
        if not specifier.contains(version, prereleases=True):
            continue
        if only_installed:
            raw_path = str(row.get("path") or "").strip()
            if not raw_path:
                continue
            installed_path = Path(raw_path).resolve()
            try:
                common = os.path.commonpath(
                    [
                        os.path.normcase(str(installed_path)),
                        os.path.normcase(str(python_root)),
                    ]
                )
            except ValueError:
                continue
            if common != os.path.normcase(str(python_root)):
                continue
        candidates.append(version)
    if not candidates:
        return None
    return str(max(candidates))


def _canonicalize_pool_paths(
    pool_root: Path,
    python_root: Path,
    cache_dir: Path,
) -> tuple[Path, Path, Path]:
    """Normalize uv-managed paths and keep them inside the owning pool."""

    resolved_pool = Path(pool_root).resolve()
    resolved_python = Path(python_root).resolve()
    resolved_cache = Path(cache_dir).resolve()
    for label, candidate in (
        ("python", resolved_python),
        ("cache", resolved_cache),
    ):
        if not _path_is_within(candidate, resolved_pool):
            raise RuntimeError(
                f"runtime pool {label} path escapes the pool: {candidate}"
            )
    return resolved_pool, resolved_python, resolved_cache


def _path_is_within(path: Path, base: Path) -> bool:
    try:
        common = os.path.commonpath(
            [os.path.normcase(str(path)), os.path.normcase(str(base))]
        )
    except ValueError:
        return False
    return common == os.path.normcase(str(base))


def _python_supports_venv(python: str) -> bool:
    """探测解释器是否带 venv/ensurepip 标准库。"""

    try:
        result = subprocess.run(
            [python, "-c", "import venv, ensurepip"],
            capture_output=True,
            timeout=VENV_PROBE_TIMEOUT_SECONDS,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _find_uv_executable(bootstrap: str) -> str | None:
    configured_uv = os.environ.get("AUTO_MAS_UV_EXE")
    if configured_uv:
        configured_path = Path(configured_uv)
        if configured_path.is_file():
            return str(configured_path.resolve())

    bootstrap_path = Path(bootstrap).resolve()
    bootstrap_candidates = (
        bootstrap_path.parent / "uv.exe",
        bootstrap_path.parent / "Scripts" / "uv.exe",
    )
    for bootstrap_uv in bootstrap_candidates:
        if bootstrap_uv.is_file():
            return str(bootstrap_uv)

    portable_uv = Path.cwd() / "environment" / "python" / "Scripts" / "uv.exe"
    if portable_uv.is_file():
        return str(portable_uv)
    return shutil.which("uv")


def _runtime_pool_root(environment_path: Path) -> Path:
    """Infer the owning pool root from ``.staging/<id>/environment``."""

    resolved = environment_path.resolve()
    stage_dir = resolved.parent
    staging_root = stage_dir.parent
    if staging_root.name == RUNTIME_POOL_STAGING_DIRECTORY_NAME:
        return staging_root.parent
    # Direct installer calls (including contract tests) have no pool object.
    # Keep their cache beside the staging parent rather than in process-global
    # uv state.
    return staging_root


def _install_requirements_with_uv(
    uv_executable: str,
    python_executable: Path,
    requirements: Sequence[str],
    *,
    cache_dir: Path,
    link_mode: str,
    cwd: Path,
) -> None:
    index_args: list[str] = []
    if not any(
        str(os.environ.get(name) or "").strip()
        for name in ("UV_INDEX_URL", "UV_DEFAULT_INDEX")
    ):
        index_url = str(os.environ.get(AUTO_MAS_UV_INDEX_URL_ENV) or "").strip()
        if index_url:
            index_args = ["--index-url", index_url]
    _run(
        [
            uv_executable,
            "pip",
            "install",
            "--python",
            str(python_executable),
            "--cache-dir",
            str(cache_dir),
            "--link-mode",
            link_mode,
            "--upgrade",
            "--quiet",
            *index_args,
            *requirements,
        ],
        cwd=cwd,
        env=_uv_install_environment(
            python_executable.parent.parent,
            cache_dir,
            link_mode,
        ),
    )


def _install_requirements_with_pip(
    python_executable: Path,
    requirements: Sequence[str],
    *,
    cwd: Path,
) -> None:
    _run(
        [
            str(python_executable),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--disable-pip-version-check",
            "--quiet",
            *requirements,
        ],
        cwd=cwd,
        env=_clean_install_environment(python_executable.parent.parent),
    )


def _probe_python_identity(python_executable: Path) -> dict[str, str]:
    try:
        result = subprocess.run(
            [str(python_executable), "-c", _IDENTITY_PROBE_SCRIPT],
            capture_output=True,
            timeout=VENV_PROBE_TIMEOUT_SECONDS,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            f"MaaFW runtime ABI 探测失败：无法执行 {python_executable}"
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if "ctypes" in detail:
            # 重建 venv 救不了：ctypes 来自 base 解释器，坏的是那份 Python 本身。
            # 所以这里只快速失败并说清楚，不触发静默重建（否则会原地打转）。
            raise RuntimeError(
                "MaaFW runtime Python 自检失败：标准库 ctypes 不可用。"
                "MaaFW 绑定完全依赖 ctypes，这通常意味着这份 Python 的标准库与"
                "扩展模块来自不同构建——例如运行时被升级或替换过，而已有的运行池"
                f"仍指向它。请修复或重装该 Python 运行时。原始错误：{detail[-400:]}"
            )
        raise RuntimeError(
            f"MaaFW runtime ABI 探测失败 (exit={result.returncode}): {detail[:400]}"
        )
    try:
        payload = json.loads(result.stdout.strip())
    except (TypeError, ValueError) as exc:
        raise RuntimeError("MaaFW runtime ABI 探测返回值不是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("MaaFW runtime ABI 探测返回值不是 JSON object")
    return {str(key): str(value) for key, value in payload.items()}


def probe_python_identity(python_executable: str | Path) -> dict[str, str]:
    """Return the JSON-compatible ABI identity of one real interpreter."""

    return _probe_python_identity(Path(python_executable))


def _verify_runtime_identity(
    python_executable: Path,
    identity: dict[str, Any] | None,
) -> dict[str, str]:
    """对账新建 runtime 的实际 ABI 与 pool 声明的 identity。"""

    probe = _probe_python_identity(python_executable)
    if not identity:
        return probe
    actual_abi = (
        f"{probe.get('implementation', 'python')}:"
        f"{probe.get('cacheTag', 'unknown')}:"
        f"{probe.get('soabi', 'unknown')}"
    )
    expected_abi = str(identity.get("pythonAbi") or "").strip()
    if expected_abi and expected_abi != actual_abi:
        raise RuntimeError(
            "MaaFW runtime ABI 与 identity 声明不一致："
            f"expected={expected_abi}, actual={actual_abi}"
        )
    expected_version = str(identity.get("pythonVersion") or "").strip()
    actual_version = ""
    if expected_version:
        try:
            expected_release = Version(expected_version).release
        except InvalidVersion as exc:
            raise RuntimeError(
                f"MaaFW runtime identity 的 pythonVersion 无效：{expected_version}"
            ) from exc
        actual_version = str(
            probe.get("version", "")
            if len(expected_release) >= 3
            else probe.get("shortVersion", "")
        )
    if expected_version and expected_version != actual_version:
        raise RuntimeError(
            "MaaFW runtime Python 版本与 identity 声明不一致："
            f"expected={expected_version}, actual={actual_version}"
        )
    return probe


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = RUNTIME_INSTALL_TIMEOUT_SECONDS,
) -> None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"MaaFW runtime 安装超时: {command[:3]}") from exc
    if result.returncode == 0:
        return
    detail = (result.stderr or result.stdout or "").strip()
    raise RuntimeError(
        f"MaaFW runtime 安装失败 (exit={result.returncode}): {detail[:800]}"
    )


def _clean_process_environment() -> dict[str, str]:
    env = os.environ.copy()
    for name in (
        "PYTHONHOME",
        "PYTHONUSERBASE",
        "PYTHONPATH",
        "PIP_TARGET",
        "PIP_PREFIX",
        "PIP_USER",
    ):
        env.pop(name, None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _clean_install_environment(environment_path: Path) -> dict[str, str]:
    env = _clean_process_environment()
    scripts_dir = environment_path / ("Scripts" if os.name == "nt" else "bin")
    env["VIRTUAL_ENV"] = str(environment_path)
    env["PATH"] = f"{scripts_dir}{os.pathsep}{env.get('PATH', '')}"
    return env


def _uv_environment(cache_dir: Path, link_mode: str) -> dict[str, str]:
    env = _clean_process_environment()
    env["UV_CACHE_DIR"] = str(cache_dir)
    env["UV_LINK_MODE"] = link_mode
    return env


def _uv_install_environment(
    environment_path: Path,
    cache_dir: Path,
    link_mode: str,
) -> dict[str, str]:
    env = _clean_install_environment(environment_path)
    env["UV_CACHE_DIR"] = str(cache_dir)
    env["UV_LINK_MODE"] = link_mode
    return env


def _installed_maafw_version(python_executable: Path) -> str | None:
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
            env=_clean_install_environment(python_executable.parent.parent),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _resolved_requirements_with_uv(
    uv_executable: str,
    python_executable: Path,
    *,
    cache_dir: Path,
) -> list[str]:
    try:
        result = subprocess.run(
            [
                uv_executable,
                "pip",
                "freeze",
                "--python",
                str(python_executable),
                "--cache-dir",
                str(cache_dir),
            ],
            capture_output=True,
            timeout=RUNTIME_AUDIT_TIMEOUT_SECONDS,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_uv_install_environment(
                python_executable.parent.parent,
                cache_dir,
                UV_LINK_MODE,
            ),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("MaaFW runtime uv resolved requirements 审计失败") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            "MaaFW runtime uv pip freeze 失败 "
            f"(exit={result.returncode}): {detail[:800]}"
        )
    return _normalized_freeze_lines(result.stdout)


def _resolved_requirements(python_executable: Path) -> list[str]:
    try:
        result = subprocess.run(
            [
                str(python_executable),
                "-m",
                "pip",
                "--disable-pip-version-check",
                "freeze",
                "--all",
            ],
            capture_output=True,
            timeout=RUNTIME_AUDIT_TIMEOUT_SECONDS,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_clean_install_environment(python_executable.parent.parent),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("MaaFW runtime resolved requirements 审计失败") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            "MaaFW runtime pip freeze --all 失败 "
            f"(exit={result.returncode}): {detail[:800]}"
        )
    return _normalized_freeze_lines(result.stdout)


def _normalized_freeze_lines(output: str) -> list[str]:
    return sorted(
        {
            line.strip()
            for line in output.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        },
        key=str.casefold,
    )


def _uv_version(uv_executable: str) -> str | None:
    return _command_version([uv_executable, "--version"], prefix="uv ")


def _pip_version(python_executable: Path) -> str | None:
    return _command_version(
        [str(python_executable), "-m", "pip", "--version"],
        prefix="pip ",
        env=_clean_install_environment(python_executable.parent.parent),
    )


def _command_version(
    command: list[str],
    *,
    prefix: str,
    env: dict[str, str] | None = None,
) -> str | None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=15,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    if value.casefold().startswith(prefix.casefold()):
        value = value[len(prefix) :].strip()
    return value or None


def _venv_python(environment_path: Path) -> Path:
    if os.name == "nt":
        return environment_path / "Scripts" / "python.exe"
    return environment_path / "bin" / "python"
