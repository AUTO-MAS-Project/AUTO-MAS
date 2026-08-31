from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import platform as platform_module
import struct
import sys
import sysconfig
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from app.task.MaaFW.tools.core.automas_maafw_runtime_pool import (
    MaaFWRuntimePool,
    RuntimeInstaller,
    build_runtime_id,
    canonicalize_requirements,
    install_python_runtime,
)
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version


RUNNER_ENV_MANIFEST_NAME = ".auto_mas_maafw_runner_env.json"
PROJECT_RUNTIME_MANIFEST_NAME = ".auto_mas_maafw_project.json"
RUNNER_DEFAULT_PACKAGES = (
    "maafw",
    "pydantic==2.11.7",
    "json5==0.14.0",
    "json-with-comments",
    # worker 子进程自身要用：runner 与 worker 看门狗用 psutil，
    # runtime_pool 用 packaging。插件形态下它们由插件目录经 PYTHONPATH
    # 提供，树内没有那层，必须装进 runner venv。
    "psutil",
    "packaging",
)
RUNNER_ENV_TIMEOUT = 300
DEFAULT_RUNTIME_LEASE_TTL_SECONDS = 24 * 60 * 60
AUTOMATIC_RUNTIME_GC_GRACE_SECONDS = 7 * 24 * 60 * 60
AUTOMATIC_RUNTIME_GC_KEEP_LATEST = 1
REQUIREMENT_NAME_RE = re.compile(
    r"^\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"\s*(?:\[[^\]]+\])?\s*(?:===|[<>=!~]=?|@|;|\s|$)"
)

_AUTOMATIC_GC_ROOTS: set[str] = set()
_AUTOMATIC_GC_LOCK = threading.Lock()

EnvironmentProgressCallback = Callable[[dict[str, Any]], None]


def _report_environment_progress(
    callback: EnvironmentProgressCallback | None,
    stage: str,
    status: str,
    message: str,
    *,
    percent: float | None = None,
    **payload: Any,
) -> None:
    if callback is None:
        return
    event: dict[str, Any] = {
        "stage": stage,
        "status": status,
        "message": message,
        **payload,
    }
    if percent is not None:
        event["percent"] = percent
    try:
        callback(event)
    except Exception:
        return


@dataclass(frozen=True)
class MaaFWRunnerEnvironment:
    python_executable: Path
    venv_path: Path
    env: dict[str, str]
    packages: tuple[str, ...]
    maafw_version: str | None
    runtime_id: str | None = None
    maafw_requirement: str | None = None
    runtime_pool_root: Path | None = None
    runtime_pool_id: str | None = None
    python_constraint: str | None = None
    lease_id: str | None = None


