from __future__ import annotations

import json
import logging
import os
import platform as platform_module
import re
import struct
import sys
import sysconfig
import threading
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from app.task.MaaFW.tools.core.automas_maafw_runtime_pool import (
    ExtraPackagesInstaller,
    MaaFWRuntimePool,
    MaaFWRuntimePoolBusyError,
    RuntimeInstaller,
    build_runtime_id,
    install_extra_packages,
    install_python_runtime,
)
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.binding import (
    BindingInfo,
    MaaFWBindingError,
    binding_environment_variables,
    binding_index_candidates,
    ensure_binding,
    exact_version_of,
    release_binding,
    resolve_binding_version,
    retain_binding,
    retained_versions,
    select_local_version,
)
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.host_environment import (
    current_subprocess_proxy,
    strip_host_python_environment,
)
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.installer import (
    MaaFWRuntimeInstallCancelled,
    host_bootstrap_python_request,
    install_cancel_scope,
    is_package_index_offline,
    raise_if_install_cancelled,
)

PROJECT_RUNTIME_MANIFEST_NAME = ".auto_mas_maafw_project.json"
#: base venv 的常量包集合：runner 三包自身的三方依赖 + maafw binding 的运行时依赖。
#: ``maafw`` 本身不装进 venv——按版本存在 ``<pool>/bindings/``，worker 靠 PYTHONPATH
#: 找到它（见 runtime_pool/binding.py）。集合是常量，所以一种宿主 Python 身份只有一套
#: venv；某个版本的 binding 多声明了这里没有的发行包时，prepare 会在池锁内把它追加
#: 装进 base（只新增不升级，manifest 记 ``extraPackages``，见 _check_binding_requires）。
BASE_RUNTIME_PACKAGES = (
    "pydantic==2.11.7",
    "json5==0.14.0",
    "json-with-comments",
    # worker 子进程自身要用：runner 与 worker 看门狗用 psutil，
    # runtime_pool 用 packaging。插件形态下它们由插件目录经 PYTHONPATH
    # 提供，树内没有那层，必须装进 runner venv。
    "psutil",
    "packaging",
    # maafw binding（maa/**）的 import 期依赖：8 个官方 wheel 的 Requires-Dist 都是这三个。
    "numpy",
    "strenum",
    "maaagentbinary",
)
#: 兼容别名：老调用方与本地测试仍按这个名字取。
RUNNER_DEFAULT_PACKAGES = BASE_RUNTIME_PACKAGES
DEFAULT_RUNTIME_LEASE_TTL_SECONDS = 24 * 60 * 60
REQUIREMENT_NAME_RE = re.compile(
    r"^\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"\s*(?:\[[^\]]+\])?\s*(?:===|[<>=!~]=?|@|;|\s|$)"
)

EnvironmentProgressCallback = Callable[[dict[str, Any]], None]

logger = logging.getLogger("automas.maafw.runner.environment")


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
        # 进度只是旁观者，不能拖垮环境准备；但要留痕，否则回调里的
        # ``no running event loop`` 这类错误就此消失。
        logger.warning("MaaFW 运行环境进度回调失败: stage=%s", stage, exc_info=True)


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
    lease_id: str | None = None
    #: 按版本存放的 binding 目录、其版本、以及池里的官方原生库目录（项目自带 DLL 时为 None）。
    binding_dir: Path | None = None
    binding_version: str | None = None
    native_dir: Path | None = None


def _raise_if_prepare_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise MaaFWRuntimeInstallCancelled("MaaFW Runner 环境准备已取消")


