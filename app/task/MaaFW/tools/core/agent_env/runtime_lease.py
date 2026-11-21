"""借还 worker 的运行环境：运行池里唯一的 base venv + 该项目版本的 binding（+ 需要时的 native）。

运行池（``config/maafw_runtime_pool``）归 agent 环境这一块管。运行（``runner/environment.py``）
起 worker 前只经这里两个函数拿环境、还环境：:func:`borrow_runtime_environment` 返回普通数据
（解释器路径、base venv、binding 版本与目录、要交给 worker 的环境变量、租约标识），
:func:`return_runtime_environment` 按这些标识还租约、放掉 binding 的进程内引用。worker 的
``PYTHONPATH`` 等怎么拼是运行那边的事（``build_runner_environment``）。

:func:`describe_runner_runtime_selection` 是同一套推导的「只算不建」版本：宿主侧回收对账、
运行前自检用它算出项目会落到哪个 base 与哪个 binding。
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from packaging.requirements import InvalidRequirement, Requirement
from packaging.version import InvalidVersion, Version

from ..native.architecture import supported_architecture_target
from ..native.project_runtime import project_maafw_runtime_path
from ..native.requirement import (
    bundled_project_maafw_requirement,
    declared_project_maafw_requirement,
)
from ..native.versions import (
    MaaFWBindingError,
    exact_version_of,
    normalize_maafw_requirement,
    requirement_distribution_name,
)
from ..runtime_pool import (
    ExtraPackagesInstaller,
    MaaFWRuntimePool,
    MaaFWRuntimePoolBusyError,
    RuntimeInstaller,
    build_runtime_id,
    install_extra_packages,
    install_python_runtime,
)
from ..runtime_pool.binding import (
    BindingInfo,
    binding_environment_variables,
    binding_index_candidates,
    ensure_binding,
    mask_url_credentials,
    release_binding,
    resolve_binding_version,
    retain_binding,
    retained_versions,
    select_local_version,
)
from ..runtime_pool.host_environment import current_subprocess_proxy
from ..runtime_pool.installer import (
    MaaFWRuntimeInstallCancelled,
    host_bootstrap_python_request,
    install_cancel_scope,
    is_package_index_offline,
    raise_if_install_cancelled,
)
from .pip_constraint import AGENT_PIP_CONSTRAINT_DIR_ENV, default_agent_constraint_dir

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
    # runtime_pool 用 packaging。worker 的 PYTHONPATH 只有 binding 与源码根、
    # 不带宿主的依赖（见 runner.environment.build_runner_environment），它们必须装进 runner venv。
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

EnvironmentProgressCallback = Callable[[dict[str, Any]], None]

logger = logging.getLogger("automas.maafw.agent_env.runtime_lease")


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
class MaaFWRuntimeLease:
    """借到的运行环境（普通数据）。还的时候按 ``runtime_pool_root`` / ``runtime_id`` /
    ``lease_id`` / ``binding_version`` 还（:func:`return_runtime_environment`）。"""

    python_executable: Path
    venv_path: Path
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
    #: 交给 worker 的环境变量：binding 相关的键（``binding_environment_variables``）与 agent
    #: 运行期 pip 约束文件的目录（``AGENT_PIP_CONSTRAINT_DIR_ENV``）。
    worker_env: dict[str, str] = field(default_factory=dict)


def _raise_if_prepare_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise MaaFWRuntimeInstallCancelled("MaaFW Runner 环境准备已取消")


def borrow_runtime_environment(
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
    send_log: Callable[[str], None] | None = None,
    progress: EnvironmentProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> MaaFWRuntimeLease:
    """备好一个项目的运行环境并借出：唯一的 base venv + 该项目版本的 binding（+ 需要时的 native）。

    ``managed_env_root`` remains accepted as the legacy pool-root argument.
    base venv 的身份只有常量包集合 + 宿主 Python 身份，所有项目共用；项目之间的差别
    只剩「用哪个版本的 binding」和「DLL 来自副本还是池」，都在返回值里。
    ``extras_installer`` 只给测试注入：正式路径追加装包走 ``install_extra_packages``。

    ``cancel_event`` 置位后，正在跑的 uv/pip 安装子进程与 binding 下载会被终止，本函数
    以 ``MaaFWRuntimeInstallCancelled`` 结束且不会持有租约；半成品留在 staging 目录里
    被池删掉，manifest 只在安装完整成功后才写入。

    返回的租约持有池里 base 的执行租约与 binding 的进程内引用，用完交给
    :func:`return_runtime_environment`。
    """

    # 不是 x64 就别建 venv、下 binding：后面每一步都只按 x64 选包。
    supported_architecture_target()
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
        worker_env = binding_environment_variables(
            pool.root,
            binding_dir=binding.directory,
            native_dir=binding.native_directory,
            project_runtime_path=project_runtime_path,
        )
        # worker 起 agent 时把 maafw 的 pip 约束文件写在这里（AUTO-MAS 自己的数据目录，
        # 不进项目视图），见 runner._inject_agent_pip_constraint。
        worker_env[AGENT_PIP_CONSTRAINT_DIR_ENV] = str(default_agent_constraint_dir())
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
        return MaaFWRuntimeLease(
            python_executable=python_executable,
            venv_path=venv_path,
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
            worker_env=worker_env,
        )
    except Exception:
        release_binding(pool.root, binding.version)
        pool.release_lease(resolved_runtime_id, lease_id)
        raise


def return_runtime_environment(
    *,
    runtime_pool_root: str | Path | None,
    runtime_id: str | None,
    lease_id: str | None,
    binding_version: str | None,
    runtime_pool: MaaFWRuntimePool | None = None,
) -> dict[str, Any] | None:
    """还掉 :func:`borrow_runtime_environment` 借出的租约，放掉 binding 的进程内引用。"""

    runtime_id = str(runtime_id or "").strip()
    lease_id = str(lease_id or "").strip()
    pool = runtime_pool
    if pool is None and runtime_pool_root is not None:
        pool = MaaFWRuntimePool(Path(runtime_pool_root))
    if pool is not None and binding_version:
        release_binding(pool.root, binding_version)
    if not runtime_id or not lease_id or pool is None:
        return None
    return pool.release_lease(runtime_id, lease_id)


def return_runtime_lease(
    lease: MaaFWRuntimeLease,
    *,
    runtime_pool: MaaFWRuntimePool | None = None,
) -> dict[str, Any] | None:
    """按租约对象还（:func:`return_runtime_environment` 的便捷写法）。"""

    return return_runtime_environment(
        runtime_pool_root=lease.runtime_pool_root,
        runtime_id=lease.runtime_id,
        lease_id=lease.lease_id,
        binding_version=lease.binding_version,
        runtime_pool=runtime_pool,
    )


def _describe_binding_source(binding: BindingInfo) -> str:
    source = binding.source
    if source.startswith("pypi:"):
        # 已装好的 binding 清单里可能还记着带 user:pw@ 的索引地址（打码之前装的）
        return f"PyPI/镜像 {mask_url_credentials(source[len('pypi:') :])}"
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


def _select_project_maafw_requirement(
    project: Path,
    *,
    preselected: str | None,
    managed_project: bool,
) -> str:
    """项目会用的 maafw requirement（已规范化）。

    ``borrow_runtime_environment`` 与 ``describe_runner_runtime_selection`` 共用这
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
        selected_requirement = bundled_project_maafw_requirement(project)
    if selected_requirement is None:
        selected_requirement = declared_project_maafw_requirement(project)
    if selected_requirement is None and managed_project:
        raise RuntimeError(
            "MaaFW runtime 未绑定且项目未声明 runtime constraint；"
            f"请在 {PROJECT_RUNTIME_MANIFEST_NAME} 中设置 runtime.constraint"
        )
    if selected_requirement is None:
        # Legacy projects keep the historical unpinned default. Managed
        # project-store entries must always provide a constraint or binding.
        selected_requirement = "maafw"
    return normalize_maafw_requirement(
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
    """不联网、不建 venv：算出 ``borrow_runtime_environment`` 对这个项目会选中的 base 与 binding。

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


def _send_log(send_log: Callable[[str], None] | None, message: str) -> None:
    if send_log is not None:
        send_log(message)


__all__ = [
    "BASE_RUNTIME_PACKAGES",
    "DEFAULT_RUNTIME_LEASE_TTL_SECONDS",
    "PROJECT_RUNTIME_MANIFEST_NAME",
    "RUNNER_DEFAULT_PACKAGES",
    "EnvironmentProgressCallback",
    "MaaFWRuntimeLease",
    "RunnerRuntimeSelection",
    "borrow_runtime_environment",
    "describe_runner_runtime_selection",
    "return_runtime_environment",
    "return_runtime_lease",
]