def prepare_runner_environment(
    project_path: str | Path,
    *,
    managed_env_root: str | Path | None = None,
    runtime_pool_root: str | Path | None = None,
    runtime_pool: MaaFWRuntimePool | None = None,
    runtime_installer: RuntimeInstaller | None = None,
    runtime_requirement: str | None = None,
    runtime_requirements: Iterable[str] | None = None,
    runtime_id: str | None = None,
    runtime_pool_id: str | None = None,
    runtime_python_constraint: str | None = None,
    lease_owner: str = "automas-maafw-runner",
    lease_ttl_seconds: float | None = DEFAULT_RUNTIME_LEASE_TTL_SECONDS,
    import_paths: Iterable[str | Path] = (),
    send_log: Callable[[str], None] | None = None,
    progress: EnvironmentProgressCallback | None = None,
) -> MaaFWRunnerEnvironment:
    """Prepare or reuse a runner selected by canonical requirements.

    ``managed_env_root`` remains accepted as the legacy pool-root argument.
    Runtime identity no longer contains ``project_path``; projects with the
    same canonical requirements therefore share one worker environment.
    """

    _report_environment_progress(
        progress,
        "resolving",
        "running",
        "正在解析 MaaFW Runner 依赖",
        percent=5.0,
    )
    project = Path(project_path).resolve()
    explicit_requirements = (
        _runtime_selector_requirements(
            runtime_requirements,
            label="显式 MaaFW runtime selector",
        )
        if runtime_requirements is not None
        else None
    )
    explicit_route = (
        explicit_requirements is not None
        or runtime_requirement is not None
        or runtime_id is not None
    )
    # Explicit Managed DTOs are authoritative. Never let a writable checkout
    # sidecar override or corrupt their route.
    route = (
        {"managed": True} if explicit_route else _load_project_runtime_route(project)
    )
    managed_project = (
        bool(route.get("managed"))
        or runtime_requirement is not None
        or explicit_requirements is not None
        or runtime_id is not None
    )
    root = Path(
        runtime_pool_root
        or managed_env_root
        or (Path.cwd() / "config" / "maafw_runtime_pool")
    ).resolve()
    pool = runtime_pool or MaaFWRuntimePool(root)
    expected_pool_id = (
        str(runtime_pool_id).strip() if runtime_pool_id is not None else ""
    )
    if runtime_pool_id is not None and not expected_pool_id:
        raise RuntimeError("MaaFW Runtime Pool ID 不能为空")
    actual_pool_id = str(pool.root_identity.get("poolId") or "").strip()
    if expected_pool_id and actual_pool_id != expected_pool_id:
        raise RuntimeError(
            "MaaFW Runtime Pool 身份不匹配: "
            f"expected={expected_pool_id}, actual={actual_pool_id or '<missing>'}"
        )
    if runtime_id is not None:
        bound_runtime_id = str(runtime_id).strip() or None
    elif runtime_requirement is not None:
        # An explicit requirement selects a new identity instead of silently
        # retaining a stale manifest binding.
        bound_runtime_id = None
    else:
        bound_runtime_id = str(route.get("runtimeId") or "").strip() or None
    bound_runtime = pool.get(bound_runtime_id) if bound_runtime_id else None
    if explicit_requirements is not None:
        packages = explicit_requirements
        selector_requirement = _selector_maafw_requirement(packages)
        if runtime_requirement is not None:
            selected_requirement = _normalize_maafw_requirement(
                str(runtime_requirement),
                allow_unconstrained=False,
            )
            if selected_requirement != selector_requirement:
                raise RuntimeError(
                    "MaaFW runtime requirement 与完整 selector 不匹配: "
                    f"requirement={selected_requirement}, "
                    f"selector={selector_requirement}"
                )
        else:
            selected_requirement = selector_requirement
    elif runtime_requirement is not None:
        selected_requirement = str(runtime_requirement).strip() or None
    elif bound_runtime is not None:
        # A persisted binding is authoritative after the managed gateway has
        # recovered a missing range-selected runtime as an exact version.
        # Rebuild the complete selector from the immutable project deps plus
        # the bound MaaFW requirement, then validate its runtimeId below.
        selected_requirement = (
            str(bound_runtime.get("maafwRequirement") or "").strip() or None
        )
    else:
        selected_requirement = (
            str(route.get("runtimeRequirement") or "").strip() or None
        )
    if explicit_requirements is None:
        if selected_requirement is None:
            # 自带原生库的版本优先于 requirements.txt 的声明：我们加载的就是
            # 项目自带的那份库，binding 必须跟它一致。实测 46 个发行包里有 3 个
            # 声明是陈旧的（MAAAE 声明 5.3.0 实际 5.6.0、MaaNTE 声明 v5.10.4
            # 实际 5.10.5、MaaADr 声明 5.12.2 实际 5.12.3），另有 20 个压根
            # 没有 requirements.txt、4 个写的是无版本约束。
            selected_requirement = _bundled_project_maafw_requirement(project)
        if selected_requirement is None:
            selected_requirement = _declared_project_maafw_requirement(project)
        if selected_requirement is None and bound_runtime is not None:
            selected_requirement = (
                str(bound_runtime.get("maafwRequirement") or "").strip() or None
            )
        if selected_requirement is None and managed_project:
            raise RuntimeError(
                "MaaFW runtime 未绑定且项目未声明 runtime constraint；"
                f"请在 {PROJECT_RUNTIME_MANIFEST_NAME} 中设置 runtime.constraint"
            )
        if selected_requirement is None:
            # Legacy projects keep the historical unpinned default. Managed
            # project-store entries must always provide a constraint or binding.
            selected_requirement = "maafw"
        selected_requirement = _normalize_maafw_requirement(
            selected_requirement,
            allow_unconstrained=not managed_project,
        )
        packages = tuple(
            build_runner_packages(
                project,
                maafw_requirement=selected_requirement,
            )
        )
    normalized_python_constraint = _normalize_python_constraint(
        runtime_python_constraint
    )
    if normalized_python_constraint is not None and (
        explicit_requirements is None or not bound_runtime_id
    ):
        raise RuntimeError(
            "MaaFW Managed Python constraint 必须随完整 selector/runtimeId 注入"
        )
    if explicit_requirements is not None and bound_runtime_id:
        if bound_runtime is None:
            raise RuntimeError(f"MaaFW Managed runtime 不存在: {bound_runtime_id}")
        try:
            bound_selector = canonicalize_requirements(
                bound_runtime.get("selectorRequirements")
                or bound_runtime.get("packages")
                or ()
            )
            requested_selector = canonicalize_requirements(packages)
        except Exception as exc:
            raise RuntimeError("MaaFW Managed runtime selector 无法验证") from exc
        if bound_selector != requested_selector:
            raise RuntimeError("MaaFW Managed runtime 的完整 selector 与可信路由不一致")
        _validate_runtime_python_constraint(
            bound_runtime,
            normalized_python_constraint,
        )
        # Pool.get() has already validated that runtimeId is derived from the
        # persisted identity. Do not recompute a Managed CP313 identity from
        # the CP312 host process.
        expected_runtime_id = bound_runtime_id
    else:
        expected_runtime_id = build_runtime_id(packages)
    _report_environment_progress(
        progress,
        "runtime_check",
        "running",
        "正在检查共享 MaaFW Runtime",
        percent=15.0,
        runtime_id=expected_runtime_id,
    )
    if bound_runtime_id and bound_runtime_id != expected_runtime_id:
        raise RuntimeError(
            "MaaFW runtime binding 与当前 canonical requirement selector 不匹配: "
            f"binding={bound_runtime_id}, expected={expected_runtime_id}"
        )

    existing_runtime = (
        bound_runtime
        if bound_runtime_id == expected_runtime_id
        else pool.get(expected_runtime_id)
    )
    if existing_runtime is None:
        _report_environment_progress(
            progress,
            "creating_runtime",
            "running",
            "正在创建共享 MaaFW Runtime",
            percent=25.0,
            runtime_id=expected_runtime_id,
        )
        _report_environment_progress(
            progress,
            "installing_runtime",
            "running",
            "正在安装 MaaFW Runner 依赖",
            percent=30.0,
            runtime_id=expected_runtime_id,
        )

    def install(
        environment_path: Path,
        requirements: tuple[str, ...] | list[str],
        identity: dict[str, object],
    ) -> dict[str, object]:
        return install_python_runtime(
            environment_path,
            requirements,
            identity,
            cwd=project,
            # Runtime identity is derived from this process' Python ABI, so
            # the created environment must use the same interpreter family.
            bootstrap_python=sys.executable,
            send_log=send_log,
        )

    if existing_runtime is not None:
        runtime = pool.touch(expected_runtime_id)
    else:
        runtime = pool.ensure(
            packages,
            installer=runtime_installer or install,
            metadata={"component": "automas-maafw-runner"},
        )
    resolved_runtime_id = str(runtime["runtimeId"])
    _report_environment_progress(
        progress,
        "runtime_ready",
        "reused" if existing_runtime is not None else "created",
        (
            "已复用共享 MaaFW Runtime"
            if existing_runtime is not None
            else "共享 MaaFW Runtime 已创建"
        ),
        percent=70.0,
        runtime_id=resolved_runtime_id,
    )
    lease_id = f"runner-{uuid.uuid4().hex}"
    runtime = pool.acquire_lease(
        resolved_runtime_id,
        lease_id,
        owner=lease_owner,
        ttl_seconds=lease_ttl_seconds,
    )
    try:
        venv_path = Path(str(runtime["venvPath"])).resolve()
        python_executable = Path(str(runtime["pythonExecutable"])).resolve()
        _collect_stale_runtimes_once(pool, send_log=send_log)
        resolved_packages = tuple(
            str(item) for item in runtime.get("packages", packages)
        )
        env = build_runner_environment(venv_path, import_paths=import_paths)
        maafw_version = str(runtime.get("maafwVersion") or "").strip() or None
        if maafw_version is None:
            maafw_version = _installed_maafw_version(python_executable, env)
        maafw_requirement = str(runtime.get("maafwRequirement") or "").strip() or None
        _send_log(
            send_log,
            f"[MaaFW Runner] 复用共享 runtime: {resolved_runtime_id} ({venv_path})",
        )
        if maafw_version:
            _send_log(send_log, f"[MaaFW Runner] 使用 MaaFW: v{maafw_version}")

        return MaaFWRunnerEnvironment(
            python_executable=python_executable,
            venv_path=venv_path,
            env=env,
            packages=resolved_packages,
            maafw_version=maafw_version,
            runtime_id=resolved_runtime_id,
            maafw_requirement=maafw_requirement,
            runtime_pool_root=pool.root,
            runtime_pool_id=actual_pool_id or None,
            python_constraint=normalized_python_constraint,
            lease_id=lease_id,
        )
    except Exception:
        pool.release_lease(resolved_runtime_id, lease_id)
        raise