def prepare_runner_environment(
    project_path: str | Path,
    *,
    managed_env_root: str | Path | None = None,
    runtime_pool_root: str | Path | None = None,
    runtime_pool: MaaFWRuntimePool | None = None,
    runtime_installer: RuntimeInstaller | None = None,
    extras_installer: ExtraPackagesInstaller | None = None,
    runtime_pool_id: str | None = None,
    lease_owner: str = "automas-maafw-runner",
    lease_ttl_seconds: float | None = DEFAULT_RUNTIME_LEASE_TTL_SECONDS,
    import_paths: Iterable[str | Path] = (),
    send_log: Callable[[str], None] | None = None,
    progress: EnvironmentProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> MaaFWRunnerEnvironment:
    """备好一个项目的运行环境：唯一的 base venv + 该项目版本的 binding（+ 需要时的 native）。

    ``managed_env_root`` remains accepted as the legacy pool-root argument.
    base venv 的身份只有常量包集合 + 宿主 Python 身份，所有项目共用；项目之间的差别
    只剩「用哪个版本的 binding」和「DLL 来自副本还是池」，都在返回值里。
    ``extras_installer`` 只给测试注入：正式路径追加装包走 ``install_extra_packages``。

    ``cancel_event`` 置位后，正在跑的 uv/pip 安装子进程与 binding 下载会被终止，本函数
    以 ``MaaFWRuntimeInstallCancelled`` 结束且不会持有租约；半成品留在 staging 目录里
    被池删掉，manifest 只在安装完整成功后才写入。
    """

    _report_environment_progress(
        progress,
        "resolving",
        "running",
        "正在解析 MaaFW Runner 依赖",
        percent=5.0,
    )
    project = Path(project_path).resolve()
    route = _load_project_runtime_route(project)
    managed_project = bool(route.get("managed"))
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
    selected_requirement = _select_project_maafw_requirement(
        project,
        preselected=str(route.get("runtimeRequirement") or "").strip() or None,
        managed_project=managed_project,
    )
    packages = tuple(BASE_RUNTIME_PACKAGES)
    project_runtime_path = project_maafw_runtime_path(project)
    native_needed = project_runtime_path is None

    bootstrap_python = sys.executable
    bootstrap_python_identity: dict[str, Any] | None = None
    # 宿主是 embeddable 发行版时不能拿它建 venv（见 installer 探针注释），改用
    # 池内同小版本的托管解释器；identity 也随之取自那份解释器，别再从宿主进程推。
    bootstrap_request = host_bootstrap_python_request()
    if bootstrap_request is not None:
        bootstrap_target = pool.resolve_python(bootstrap_request, allow_install=False)
        if bootstrap_target is None:
            _report_environment_progress(
                progress,
                "installing_python",
                "running",
                "正在准备 MaaFW Runtime 的 Python 解释器",
                percent=10.0,
            )
            bootstrap_target = pool.resolve_python(
                bootstrap_request, allow_install=True
            )
        if bootstrap_target is None:  # pragma: no cover - fail-closed
            raise RuntimeError(
                "MaaFW runtime 宿主 Python 不能作引导，且池内没有可用的托管解释器"
            )
        bootstrap_python = str(bootstrap_target["executable"])
        bootstrap_python_identity = dict(bootstrap_target["identity"])
    expected_runtime_id = build_runtime_id(
        packages,
        python_identity=bootstrap_python_identity,
    )
    _report_environment_progress(
        progress,
        "runtime_check",
        "running",
        "正在检查共享 MaaFW Runtime",
        percent=15.0,
        runtime_id=expected_runtime_id,
    )

    existing_runtime = pool.get(expected_runtime_id)
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
        with install_cancel_scope(cancel_event):
            return install_python_runtime(
                environment_path,
                requirements,
                identity,
                cwd=project,
                # Runtime identity is derived from the bootstrap interpreter (this
                # process, or the pool-managed one standing in for an embeddable
                # host), so the created environment must use that same interpreter.
                bootstrap_python=bootstrap_python,
                send_log=send_log,
            )

    _raise_if_prepare_cancelled(cancel_event)
    if existing_runtime is not None:
        runtime = pool.touch(expected_runtime_id)
    else:
        runtime = pool.ensure(
            packages,
            installer=runtime_installer or install,
            metadata={"component": "automas-maafw-runner", "layout": "base"},
            python_identity=bootstrap_python_identity,
        )
    # 安装可能恰好在取消后一瞬间完成：runtime 已发布是好事，但本次调用不能再
    # 拿租约，否则取消方已经放弃等待，这份租约要拖到 TTL 过期才释放。
    _raise_if_prepare_cancelled(cancel_event)
    resolved_runtime_id = str(runtime["runtimeId"])
    venv_path = Path(str(runtime["venvPath"])).resolve()
    python_executable = Path(str(runtime["pythonExecutable"])).resolve()
    _report_environment_progress(
        progress,
        "runtime_ready",
        "reused" if existing_runtime is not None else "created",
        (
            "已复用共享 MaaFW Runtime"
            if existing_runtime is not None
            else "共享 MaaFW Runtime 已创建"
        ),
        percent=55.0,
        runtime_id=resolved_runtime_id,
    )

    # binding：按项目钉的版本从 <pool>/bindings 取，没有就下载；项目没自带 DLL 时连
    # 官方原生库一起备到 <pool>/native。
    _report_environment_progress(
        progress,
        "binding",
        "running",
        "正在准备 MaaFW Python binding",
        percent=60.0,
        runtime_id=resolved_runtime_id,
    )
    with install_cancel_scope(cancel_event):
        binding = _ensure_project_binding(
            pool,
            project,
            selected_requirement,
            native_needed=native_needed,
            base_python=python_executable,
            send_log=send_log,
        )
    _raise_if_prepare_cancelled(cancel_event)
    extras = _check_binding_requires(runtime, binding)
    if extras:
        # 在拿自己的租约之前追加（拿了之后「无活租约」永远为假）
        _report_environment_progress(
            progress,
            "installing_extras",
            "running",
            f"正在为 MaaFW binding v{binding.version} 追加安装依赖: {', '.join(extras)}",
            percent=65.0,
            runtime_id=resolved_runtime_id,
        )
        runtime = _install_binding_extras(
            pool,
            resolved_runtime_id,
            binding,
            extras,
            cwd=project,
            bootstrap_python=bootstrap_python,
            extras_installer=extras_installer,
            send_log=send_log,
            cancel_event=cancel_event,
        )
        _raise_if_prepare_cancelled(cancel_event)
    _report_environment_progress(
        progress,
        "binding_ready",
        "ready",
        f"MaaFW binding v{binding.version} 已就绪",
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
    retain_binding(pool.root, binding.version)
    try:
        resolved_packages = tuple(
            str(item) for item in runtime.get("packages", packages)
        )
        env = build_runner_environment(
            venv_path,
            import_paths=import_paths,
            pool_root=pool.root,
            binding_dir=binding.directory,
            native_dir=binding.native_directory,
            project_runtime_path=project_runtime_path,
        )
        _send_log(
            send_log,
            f"[MaaFW Runner] 复用共享 runtime: {resolved_runtime_id} ({venv_path})",
        )
        _send_log(
            send_log,
            f"[MaaFW Runner] binding maafw {binding.version}（{_describe_binding_source(binding)}）"
            + (
                f"· DLL 来自副本 {project_runtime_path}"
                if project_runtime_path is not None
                else f"· DLL 来自池 {binding.native_directory}"
            ),
        )
        return MaaFWRunnerEnvironment(
            python_executable=python_executable,
            venv_path=venv_path,
            env=env,
            packages=resolved_packages,
            maafw_version=binding.version,
            runtime_id=resolved_runtime_id,
            maafw_requirement=selected_requirement,
            runtime_pool_root=pool.root,
            runtime_pool_id=actual_pool_id or None,
            lease_id=lease_id,
            binding_dir=binding.directory,
            binding_version=binding.version,
            native_dir=binding.native_directory,
        )
    except Exception:
        release_binding(pool.root, binding.version)
        pool.release_lease(resolved_runtime_id, lease_id)
        raise


def _describe_binding_source(binding: BindingInfo) -> str:
    source = binding.source
    if source.startswith("pypi:"):
        return f"PyPI/镜像 {source[len('pypi:') :]}"
    if source.startswith("github-source:"):
        return f"GitHub 源码 {source[len('github-source:') :]}"
    if source.startswith("harvest"):
        return "自旧运行环境收割"
    return source


def _ensure_project_binding(
    pool: MaaFWRuntimePool,
    project: Path,
    requirement: str,
    *,
    native_needed: bool,
    base_python: Path,
    send_log: Callable[[str], None] | None,
) -> BindingInfo:
    """requirement → 精确版本（D14）→ ``ensure_binding``；错误改成给用户看的文案。"""

    index_candidates = binding_index_candidates()
    offline = is_package_index_offline()
    proxy_url = current_subprocess_proxy()
    try:
        version = resolve_binding_version(
            pool.root,
            requirement,
            native_needed=native_needed,
            project_path=project,
            index_candidates=index_candidates,
            offline=offline,
            proxy_url=proxy_url,
        )
        return ensure_binding(
            pool.root,
            version,
            native_needed=native_needed,
            base_python=base_python,
            index_candidates=index_candidates,
            offline=offline,
            proxy_url=proxy_url,
            check_cancelled=raise_if_install_cancelled,
            log=send_log,
        )
    except MaaFWBindingError as exc:
        raise RuntimeError(f"MaaFW binding 准备失败：{exc}") from exc


def _check_binding_requires(
    runtime: Mapping[str, Any], binding: BindingInfo
) -> list[str]:
    """对账 binding 的 Requires-Dist 与 base 已装的包；返回要追加装进 base 的声明。

    按发行名比 manifest 里的 freeze 结果（不是常量集合：pydantic 带进来的
    ``typing-extensions`` 这类传递依赖也算已装）：

    - 已装且版本满足 specifier → 什么都不做；
    - 已装但版本**不满足** → 报错「请升级 AUTO-MAS」。改常量集合是代码变更，不在运行期
      原地升级共享 venv（会撞正被别的 worker 映射着的 ``numpy._multiarray_umath.pyd``）；
    - 没装的发行名 → 返回给调用方在池锁内追加安装（D2 ``extraPackages``，只新增）。

    8 个官方版本的声明全一致（numpy / strenum / maaagentbinary），这里是「哪天上游
    多要一个依赖」的前向钩子，而不是 worker 起来才 ``ModuleNotFoundError``。
    """

    installed: dict[str, str | None] = {}
    for item in runtime.get("resolvedRequirements") or []:
        text = str(item).split(";", 1)[0].strip()
        name = requirement_distribution_name(text)
        if name is None:
            continue
        try:
            parsed = Requirement(text)
        except InvalidRequirement:
            installed.setdefault(name, None)
            continue
        specifiers = list(parsed.specifier)
        if len(specifiers) == 1 and specifiers[0].operator == "==":
            installed[name] = specifiers[0].version
        else:
            installed.setdefault(name, None)
    problems: list[str] = []
    extras: list[str] = []
    for declared in binding.requires_dist:
        try:
            parsed = Requirement(str(declared).strip())
        except InvalidRequirement:
            continue
        # 环境标记按 base 解释器求值（base 与宿主同小版本）：``extra == "test"`` 这类
        # 可选依赖不带 extra 时为假、``python_version < "3.10"`` 在 3.12 上为假，
        # 都不是硬性依赖，不能拿去 fail-closed。
        if parsed.marker is not None:
            try:
                if not parsed.marker.evaluate({"extra": ""}):
                    continue
            except Exception:  # noqa: BLE001 - 标记求值失败按「不适用」处理
                continue
        name = requirement_distribution_name(str(parsed))
        if not name:
            continue
        if name not in installed:
            # 去掉标记后的声明原样交给 uv（extras / specifier 都保留）
            parsed.marker = None
            requirement_text = str(parsed)
            if requirement_text not in extras:
                extras.append(requirement_text)
            continue
        if not list(parsed.specifier):
            continue
        actual = installed.get(name)
        if actual is None:
            continue
        try:
            if not parsed.specifier.contains(Version(actual), prereleases=True):
                problems.append(f"{declared}（base 里是 {actual}）")
        except InvalidVersion:
            continue
    if problems:
        raise RuntimeError(
            f"maafw {binding.version} 的 binding 需要 base 运行环境里没有的依赖版本："
            + "、".join(problems)
            + "；请升级 AUTO-MAS"
        )
    return extras


def _install_binding_extras(
    pool: MaaFWRuntimePool,
    runtime_id: str,
    binding: BindingInfo,
    extras: Sequence[str],
    *,
    cwd: Path,
    bootstrap_python: str,
    extras_installer: ExtraPackagesInstaller | None,
    send_log: Callable[[str], None] | None,
    cancel_event: threading.Event | None,
) -> dict[str, Any]:
    """把 binding 多声明的发行包追加装进 base（池锁内、只新增），返回刷新后的 runtime。

    判据照 §2.2：base 无别的活租约（池里查）且本进程没人正引用着 binding（预检 /
    prepare 后未 release 的运行）时才装；否则报「稍后再试」——base 正被别的 worker
    用着，哪怕只是新增文件也不在它脚下动 site-packages。
    """

    declared = ", ".join(extras)
    busy_hint = (
        f"maafw {binding.version} 的 binding 需要追加安装 {declared}，"
        "但共享的 base 运行环境正被其它任务使用，等它们结束后再试"
    )
    if retained_versions(pool.root):
        raise RuntimeError(busy_hint)

    def install(
        python_executable: Path,
        requirements: tuple[str, ...],
        installed: tuple[str, ...],
    ) -> Mapping[str, Any] | None:
        with install_cancel_scope(cancel_event):
            if extras_installer is not None:
                return extras_installer(python_executable, requirements, installed)
            return install_extra_packages(
                python_executable,
                requirements,
                pool_root=pool.root,
                installed=installed,
                cwd=cwd,
                bootstrap_python=bootstrap_python,
                send_log=send_log,
            )

    try:
        runtime = pool.install_extra_packages(runtime_id, extras, installer=install)
    except MaaFWRuntimePoolBusyError as exc:
        raise RuntimeError(f"{busy_hint}（{exc}）") from exc
    except MaaFWRuntimeInstallCancelled:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"maafw {binding.version} 的 binding 需要追加安装 {declared}，但安装失败"
            f"（与 base 已装的包冲突、或索引上没有）：{exc}"
        ) from exc
    _send_log(
        send_log,
        f"[MaaFW Runner] 已为 binding maafw {binding.version} 追加安装 {declared}",
    )
    return runtime


def release_runner_environment(
    environment: MaaFWRunnerEnvironment,
    *,
    runtime_pool: MaaFWRuntimePool | None = None,
) -> dict[str, Any] | None:
    """Release the execution lease held by a prepared runner environment."""

    runtime_id = str(environment.runtime_id or "").strip()
    lease_id = str(environment.lease_id or "").strip()
    pool = runtime_pool
    if pool is None and environment.runtime_pool_root is not None:
        pool = MaaFWRuntimePool(environment.runtime_pool_root)
    if pool is not None and environment.binding_version:
        release_binding(pool.root, environment.binding_version)
    if not runtime_id or not lease_id or pool is None:
        return None
    return pool.release_lease(runtime_id, lease_id)


def build_runner_packages(
    project_path: str | Path | None = None,
    *,
    maafw_requirement: str | None = None,
) -> list[str]:
    """base venv 的包集合：常量，与项目无关。

    ``project_path`` / ``maafw_requirement`` 保留在签名里给旧调用方对齐：maafw 不再
    进 venv，按版本存在 ``<pool>/bindings/``（见 runtime_pool/binding.py）。
    """

    del project_path, maafw_requirement
    return list(BASE_RUNTIME_PACKAGES)


def _select_project_maafw_requirement(
    project: Path,
    *,
    preselected: str | None,
    managed_project: bool,
) -> str:
    """项目会用的 maafw requirement（已规范化）。

    ``prepare_runner_environment`` 与 ``describe_runner_runtime_selection`` 共用这
    一段，两边算出的 binding 版本才不会岔开。顺序：路由 sidecar 里的 ``runtime.constraint``
    → 项目自带原生库的实测版本 → ``requirements.txt`` 的声明 → Managed 项目报错、
    普通项目回退到历史上的无约束 ``maafw``。

    自带原生库的版本优先于 requirements.txt 的声明：我们加载的就是项目自带的那份
    库，binding 必须跟它一致。实测 46 个发行包里有 3 个声明是陈旧的（MAAAE 声明
    5.3.0 实际 5.6.0、MaaNTE 声明 v5.10.4 实际 5.10.5、MaaADr 声明 5.12.2 实际
    5.12.3），另有 20 个压根没有 requirements.txt、4 个写的是无版本约束。
    """

    selected_requirement = preselected
    if selected_requirement is None:
        selected_requirement = _bundled_project_maafw_requirement(project)
    if selected_requirement is None:
        selected_requirement = _declared_project_maafw_requirement(project)
    if selected_requirement is None and managed_project:
        raise RuntimeError(
            "MaaFW runtime 未绑定且项目未声明 runtime constraint；"
            f"请在 {PROJECT_RUNTIME_MANIFEST_NAME} 中设置 runtime.constraint"
        )
    if selected_requirement is None:
        # Legacy projects keep the historical unpinned default. Managed
        # project-store entries must always provide a constraint or binding.
        selected_requirement = "maafw"
    return _normalize_maafw_requirement(
        selected_requirement,
        allow_unconstrained=not managed_project,
    )


@dataclass(frozen=True)
class RunnerRuntimeSelection:
    """``describe_runner_runtime_selection`` 的结果：项目会落到哪个 base 与哪个 binding。"""

    runtime_id: str
    maafw_requirement: str
    packages: tuple[str, ...]
    #: 精确钉住 / 本地已能定下来的 binding 版本；范围声明且本地没有候选时为 None。
    binding_version: str | None
    #: 项目没自带 DLL → 还需要池里的官方原生库。
    native_needed: bool


def describe_runner_runtime_selection(
    project_path: str | Path,
    pool: MaaFWRuntimePool,
) -> RunnerRuntimeSelection | None:
    """不联网、不建 venv：算出 ``prepare_runner_environment`` 对这个项目会选中的 base 与 binding。

    宿主侧回收对账用它把权威集合里的每个项目翻成「当前身份下应存在的 base id」和
    「应保留的 binding 版本」，推导与 prepare 走同一批 helper。Python 身份取
    ``host_bootstrap_python_request``——宿主是 embeddable 时身份来自池内托管解释器，
    它还没装时**算不出身份**，返回 None，调用方此时不得删任何 runtime。范围声明的
    binding 版本按 D14 第 1 条只看本地（本项目记住的 → 本地满足的最高），定不下来
    就是 None，调用方靠宽限兜住。项目读不出 requirement 时抛 ``RuntimeError``。
    """

    project = Path(project_path).resolve()
    route = _load_project_runtime_route(project)
    managed_project = bool(route.get("managed"))
    selected_requirement = _select_project_maafw_requirement(
        project,
        preselected=str(route.get("runtimeRequirement") or "").strip() or None,
        managed_project=managed_project,
    )
    packages = tuple(BASE_RUNTIME_PACKAGES)
    python_identity: dict[str, Any] | None = None
    bootstrap_request = host_bootstrap_python_request()
    if bootstrap_request is not None:
        target = pool.resolve_python(bootstrap_request, allow_install=False)
        if target is None:
            return None
        python_identity = dict(target["identity"])
    native_needed = project_maafw_runtime_path(project) is None
    binding_version = exact_version_of(selected_requirement)
    if binding_version is None:
        binding_version = select_local_version(
            pool.root,
            selected_requirement,
            native_needed=native_needed,
            project_path=project,
        )
    return RunnerRuntimeSelection(
        runtime_id=build_runtime_id(packages, python_identity=python_identity),
        maafw_requirement=selected_requirement,
        packages=packages,
        binding_version=binding_version,
        native_needed=native_needed,
    )


def _load_project_runtime_route(project_path: Path) -> dict[str, Any]:
    """项目目录里的路由 sidecar（``.auto_mas_maafw_project.json``）。

    只认 ``runtime.constraint``（作 requirement 来源）。``runtime.binding`` 曾经把项目
    钉到某个 runtime id 上，base 布局下 runtime 与项目无关，这个键忽略并记一条日志；
    ``runtime_requirements`` / ``runtime_id`` / ``runtime_python_constraint`` 那套 Managed
    DTO 路由全仓无写入者、盘上无文件，已删（方案 D13）。
    """

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
    if runtime.get("binding") is not None or payload.get("runtimeBinding") is not None:
        logger.info(
            "MaaFW project manifest 里的 runtime.binding 已不再使用（base 布局下 runtime "
            "与项目无关），忽略: %s",
            manifest_path,
        )
    constraint = _runtime_constraint_text(raw_constraint)
    route: dict[str, Any] = {"managed": True}
    if constraint:
        route["runtimeRequirement"] = constraint
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


def resolve_project_maafw_requirement(project_path: Path) -> str | None:
    """普通项目（非 Managed）会用到的 MaaFW requirement。

    与 ``prepare_runner_environment`` 内的解析顺序一致：项目自带原生库的实测
    版本优先于 requirements.txt 的声明（实测 46 个发行包里有 3 个声明是陈旧的）。

    供运行前自检复用——它只需要知道「这个项目会用哪个 runtime」，不需要真的去
    准备环境，因此不联网、不建 venv。
    """

    project = Path(project_path)
    requirement = _bundled_project_maafw_requirement(
        project
    ) or _declared_project_maafw_requirement(project)
    if requirement is None:
        return None
    return _normalize_maafw_requirement(requirement, allow_unconstrained=True)


def pin_agent_maafw_requirement(
    project_path: Path,
    packages: Sequence[str],
) -> list[str]:
    """把 agent 依赖清单里的 maafw 钉成与 runner 加载的原生库同一个版本。

    MaaFW 的 AgentServer（跑在 agent 那一侧）与 AgentClient（跑在 runner 这一侧）
    之间有协议版本号 ``kProtocolVersion``，跨版本会直接拒绝握手，而在我们这边只
    表现为连不上。runner 加载的是项目自带的那份原生库（见
    ``project_maafw_runtime_path``），所以 agent venv 里的 binding 必须跟它一致。

    照抄 ``requirements.txt`` 做不到这件事：实测 46 个发行包里有 4 个写的是无版本
    约束的 ``maafw`` / ``MaaFw``，pip 会拉到当时的最新版。maafw 5.13.0 于
    2026-09-07 发布并把协议号从 7 抬到 8，于是这些项目的 agent venv 一旦在那之后
    重建，就会出现 AgentClient v5.12.3 对 AgentServer v5.13.0，每次运行都连不上。

    解析口径与运行池 venv 完全一致（``resolve_project_maafw_requirement``：自带
    原生库的实测版本优先于声明），两侧因此不会再岔开。

    **只替换已有的声明，不凭空追加**：没在 requirements.txt 里声明 maafw 的项目，
    agent 多半不是 Python 的或不用 binding，给它装一个用不上的包没有意义。
    """

    requirement = resolve_project_maafw_requirement(Path(project_path))
    if requirement is None:
        return list(packages)

    pinned: list[str] = []
    replaced = False
    for package in packages:
        declaration = str(package).split(";", 1)[0].strip()
        if requirement_distribution_name(declaration) != "maafw":
            pinned.append(package)
            continue
        if replaced:
            # 同名声明只保留一条，重复的丢掉；pip 拿到两条互斥的约束会直接失败。
            continue
        pinned.append(requirement)
        replaced = True
    return pinned


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


def requirement_distribution_name(requirement: str) -> str | None:
    match = REQUIREMENT_NAME_RE.match(requirement)
    if match is None:
        return None
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def build_runner_environment(
    venv_path: str | Path,
    *,
    import_paths: Iterable[str | Path] = (),
    pool_root: str | Path | None = None,
    binding_dir: str | Path | None = None,
    native_dir: str | Path | None = None,
    project_runtime_path: str | Path | None = None,
) -> dict[str, str]:
    """worker 子进程的环境变量。

    ``binding_dir`` 排在 ``PYTHONPATH`` 最前：base venv 里没有 ``maa``，``SOURCE_ROOT``
    与基解释器目录也没有，所以 ``import maa`` 落到它。``MAAFW_BINARY_PATH`` 指到副本
    自带的 ``maafw/`` 或池里的 native 目录（``maa/__init__.py`` 读它）；worker 与 binding
    自检共用这几个键的拼法（``binding_environment_variables``），自检过了 worker 就一定
    能起。
    """

    # 宿主的 PYTHONPATH / PYTHONWARNINGS 等一律不进 worker：worker 能 import 什么只由
    # import_paths 决定（剔除名单与运行池 / agent 共用，见 host_environment 模块）。
    env = strip_host_python_environment()

    venv = Path(venv_path).resolve()
    scripts_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    resolved_import_paths = [
        str(Path(path).resolve()) for path in import_paths if Path(path).exists()
    ]
    if binding_dir is not None:
        resolved_import_paths.insert(0, str(Path(binding_dir).resolve()))

    env["VIRTUAL_ENV"] = str(venv)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # `python -m` 会把 cwd 插到 sys.path[0]，排在 PYTHONPATH 之前。受 Runtime 监督时
    # cwd 是 <app-root>，那里还躺着安装包自带的旧 app/ 包（只随整包安装更新），会把
    # PYTHONPATH 里的源码根整个盖掉，worker 于是跑上一个版本的引擎代码。这里禁掉 cwd
    # 前置，让 import_paths 说了算；worker 的 cwd 仍是 <app-root>，因为运行池、更新
    # 缓存等用户数据都按它解析。运行池的解释器约束是 3.12/3.13，该变量必然生效。
    env["PYTHONSAFEPATH"] = "1"
    env["PATH"] = f"{scripts_dir}{os.pathsep}{env.get('PATH', '')}"
    if resolved_import_paths:
        env["PYTHONPATH"] = os.pathsep.join(resolved_import_paths)
    else:
        env.pop("PYTHONPATH", None)
    if binding_dir is not None and pool_root is not None:
        env.update(
            binding_environment_variables(
                Path(pool_root),
                binding_dir=Path(binding_dir),
                native_dir=Path(native_dir) if native_dir is not None else None,
                project_runtime_path=(
                    Path(project_runtime_path)
                    if project_runtime_path is not None
                    else None
                ),
            )
        )
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


def _normalized_sys_path(path: str) -> str:
    try:
        return str(Path(path).resolve())
    except (OSError, RuntimeError):
        return path


def _send_log(send_log: Callable[[str], None] | None, message: str) -> None:
    if send_log is not None:
        send_log(message)
