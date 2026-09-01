from __future__ import annotations

import json
import logging
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


logger = logging.getLogger("automas.maafw.runtime_pool.installer")

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
# 优先，其次是本变量，最后是 Runtime 注入的 AUTO_MAS_MIRROR_PYTHON 有序列表
# （见 _resolve_python_mirror_candidates）。
AUTO_MAS_UV_PYTHON_INSTALL_MIRROR_ENV = "AUTO_MAS_UV_PYTHON_INSTALL_MIRROR"
# 以下四个变量由 Runtime 监督器在受监督时注入（契约见
# doc/契约补充-v1-增补1.md C11 与「新增注入环境变量」一节）；未受监督时均不设置，
# 行为回退到本文件原有的池本地目录 / 单值镜像逻辑。变量名与取值格式已冻结，
# 改名或改格式须先改 Runtime 侧契约文档。
AUTO_MAS_UV_CACHE_DIR_ENV = "AUTO_MAS_UV_CACHE_DIR"
AUTO_MAS_UV_PYTHON_INSTALL_DIR_ENV = "AUTO_MAS_UV_PYTHON_INSTALL_DIR"
AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV = "AUTO_MAS_MIRROR_PACKAGE_INDEX"
AUTO_MAS_MIRROR_PYTHON_ENV = "AUTO_MAS_MIRROR_PYTHON"
RUNTIME_POOL_STAGING_DIRECTORY_NAME = ".staging"
SUPPORTED_CPYTHON_MINORS = ((3, 12), (3, 13))


def _resolve_injected_pool_directory(
    pool_root: str | Path,
    *,
    env_name: str,
    relative_default: Path,
    label: str,
) -> tuple[Path, bool]:
    """解析一个可能被 Runtime 注入覆盖的池托管目录。

    非空且为绝对路径、父目录存在时采用注入值（返回的 ``injected`` 为
    ``True``）；未设置该变量时按池本地默认目录静默回退（未受监督的今天没有
    变化）；设置了但无效（相对路径、父目录不存在）时同样回退，但记一条
    warning——这属于配置错误，不应该被默默吞掉。两种回退情形 ``injected``
    都是 ``False``：调用方（尤其是 ``_canonicalize_pool_paths``）需要这个
    事实来判断是否可以放行「路径落在 pool_root 之外」。
    """

    default_dir = (Path(pool_root).resolve() / relative_default).resolve()
    raw_value = os.environ.get(env_name)
    if raw_value is None:
        return default_dir, False
    candidate_text = raw_value.strip()
    if not candidate_text:
        return default_dir, False
    candidate = Path(candidate_text)
    if not candidate.is_absolute():
        logger.warning(
            "%s环境变量 %s 不是绝对路径，已忽略注入值并回退到池本地目录：%s",
            label,
            env_name,
            candidate_text,
        )
        return default_dir, False
    if not candidate.parent.exists():
        logger.warning(
            "%s环境变量 %s 的父目录不存在，已忽略注入值并回退到池本地目录：%s",
            label,
            env_name,
            candidate_text,
        )
        return default_dir, False
    return candidate.resolve(), True


def _resolve_uv_cache_dir_with_source(pool_root: str | Path) -> tuple[Path, bool]:
    return _resolve_injected_pool_directory(
        pool_root,
        env_name=AUTO_MAS_UV_CACHE_DIR_ENV,
        relative_default=UV_CACHE_RELATIVE_PATH,
        label="uv 缓存目录",
    )


def _resolve_python_install_dir_with_source(pool_root: str | Path) -> tuple[Path, bool]:
    return _resolve_injected_pool_directory(
        pool_root,
        env_name=AUTO_MAS_UV_PYTHON_INSTALL_DIR_ENV,
        relative_default=UV_PYTHON_RELATIVE_PATH,
        label="Python 安装目录",
    )


def resolve_uv_cache_dir(pool_root: str | Path) -> Path:
    """解析 MaaFW 运行池实际使用的 uv 缓存目录。

    受监督时优先复用 Runtime 经 ``AUTO_MAS_UV_CACHE_DIR`` 注入的受管缓存目录，
    与 Runtime 主项目共用一份 wheel 缓存；未设置、相对路径或父目录不存在时
    视为无效注入，回退到池本地目录 ``<pool_root>/cache/uv``。

    只要路径，不关心是否命中注入；需要一并知道「是否注入」时改用
    ``_resolve_uv_cache_dir_with_source``（例如 ``_canonicalize_pool_paths``
    据此判断能否放行「落在 pool_root 之外」）。
    """

    path, _injected = _resolve_uv_cache_dir_with_source(pool_root)
    return path