def release_runner_environment(
    environment: MaaFWRunnerEnvironment,
    *,
    runtime_pool: MaaFWRuntimePool | None = None,
) -> dict[str, Any] | None:
    """Release the execution lease held by a prepared runner environment."""

    runtime_id = str(environment.runtime_id or "").strip()
    lease_id = str(environment.lease_id or "").strip()
    if not runtime_id or not lease_id:
        return None
    pool = runtime_pool
    if pool is None:
        if environment.runtime_pool_root is None:
            return None
        pool = MaaFWRuntimePool(environment.runtime_pool_root)
    return pool.release_lease(runtime_id, lease_id)


def _collect_stale_runtimes_once(
    pool: MaaFWRuntimePool,
    *,
    send_log: Callable[[str], None] | None,
) -> None:
    """Collect stale runtimes once per pool root for this process.

    The current runtime already holds a lease when this runs, so pool GC keeps
    it along with pinned, referenced, recently used, and keep-latest runtimes.
    Cleanup is maintenance rather than a run prerequisite: failures are logged
    without blocking the first run or retrying in this process.
    """

    root_key = os.path.normcase(str(pool.root.resolve()))
    with _AUTOMATIC_GC_LOCK:
        if root_key in _AUTOMATIC_GC_ROOTS:
            return
        _AUTOMATIC_GC_ROOTS.add(root_key)

    try:
        result = pool.gc(
            dry_run=False,
            grace_seconds=AUTOMATIC_RUNTIME_GC_GRACE_SECONDS,
            keep_latest=AUTOMATIC_RUNTIME_GC_KEEP_LATEST,
        )
    except Exception as exc:
        _send_log(
            send_log,
            f"[MaaFW Runner] 过时 runtime 自动清理失败，继续运行: {exc}",
        )
        return

    deleted = [str(item) for item in result.get("deleted", [])]
    errors = [item for item in result.get("errors", []) if isinstance(item, Mapping)]
    if deleted:
        _send_log(
            send_log,
            "[MaaFW Runner] 已清理过时 runtime: " + ", ".join(deleted),
        )
    if errors:
        _send_log(
            send_log,
            f"[MaaFW Runner] 部分过时 runtime 清理失败，继续运行: {errors}",
        )
    cache_prune = result.get("cachePrune")
    if isinstance(cache_prune, Mapping):
        status = str(cache_prune.get("status") or "unknown")
        if status == "pruned":
            _send_log(
                send_log,
                "[MaaFW Runner] uv 缓存清理完成: "
                f"removedFiles={int(cache_prune.get('removedFiles') or 0)}, "
                f"removedBytes={int(cache_prune.get('removedBytes') or 0)}",
            )
        elif status in {"disabled", "error", "unavailable", "unsafe"}:
            detail = str(cache_prune.get("error") or "no detail")
            _send_log(
                send_log,
                "[MaaFW Runner] uv 缓存清理未完成，继续运行: "
                f"status={status}, error={detail}",
            )


def build_runner_packages(
    project_path: str | Path,
    *,
    maafw_requirement: str | None = None,
) -> list[str]:
    project_packages = _load_requirements(Path(project_path).resolve())
    if maafw_requirement is not None:
        project_packages = [
            requirement
            for requirement in project_packages
            if requirement_distribution_name(requirement) != "maafw"
        ]
        project_packages.append(maafw_requirement)
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


def _load_project_runtime_route(project_path: Path) -> dict[str, Any]:
    manifest_path = project_path / PROJECT_RUNTIME_MANIFEST_NAME
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"managed": False}
    except Exception as exc:
        raise RuntimeError(
            f"MaaFW project manifest 解析失败: {manifest_path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"MaaFW project manifest 必须是 JSON 对象: {manifest_path}")

    runtime_payload = payload.get("runtime")
    runtime = runtime_payload if isinstance(runtime_payload, Mapping) else {}
    raw_constraint = runtime.get("constraint", payload.get("runtimeConstraint"))
    raw_binding = runtime.get("binding", payload.get("runtimeBinding"))
    binding_id = ""
    if isinstance(raw_binding, str):
        binding_id = raw_binding.strip()
    elif isinstance(raw_binding, Mapping):
        binding_id = str(
            raw_binding.get("runtimeId")
            or raw_binding.get("runtime_id")
            or raw_binding.get("id")
            or ""
        ).strip()
    constraint = _runtime_constraint_text(raw_constraint)
    route: dict[str, Any] = {"managed": True}
    if constraint:
        route["runtimeRequirement"] = constraint
    if binding_id:
        route["runtimeId"] = binding_id
    return route


def _runtime_constraint_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, Mapping):
        return ""
    requirement = value.get("requirement") or value.get("specifier")
    if isinstance(requirement, str) and requirement.strip():
        return requirement.strip()
    version = value.get("version")
    return (
        f"=={version.strip()}" if isinstance(version, str) and version.strip() else ""
    )