def resolve_python_install_dir(pool_root: str | Path) -> Path:
    """解析 MaaFW 运行池实际使用的 Python 安装目录。

    受监督时优先复用 Runtime 经 ``AUTO_MAS_UV_PYTHON_INSTALL_DIR`` 注入的受管
    Python 安装目录，与 Runtime 主项目共用同一份解释器；未设置、相对路径或
    父目录不存在时视为无效注入，回退到池本地目录 ``<pool_root>/python``。

    只要路径，不关心是否命中注入；需要一并知道「是否注入」时改用
    ``_resolve_python_install_dir_with_source``。
    """

    path, _injected = _resolve_python_install_dir_with_source(pool_root)
    return path


def _split_semicolon_list(raw: str | None) -> list[str]:
    """按 ``;`` 切分一份有序源列表，去首尾空白、丢弃空项；不做去重。"""

    if not raw:
        return []
    return [item.strip() for item in raw.split(";") if item.strip()]


def _build_ordered_candidates(*groups: Sequence[str | None]) -> list[str]:
    """按给定顺序合并多组候选值，跳过空白项并做跨组保序去重。"""

    ordered: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for raw in group:
            value = str(raw or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            ordered.append(value)
    return ordered


def resolve_package_index_candidates() -> list[str] | None:
    """解析 Python 包索引的有序候选列表，供调用方按序重试。

    优先级：单值 ``AUTO_MAS_UV_INDEX_URL``（若设置，作为用户显式首选）在前，
    随后追加 Runtime 经 ``AUTO_MAS_MIRROR_PACKAGE_INDEX`` 注入的 ``;`` 分隔有序
    列表；跨两者保序去重。全部为空时返回 ``None``，调用方应沿用 uv 默认行为。
    """

    ordered = _build_ordered_candidates(
        [os.environ.get(AUTO_MAS_UV_INDEX_URL_ENV)],
        _split_semicolon_list(os.environ.get(AUTO_MAS_MIRROR_PACKAGE_INDEX_ENV)),
    )
    return ordered or None


def _resolve_python_mirror_candidates(*, explicit_mirror: str | None) -> list[str] | None:
    """解析 Python 解释器分发源的有序候选列表，供 ``uv python install`` 按序重试。

    优先级：调用方已解析出的显式 ``UV_PYTHON_INSTALL_MIRROR``（若有）最高，
    其次是单值 ``AUTO_MAS_UV_PYTHON_INSTALL_MIRROR``，最后追加 Runtime 经
    ``AUTO_MAS_MIRROR_PYTHON`` 注入的 ``;`` 分隔有序列表；全体保序去重。
    全部为空时返回 ``None``，调用方应沿用 uv 默认行为（不设置该变量）。
    """

    ordered = _build_ordered_candidates(
        [explicit_mirror],
        [os.environ.get(AUTO_MAS_UV_PYTHON_INSTALL_MIRROR_ENV)],
        _split_semicolon_list(os.environ.get(AUTO_MAS_MIRROR_PYTHON_ENV)),
    )
    return ordered or None


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
    python_root, python_root_injected = _resolve_python_install_dir_with_source(root)
    cache_dir, cache_dir_injected = _resolve_uv_cache_dir_with_source(root)
    root, python_root, cache_dir = _canonicalize_pool_paths(
        root,
        python_root,
        cache_dir,
        python_injected=python_root_injected,
        cache_injected=cache_dir_injected,
    )
    # 下面每个下游调用内部都会用同一对 pool_root/python_root/cache_dir 再次
    # 调用 _canonicalize_pool_paths 做防御性复核；不带上这两个标记，复核会用
    # 默认值 False，把受监督时合法的「路径落在 pool_root 之外」当成 bug 拒掉。
    path_injected_kwargs = {
        "python_injected": python_root_injected,
        "cache_injected": cache_dir_injected,
    }
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
            **path_injected_kwargs,
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
            **path_injected_kwargs,
        )
        if installed_target is None:
            return None
        executable = _find_pool_managed_python(
            uv_executable,
            installed_target,
            pool_root=root,
            python_root=python_root,
            cache_dir=cache_dir,
            **path_injected_kwargs,
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
            **path_injected_kwargs,
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
        **path_injected_kwargs,
    )
    executable = _find_pool_managed_python(
        uv_executable,
        target_version,
        pool_root=root,
        python_root=python_root,
        cache_dir=cache_dir,
        **path_injected_kwargs,
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
    uv_cache_dir = resolve_uv_cache_dir(pool_root)
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
        index_metadata = _install_requirements_with_uv(
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
        index_metadata = None
    _verify_maafw_importable(python_executable)
    version = _installed_maafw_version(python_executable)
    installer_name = "uv" if uv_executable is not None else "pip"
    cache_relative_to_pool: str | None = None
    if uv_executable is not None:
        try:
            cache_relative_to_pool = uv_cache_dir.relative_to(pool_root).as_posix()
        except ValueError:
            # 受监督时 uv_cache_dir 可能是 Runtime 注入的共享目录，不在 pool_root
            # 之内——这不是错误，只是「相对池目录」这个概念本身不适用。
            cache_relative_to_pool = None
    installer_metadata: dict[str, Any] = {
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
            "relativeToPool": cache_relative_to_pool,
        },
        "link": {
            "mode": UV_LINK_MODE if uv_executable is not None else "pip-default",
        },
    }
    if index_metadata is not None:
        installer_metadata["index"] = index_metadata
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
    python_injected: bool = False,
    cache_injected: bool = False,
) -> Path | None:
    pool_root, python_root, cache_dir = _canonicalize_pool_paths(
        pool_root,
        python_root,
        cache_dir,
        python_injected=python_injected,
        cache_injected=cache_injected,
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
    python_injected: bool = False,
    cache_injected: bool = False,
) -> None:
    """按 ``_resolve_python_mirror_candidates`` 的顺序重试同一条安装命令。

    命令本身不含镜像参数——uv 只认 ``UV_PYTHON_INSTALL_MIRROR`` 环境变量，
    因此每次重试只换 env 里这一个键，命令行不变。
    """

    pool_root, python_root, cache_dir = _canonicalize_pool_paths(
        pool_root,
        python_root,
        cache_dir,
        python_injected=python_injected,
        cache_injected=cache_injected,
    )
    base_env = _uv_environment(cache_dir, UV_LINK_MODE)
    base_env["UV_PYTHON_INSTALL_DIR"] = str(python_root)
    explicit_mirror = str(base_env.get("UV_PYTHON_INSTALL_MIRROR") or "").strip() or None
    candidates = _resolve_python_mirror_candidates(explicit_mirror=explicit_mirror)

    command = [
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
    ]

    def _build_env(source: str | None) -> dict[str, str]:
        env = dict(base_env)
        if source:
            env["UV_PYTHON_INSTALL_MIRROR"] = source
        else:
            env.pop("UV_PYTHON_INSTALL_MIRROR", None)
        return env

    _run_with_source_rotation(
        lambda _source: command,
        candidates,
        cwd=pool_root,
        build_env=_build_env,
        timeout=UV_PYTHON_INSTALL_TIMEOUT_SECONDS,
        failure_label="MaaFW runtime Python 安装",
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
    python_injected: bool = False,
    cache_injected: bool = False,
) -> str | None:
    """Select the newest real uv catalog version satisfying a patch range."""

    pool_root, python_root, cache_dir = _canonicalize_pool_paths(
        pool_root,
        python_root,
        cache_dir,
        python_injected=python_injected,
        cache_injected=cache_injected,
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
    *,
    python_injected: bool = False,
    cache_injected: bool = False,
) -> tuple[Path, Path, Path]:
    """Normalize uv-managed paths and keep non-injected ones inside the owning pool.

    ``python_root``/``cache_dir`` normally derive from ``pool_root`` (via
    ``UV_PYTHON_RELATIVE_PATH`` / ``UV_CACHE_RELATIVE_PATH``) and must stay
    inside it; this containment check is a defensive sanity net against that
    invariant ever breaking, and it still applies unconditionally when the
    caller does not say otherwise — this is the ``False`` default for both
    flags, i.e. the strict/pre-C11 behaviour.

    Under supervision, ``resolve_python_install_dir``/``resolve_uv_cache_dir``
    (via their ``_with_source`` variants) may legitimately return a
    Runtime-injected shared directory outside ``pool_root`` instead
    (``AUTO_MAS_UV_PYTHON_INSTALL_DIR`` / ``AUTO_MAS_UV_CACHE_DIR``, C11).
    Callers that resolved a path this way must say so via
    ``python_injected``/``cache_injected`` so *that* path's containment check
    is skipped — every path that was not resolved from an injected env var
    (including a caller that simply omits these flags) is still asserted
    exactly as before.
    """

    resolved_pool = Path(pool_root).resolve()
    resolved_python = Path(python_root).resolve()
    resolved_cache = Path(cache_dir).resolve()
    for label, candidate, injected in (
        ("python", resolved_python, python_injected),
        ("cache", resolved_cache, cache_injected),
    ):
        if injected:
            continue
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
) -> dict[str, Any] | None:
    """按 ``resolve_package_index_candidates()`` 的顺序重试同一条安装命令。

    用户已经显式设置 ``UV_INDEX_URL``/``UV_DEFAULT_INDEX`` 时，沿用 uv 自身对
    这两个环境变量的解析，不参与本机制的候选与重试（尊重更明确的显式配置）。
    返回实际生效的索引来源与尝试序号，供调用方写入 ``installer_metadata``；
    未使用候选列表（未配置任何镜像/单值索引，或命中上面的显式旁路）时返回
    ``None``。
    """

    env = _uv_install_environment(
        python_executable.parent.parent,
        cache_dir,
        link_mode,
    )

    def _base_command(index_args: list[str]) -> list[str]:
        return [
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
        ]

    if any(
        str(os.environ.get(name) or "").strip()
        for name in ("UV_INDEX_URL", "UV_DEFAULT_INDEX")
    ):
        _run(_base_command([]), cwd=cwd, env=env)
        return None

    candidates = resolve_package_index_candidates()
    source, attempt = _run_with_source_rotation(
        lambda index_source: _base_command(
            ["--index-url", index_source] if index_source else []
        ),
        candidates,
        cwd=cwd,
        build_env=lambda _source: env,
        timeout=RUNTIME_INSTALL_TIMEOUT_SECONDS,
        failure_label="MaaFW runtime 依赖安装",
    )
    if source is None:
        return None
    return {"source": source, "attempt": attempt}


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