# 内置运行能驱动的最低 MaaFramework 版本。
#
# runner 侧 import 了 ``maa.event_sink``，而该模块是 **5.0.0** 才加进 py binding
# 的：逐个 minor 首版查过 PyPI 上的 wheel，4.0.0 到 4.5.0 全部没有它，5.0.0 起
# 才有。装上更老的 binding，worker 会在启动时 ``ModuleNotFoundError``。
#
# MaaFramework 上游自己的支持线更高——5.1 之前一律不再支持。这里取 5.0.0 是
# 因为它是**本代码实际需要**的下限，不替上游表态。
#
# 官方目录里踩线的项目（2026-08-30 勘察）：MMleo 自带 4.5.3、MaaEOV 自带 4.5.6。
# 这两个用内置运行跑不起来，属已知边界而非缺陷——太老的不支持是正常的。
MINIMUM_SUPPORTED_MAAFW_VERSION = "5.0.0"

PROJECT_MAAFW_DLL_NAME = "MaaFramework.dll"

# 兜底搜索的最大深度。真实布局最深是 ``runtimes/<rid>/native``（3 层），
# 留一层余量吸收未来的挪动；再深就会扫进 ``python/Lib/site-packages/maa/bin``
# 那种项目自带解释器的副本，那是 agent 的，不是外壳的。
_RUNTIME_SEARCH_MAX_DEPTH = 4