def _run_with_source_rotation(
    build_command: Callable[[str | None], list[str]],
    candidates: Sequence[str] | None,
    *,
    cwd: Path,
    build_env: Callable[[str | None], dict[str, str]],
    timeout: int,
    failure_label: str,
) -> tuple[str | None, int]:
    """按候选源顺序重试同一条安装命令，返回 (实际使用的源, 尝试序号)。

    ``candidates`` 为 ``None``/空时只按「不指定源」跑一次，行为与未下发候选
    列表时完全一致；返回的源是 ``None``，序号是 1。

    某次尝试以非零退出码结束（命令确实跑完了，只是失败）就记一条 warning
    （含失败来源与 stderr 尾部）后换下一个候选；全部候选都失败则抛出最后一次
    的 ``RuntimeError``。超时或进程本身无法启动（``subprocess.TimeoutExpired``
    以外的异常，例如可执行文件不存在）视为该次尝试之外的问题，不换源，直接
    向上抛出——换一个包索引或分发源不可能修好「uv 都跑不起来」。
    """

    attempts: list[str | None] = list(candidates) if candidates else [None]
    last_error: RuntimeError | None = None
    for attempt_index, source in enumerate(attempts, start=1):
        command = build_command(source)
        env = build_env(source)
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
            raise RuntimeError(f"{failure_label}超时: {command[:3]}") from exc
        if result.returncode == 0:
            return source, attempt_index
        detail = (result.stderr or result.stdout or "").strip()
        last_error = RuntimeError(
            f"{failure_label}失败 (exit={result.returncode}): {detail[:800]}"
        )
        if attempt_index < len(attempts):
            logger.warning(
                "%s失败，换下一个源重试（失败源：%s，第 %d/%d 次尝试）：%s",
                failure_label,
                source or "默认",
                attempt_index,
                len(attempts),
                detail[-400:],
            )
    if last_error is None:
        # attempts 至少一项，循环体必然至少跑过一次并设置过 last_error；
        # 走到这里说明调用方式本身有 bug。
        raise RuntimeError(f"{failure_label}重试逻辑内部错误：候选列表为空")
    raise last_error


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


def _verify_maafw_importable(python_executable: Path) -> None:
    """装完必须真的 import 得动 maa，而不是「元数据里有」。

    ``importlib.metadata.version('maafw')`` 只读包元数据，装了一半、或者解释器
    自己的标准库坏掉时它照样报得出版本号——真机上就出过这种事：运行池认为环境
    就绪，worker 起来才在 ``maa/library.py`` 第 1 行的 ``import ctypes`` 处炸掉。
    这里在写 manifest 之前拦一次，坏环境就不会被记成好的。
    """

    try:
        result = subprocess.run(
            [str(python_executable), "-c", "import maa"],
            capture_output=True,
            timeout=60,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_clean_install_environment(python_executable.parent.parent),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            f"MaaFW runtime 校验失败：无法执行 {python_executable}"
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            "MaaFW runtime 校验失败：依赖已安装但 import maa 不成功，"
            f"该环境不可用。原始错误：{detail[-400:]}"
        )


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