# MaaFramework 把自身版本以 ``v5.13.0-beta.2`` 这样的形式内嵌在原生库里。
# 用已知版本的样本校验过：来自 ``maafw==5.12.3`` 包的那份原生库提取出的正是
# ``5.12.3``，说明取到的确实是它自己的版本而非别的字符串。
_MAAFW_DLL_VERSION_RE = re.compile(
    rb"(?<![0-9A-Za-z.])v(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)(?![0-9A-Za-z.])"
)


def _iter_project_maafw_candidates(project_path: Path):
    """按优先级产出可能放着 MaaFramework.dll 的目录。

    先枚举已知布局，再退到有界的逐层搜索——不写死具体 rid，也不指望布局
    永远不变。
    """

    yield project_path / "maafw"

    runtimes = project_path / "runtimes"
    if runtimes.is_dir():
        # .NET 把原生库放在 runtimes/<rid>/native/ 下（MFAAvalonia 即如此）。
        # 用枚举而不是钉死 win-x64，arm64 / linux-x64 同样能命中。
        try:
            rids = [item for item in sorted(runtimes.iterdir()) if item.is_dir()]
        except OSError:
            return
        for rid in rids:
            yield rid / "native"
        for rid in rids:
            yield rid


def _search_project_maafw_dll(project_path: Path) -> Path | None:
    """逐层就近搜索，返回最浅的那一份。"""

    frontier = [project_path]
    for _ in range(_RUNTIME_SEARCH_MAX_DEPTH):
        following: list[Path] = []
        for directory in frontier:
            try:
                entries = sorted(directory.iterdir())
            except OSError:
                continue
            for item in entries:
                if item.is_dir():
                    following.append(item)
                elif item.name == PROJECT_MAAFW_DLL_NAME:
                    return directory
        if not following:
            break
        frontier = following
    return None


def project_maafw_runtime_path(project_path: Path | None) -> Path | None:
    """项目自带的 MaaFramework 运行时目录。

    优先用项目自己的原生库而不是 runner venv 里那份：同一个版本号下二进制未必
    相同（实测 MaaYYs 与 MaaEnd 自带的 MaaFramework.dll 互不相同，也都不同于
    PyPI 的 maafw 包），项目的自定义构建只有用它自己的库才对得上。
    """

    if project_path is None:
        return None

    for candidate in _iter_project_maafw_candidates(project_path):
        if (candidate / PROJECT_MAAFW_DLL_NAME).is_file():
            return candidate
    return _search_project_maafw_dll(project_path)


_PE_SIGNATURE = bytes((0x50, 0x45, 0x00, 0x00))  # PE signature
# PE 头里的 machine 字段 -> 架构名。取值来自 PE/COFF 规范。
_PE_MACHINE_ARCHITECTURES = {
    0x014C: "x86",
    0x8664: "x64",
    0xAA64: "arm64",
}


def detect_pe_architecture(path: Path) -> str | None:
    """读出 PE 文件的目标架构，**不映射也不执行它**。

    只解析 DOS 头里的 e_lfanew 偏移、跳到 PE 签名、再读两字节 machine 字段。
    做法取自 mfwa 的 ``tools/runtime/probe.py``。

    Returns:
        ``"x86"`` / ``"x64"`` / ``"arm64"``；不是 PE 文件或读不出来时 None。
    """

    try:
        with path.open("rb") as stream:
            if stream.read(2) != b"MZ":
                return None
            stream.seek(0x3C)
            offset_bytes = stream.read(4)
            if len(offset_bytes) != 4:
                return None
            stream.seek(int.from_bytes(offset_bytes, "little"))
            if stream.read(4) != _PE_SIGNATURE:
                return None
            machine = int.from_bytes(stream.read(2), "little")
    except (OSError, ValueError):
        return None
    return _PE_MACHINE_ARCHITECTURES.get(machine)


def host_architecture() -> str:
    """当前解释器进程的架构。"""

    if struct.calcsize("P") == 8:
        machine = platform_module.machine().casefold()
        return "arm64" if "arm" in machine or "aarch" in machine else "x64"
    return "x86"


def describe_runtime_architecture_mismatch(runtime_path: Path | None) -> str | None:
    """项目自带的原生库架构与本机不符时给出可读原因。

    不符时 ``Library.open`` 必然失败，但原生层报的错难以定位到「装错了包」。
    提前判断只是把同一个失败说清楚，不会挡下任何原本能跑的情况。

    典型场景：arm64 机器上装了 win-x86_64 的发行包（或反之）——MaaFramework
    的项目普遍两种都发，选错了很难自己看出来。
    """

    if runtime_path is None:
        return None
    dll = runtime_path / PROJECT_MAAFW_DLL_NAME
    found = detect_pe_architecture(dll)
    if found is None:
        return None  # 读不出来就不猜，交给原生层去报
    expected = host_architecture()
    if found == expected:
        return None
    return (
        f"项目自带的 MaaFramework 是 {found} 架构，本机是 {expected}——"
        "多半是下载了不匹配的发行包，请换成对应架构的包"
    )


def probe_bundled_maafw_version(project_path: Path) -> str | None:
    """读出项目自带原生库的版本，规范化成 PEP 440。

    ``v5.13.0-beta.2`` -> ``5.13.0b2``，正好对得上 PyPI 上的预发布版本号。
    只在原生库里恰好存在唯一一个版本串时才采信——多于一个说明这个提取方式
    对该构建不成立，宁可返回 None 走原有兜底。
    """

    runtime_path = project_maafw_runtime_path(project_path)
    if runtime_path is None:
        return None
    try:
        data = (runtime_path / PROJECT_MAAFW_DLL_NAME).read_bytes()
    except OSError:
        return None

    found = {
        match.group(1).decode("ascii", errors="ignore")
        for match in _MAAFW_DLL_VERSION_RE.finditer(data)
    }
    if len(found) != 1:
        return None
    try:
        return str(Version(found.pop()))
    except InvalidVersion:
        return None


def _bundled_project_maafw_requirement(project_path: Path) -> str | None:
    """按项目自带原生库的版本钉 Python binding。

    MaaFW 的 py binding 与原生库是绑定关系，跨 minor 混用不报错但行为可能不同。
    我们加载的就是项目自带的那份库（见 ``project_maafw_runtime_path``），
    所以 binding 必须跟它一致——这比 ``requirements.txt`` 的声明更可靠。

    对 MaaFramework 官方目录里 46 个 Windows 发行包做过远程勘察，结论：

    - 涉及 10 个不同的 FW 版本（4.5.3 到 5.13.0-beta.5），**PyPI 上全都有**
    - 20 个包没有 requirements.txt（agent 是 Go/C++ 或纯 Pipeline 的项目）
    - 4 个写的是无版本约束的 ``maafw`` / ``MaaFw``
    - **3 个的声明与实际发行的库对不上**：MAAAE 声明 5.3.0 实际 5.6.0、
      MaaNTE 声明 v5.10.4 实际 5.10.5、MaaADr 声明 5.12.2 实际 5.12.3

    从库二进制里读出的版本可直接对上 PyPI 的包：抽查 4.5.3 / 5.6.0 / 5.10.2 /
    5.12.2 四个版本，项目自带的库与对应 wheel 里的**逐字节相同**；本机另验过
    5.13.0b2 与 5.13.0b5 亦然。
    """

    version = probe_bundled_maafw_version(project_path)
    return f"maafw=={version}" if version else None


def _declared_project_maafw_requirement(project_path: Path) -> str | None:
    matches = [
        requirement
        for requirement in _load_requirements(project_path)
        if requirement_distribution_name(requirement) == "maafw"
    ]
    if len(matches) > 1:
        raise RuntimeError("项目 requirements.txt 声明了多个 MaaFW runtime requirement")
    return matches[0] if matches else None


def _normalize_python_constraint(value: str | None) -> str | None:
    if value is None:
        return None
    raw_value = str(value).strip()
    if not raw_value:
        raise RuntimeError("MaaFW Managed Python constraint 不能为空")
    try:
        normalized = str(SpecifierSet(raw_value))
    except InvalidSpecifier as exc:
        raise RuntimeError(
            f"无效的 MaaFW Managed Python constraint: {raw_value}"
        ) from exc
    if not normalized:
        raise RuntimeError("MaaFW Managed Python constraint 不能为空")
    return normalized


def _validate_runtime_python_constraint(
    runtime: Mapping[str, Any],
    constraint: str | None,
) -> None:
    if constraint is None:
        return
    identity = runtime.get("identity")
    identity_data = dict(identity) if isinstance(identity, Mapping) else {}
    python_abi = str(identity_data.get("pythonAbi") or "").strip().casefold()
    if not python_abi.startswith("cpython:"):
        raise RuntimeError("MaaFW Managed runtime 缺少可信 CPython identity.pythonAbi")
    python_version = str(identity_data.get("pythonVersion") or "").strip()
    try:
        compatible = Version(python_version) in SpecifierSet(constraint)
    except (InvalidVersion, InvalidSpecifier) as exc:
        raise RuntimeError(
            "MaaFW Managed runtime 缺少可验证的 identity.pythonVersion"
        ) from exc
    if not compatible:
        raise RuntimeError(
            "MaaFW Managed runtime Python 版本不满足项目约束: "
            f"required={constraint}, actual={python_version or '<missing>'}"
        )


def _normalize_maafw_requirement(
    value: str,
    *,
    allow_unconstrained: bool = False,
) -> str:
    raw_value = value.strip()
    if not raw_value:
        raise RuntimeError("MaaFW runtime constraint 不能为空")
    if requirement_distribution_name(raw_value) != "maafw":
        if raw_value[0].isdigit() or raw_value[0] in {"v", "V"}:
            raw_value = f"maafw=={raw_value.lstrip('vV')}"
        elif raw_value[0] in {"<", ">", "=", "!", "~"}:
            raw_value = f"maafw{raw_value}"
        else:
            raise RuntimeError(f"无效的 MaaFW runtime constraint: {value}")
    try:
        requirement = Requirement(raw_value)
    except InvalidRequirement as exc:
        raise RuntimeError(f"无效的 MaaFW runtime constraint: {value}") from exc
    if canonicalize_name(requirement.name) != "maafw":
        raise RuntimeError(f"runtime constraint 必须约束 maafw: {value}")
    if (
        not allow_unconstrained
        and not requirement.url
        and not list(requirement.specifier)
    ):
        raise RuntimeError(
            "MaaFW runtime requirement 不能是未约束的 'maafw'；请显式声明版本或版本范围"
        )
    return str(requirement)


def _runtime_selector_requirements(
    value: Iterable[str],
    *,
    label: str,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise RuntimeError(f"{label} 必须是 requirement 列表")
    requirements: list[str] = []
    try:
        iterator = iter(value)
    except TypeError as exc:
        raise RuntimeError(f"{label} 必须是 requirement 列表") from exc
    for index, raw_requirement in enumerate(iterator):
        if not isinstance(raw_requirement, str) or not raw_requirement.strip():
            raise RuntimeError(f"{label}[{index}] 必须是非空字符串")
        requirements.append(raw_requirement.strip())
    if not requirements:
        raise RuntimeError(f"{label} 不能为空")
    # Canonicalization and duplicate/conflict validation are deliberately
    # delegated to the same identity builder used by Runtime Pool.
    build_runtime_id(requirements)
    return tuple(requirements)


def _selector_maafw_requirement(requirements: Iterable[str]) -> str:
    matches = [
        requirement
        for requirement in requirements
        if requirement_distribution_name(requirement) == "maafw"
    ]
    if len(matches) != 1:
        raise RuntimeError(
            "完整 MaaFW runtime selector 必须且只能包含一个 maafw requirement"
        )
    return _normalize_maafw_requirement(
        matches[0],
        allow_unconstrained=False,
    )


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
        str(Path(path).resolve()) for path in import_paths if Path(path).exists()
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
        item for item in sys.path if _normalized_sys_path(item) != normalized_path
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
