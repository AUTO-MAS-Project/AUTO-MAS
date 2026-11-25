"""uv 工具链：查找、镜像、装卸包。

uv 安装由 Runtime 负责；后端只查找并用 ``ProcessRunner`` 调用。
成功镜像持久化到 ``Config.setting.uv.preferred_mirror``（UI 隐藏）。
升版预检见同包 ``precheck``。
"""

from __future__ import annotations

import importlib
import importlib.metadata as importlib_metadata
import json
import os
import platform
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from uuid import UUID, uuid4

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from app.utils import ProcessRunner, get_logger

from ..errors import PluginError, PluginPrecheckError

logger = get_logger("插件 uv")

# ── PyPI simple 镜像（顺序即优先级）──
_MIRRORS: list[str] = [
    "https://mirrors.aliyun.com/pypi/simple/",
    "https://pypi.tuna.tsinghua.edu.cn/simple/",
    "https://pypi.mirrors.ustc.edu.cn/simple/",
    "https://pypi.org/simple/",
]


def ensure() -> str:
    """返回可用的 uv 路径；找不到则报错（不下载、不安装）。

    查找顺序：``AUTO_MAS_UV_EXE`` → ``runtime/tools/uv/<ver>/uv[.exe]`` → PATH。
    """
    env = (os.environ.get("AUTO_MAS_UV_EXE") or "").strip()
    if env and Path(env).is_file():
        return env

    tools = Path.cwd() / "runtime" / "tools" / "uv"
    if tools.is_dir():
        name = "uv.exe" if sys.platform == "win32" else "uv"
        found: list[tuple[Version, Path]] = []
        for child in tools.iterdir():
            if not child.is_dir():
                continue
            exe = child / name
            if exe.is_file():
                try:
                    version = Version(child.name)
                except InvalidVersion:
                    continue
                found.append((version, exe))
        if found:
            path = str(max(found, key=lambda item: item[0])[1])
            os.environ["AUTO_MAS_UV_EXE"] = path
            return path

    uv_path = shutil.which("uv")
    if not uv_path:
        raise PluginError(
            "未找到 uv：请通过 AUTO-MAS-Runtime 安装，或在系统 PATH 中提供 uv"
        )
    os.environ["AUTO_MAS_UV_EXE"] = uv_path
    return uv_path


def site_dir(*, activate: bool = True) -> Path:
    """定位插件安装目录；启动升级前仅访问文件，校验完成后才加入导入路径。"""
    from app.core.config import Config

    path = Config.plugins_path / "pypi" / "site-packages"
    previous = path.with_suffix(".previous")
    if not path.exists() and previous.exists():
        previous.rename(path)
    path.mkdir(parents=True, exist_ok=True)
    text = str(path.resolve())
    if activate and text not in sys.path:
        sys.path.append(text)
    return path


def candidates() -> list[str]:
    """当前候选 ``--index-url``；已验证成功的镜像置顶且无重复。"""
    from app.core.config import Config

    preferred = Config.setting.uv.preferred_mirror or _MIRRORS[0]
    return list(dict.fromkeys([preferred, *_MIRRORS]))


async def mark_ok(mirror_url: str) -> None:
    """某镜像成功后置顶，并持久化到 ``Config.setting.uv.preferred_mirror``。"""
    needle = mirror_url.rstrip("/")
    if not any(url.rstrip("/") == needle for url in _MIRRORS):
        return

    from app.core.config import Config

    current = (Config.setting.uv.preferred_mirror or _MIRRORS[0]).rstrip("/")
    if current == needle:
        return

    Config.setting.uv.preferred_mirror = mirror_url
    await Config.setting.commit()


def _pinned_versions(pinned: list[str]) -> dict[str, str]:
    """从保留目标里取钉在 ``==版本`` 的已装插件发行包；本地工程目录不在其列。"""
    versions = {}
    for item in pinned:
        if Path(item).is_dir():
            continue
        requirement = Requirement(item)
        specifiers = list(requirement.specifier)
        if len(specifiers) == 1 and specifiers[0].operator == "==":
            versions[canonicalize_name(requirement.name)] = specifiers[0].version
    return versions


def _installed_requires(package: str, path: Path | None = None) -> set[str]:
    """已装发行包按 Requires-Dist 直接依赖的包名（规范化）；读不到的返回空集。

    给了 ``path`` 时只在该目录里找：启动前插件目录还没进导入路径。
    """
    if path is None:
        try:
            requires = importlib_metadata.distribution(package).requires or []
        except importlib_metadata.PackageNotFoundError:
            return set()
    else:
        found = next(
            (
                dist
                for dist in importlib_metadata.distributions(path=[str(path)])
                if canonicalize_name(dist.name or "") == canonicalize_name(package)
            ),
            None,
        )
        if found is None:
            return set()
        requires = found.requires or []
    names = set()
    for text in requires:
        try:
            requirement = Requirement(text)
        except ValueError:
            continue
        if requirement.marker is not None and not requirement.marker.evaluate(
            {"extra": ""}
        ):
            continue
        names.add(canonicalize_name(requirement.name))
    return names


async def _family_release(
    package_specs: list[str],
    pinned: list[str],
    pins: list[str],
    *,
    installed_path: Path | None = None,
) -> dict[str, str] | None:
    """其余插件全钉住无解时，算出要一起放开的已装插件（包名 → 当前版本）。

    范围：目标单独求解得到的依赖闭包里出现的已装插件，再加上直接依赖了目标或
    已放开包的已装插件，反复到不再增加。别的插件照旧钉住。

    目标单独求解也确定无解、且不涉及主程序钉住的包时返回 None：问题不在别的插件，
    是索引里拿不到能装的目标（连同它的依赖）。
    """
    from app.core import Config
    from app.plugin.runtime.discover import local_libraries

    from .precheck import host_dependencies, resolve_environment

    installed = _pinned_versions(pinned)
    if not installed:
        return {}
    # 只求解不安装；本地源码库照常参与，别的插件不放进来，免得它们的钉子挡住求解。
    alone = await resolve_environment(
        targets=[*package_specs, *(str(library) for library in local_libraries())],
        core_version=Config.VERSION,
        dependencies=host_dependencies(),
        constraints=pins,
        partial=True,
    )
    if not alone.ok:
        if alone.incomplete or alone.host_conflicts:
            return {}
        return None
    targets = {canonicalize_name(Requirement(spec).name) for spec in package_specs}
    released = {name for name in alone.resolved if name in installed}
    frontier = released | targets
    grown = True
    while grown:
        grown = False
        for name in sorted(installed.keys() - released):
            if _installed_requires(name, installed_path) & frontier:
                released.add(name)
                frontier.add(name)
                grown = True
    return {name: installed[name] for name in sorted(released)}


def _release_pins(pinned: list[str], released: dict[str, str]) -> list[str]:
    """把放开的插件从 ``==当前版本`` 改成 ``>=当前版本``（不许降级），其余原样保留。"""
    result = []
    for item in pinned:
        if not Path(item).is_dir():
            name = canonicalize_name(Requirement(item).name)
            if name in released:
                result.append(f"{name}>={released[name]}")
                continue
        result.append(item)
    return result


def _minimum_failure(
    raised: Mapping[str, Version],
    current: Mapping[str, str],
    result,
    unavailable: bool,
) -> str:
    """抬到版本下限没装成时的原因：要的下限、现装版本，以及是索引里拿不到还是解不开。"""
    from .precheck import conflict_summary, incomplete_message

    if result.incomplete:
        return incomplete_message(result)
    wanted = "、".join(
        f"{name}>={minimum}" + (f"（当前 {current[name]}）" if name in current else "")
        for name, minimum in raised.items()
    )
    if unavailable:
        return f"索引里没有可装的 {wanted}"
    summary = conflict_summary(result)
    return f"没能装上 {wanted}" + (f"：涉及 {summary}" if summary else "")


async def install(
    package_spec: str,
    *,
    plugin_name: str,
    meta_id: UUID | None = None,
    dry_run: bool = False,
    libraries: Sequence[str] = (),
    minimum: Version | None = None,
) -> bool:
    """联合安装到候选目录；可热加载时发布文件，否则保留候选并返回需重启。

    ``libraries``：宿主内置托管要的库（需求串），和已装插件一样留在重建后的环境里；
    按需求原样求解，新插件要更高版本时可以一起升。

    ``minimum``：存量配置要求的版本下限（``package_spec`` 已写成 ``>=下限``）；
    装不成时按下限说原因。
    """
    from packaging.requirements import Requirement

    from app.core import Config
    from app.models.schema import PluginInstallation
    from app.plugin.runtime.metadata import validate_install_metadata

    from . import environment
    from .precheck import (
        conflict_summary,
        host_constraints,
        host_dependencies,
        incomplete_message,
        plugin_targets,
        resolve_environment,
    )

    environment.ensure_writable()
    replacing = Requirement(package_spec).name
    pinned = plugin_targets(Config.plugin_registry.values(), replacing=replacing)
    # 宿主内置托管要的库不在注册表里，不带上的话重建环境会把它移走。
    targets = [*pinned, *libraries, package_spec]
    sources = {
        str(project.resolve()): project.read_text(encoding="utf-8")
        for item in targets
        if (project := Path(item) / "pyproject.toml").is_file()
    }
    target = site_dir()
    pins = host_constraints()
    # 为求解放开钉子的已装插件：规范化包名 → 原版本。
    released: dict[str, str] = {}
    # 目标单独求解也无解：索引里拿不到能装的目标。
    unavailable = False
    with tempfile.TemporaryDirectory(
        prefix=".install-", dir=target.parent
    ) as temporary:
        prepared = Path(temporary) / "site-packages"
        result = await resolve_environment(
            targets=targets,
            core_version=Config.VERSION,
            dependencies=host_dependencies(),
            constraints=pins,
            destination=None if dry_run else prepared,
            partial=True,
        )
        if not result.ok:
            # 别的插件全钉住时无解：同族插件之间写了次版本上限，要一起升才解得开。
            family = await _family_release([package_spec], pinned, pins)
            unavailable = family is None
            released = family or {}
            if released:
                logger.info(
                    "安装 {} 时其余插件全部钉住无解，放开同族插件再求解：{}",
                    package_spec,
                    "、".join(
                        f"{name}>={version}" for name, version in released.items()
                    ),
                )
                if prepared.exists():
                    shutil.rmtree(prepared)
                result = await resolve_environment(
                    targets=[
                        *_release_pins(pinned, released),
                        *libraries,
                        package_spec,
                    ],
                    core_version=Config.VERSION,
                    dependencies=host_dependencies(),
                    constraints=pins,
                    destination=None if dry_run else prepared,
                    partial=True,
                )
        if not result.ok:
            if result.incomplete:
                raise PluginPrecheckError(
                    incomplete_message(result),
                    payload={
                        "detail": result.detail,
                        "conflicts": list(result.conflicts),
                    },
                )
            if minimum is not None:
                raise PluginError(
                    _minimum_failure(
                        {canonicalize_name(replacing): minimum},
                        {
                            name: dist.version
                            for name, dist in environment.distributions(target).items()
                        },
                        result,
                        unavailable,
                    ),
                    payload={
                        "detail": result.detail,
                        "conflicts": list(result.conflicts),
                    },
                )
            summary = conflict_summary(result)
            raise PluginError(
                "插件与共享环境的依赖无法共同满足"
                + (f"：涉及 {summary}" if summary else ""),
                payload={"detail": result.detail, "conflicts": list(result.conflicts)},
            )
        if dry_run:
            return False
        if any(
            not Path(path).is_file()
            or Path(path).read_text(encoding="utf-8") != declaration
            for path, declaration in sources.items()
        ):
            raise PluginError("本地插件声明在安装准备期间发生变化，请重新安装")
        installed = environment.distributions(prepared)
        distribution = installed.get(canonicalize_name(replacing))
        if distribution is None:
            raise PluginError("候选环境缺少请求安装的插件")
        version = validate_install_metadata(
            distribution.metadata, package_name=replacing, plugin_name=plugin_name
        )
        environment.preserve_local_packages(target, prepared)
        # 放开钉子后实际换了版本的已装插件；注册表版本由安装后的发现流程统一刷新。
        upgraded = {
            name: (old, installed[name].version)
            for name, old in released.items()
            if name in installed and Version(installed[name].version) != Version(old)
        }
        records = {
            canonicalize_name(record.info.package_name): record
            for record in Config.plugin_registry.values()
            if record.info.package_name
        }
        restart_required = bool(
            environment.changed_loaded_dependencies(prepared, replacing)
        ) or any(
            # 已加载的插件换版只能交给新进程；不能文件已换、进程里还是旧模块。
            records[name]._plugin_cls is not None
            for name in upgraded
            if name in records
        )
        family_note = ""
        if upgraded:
            family_note = "同族插件一起升级：" + "、".join(
                f"{records[name].info.plugin_name if name in records else name}"
                f" {old} → {new}"
                for name, (old, new) in upgraded.items()
            )
            logger.info("安装 {} 时{}", replacing, family_note)
        existing_record = Config.plugin_registry.by_name(plugin_name)
        record = environment.InstallationRecord(
            progress=PluginInstallation(
                installationId=uuid4(),
                metaId=meta_id or uuid4(),
                packageName=replacing,
                pluginName=plugin_name,
                version=version,
                state="waiting_restart" if restart_required else "applying",
                message="插件依赖已准备，需要重启后端完成安装"
                + (f"；{family_note}" if family_note else "")
                if restart_required
                else family_note or None,
            ),
            core_version=Config.VERSION,
            host_constraints=pins,
            baseline={
                name: dist.version
                for name, dist in environment.distributions(target).items()
            },
            healthy_plugins=[
                record.info.plugin_name
                for record in Config.plugin_registry.values()
                if record._plugin_cls is not None
                and record.info.state in {"enabled", "disabled"}
            ],
            local_sources=sources,
            previous_record=existing_record.uid
            if existing_record is not None
            else None,
            co_upgraded={name: new for name, (_, new) in upgraded.items()},
        )
        if restart_required:
            pending = target.with_suffix(".pending")
            if pending.exists():
                shutil.rmtree(pending)
            prepared.rename(pending)
            environment.write_installation(record)
            return True
        environment.write_installation(record)
        try:
            environment.publish_hot(prepared, replacing)
        except BaseException:
            record.progress.state = "failed"
            record.progress.message = "插件文件发布未完成，已保留恢复材料，请重启后端"
            environment.write_installation(record)
            raise
        return False


def _below_minimum(
    records: list, existing: dict[str, str], minimums: Mapping[str, Version]
) -> dict[str, Version]:
    """已装版本低于下限的插件发行包：规范化包名 → 下限；只看给了下限的已装插件。"""
    raised = {}
    for record in records:
        minimum = minimums.get(record.info.plugin_name)
        if (
            minimum is None
            or record.info.source != "installed"
            or not record.info.package_name
        ):
            continue
        name = canonicalize_name(record.info.package_name)
        version = existing.get(name)
        if version is None:
            continue
        try:
            if Version(version) < minimum:
                raised[name] = minimum
        except InvalidVersion:
            continue
    return raised


def _lift_minimums(targets: list[str], raised: Mapping[str, Version]) -> list[str]:
    """把低于下限的插件目标换成 ``>=下限``，其余原样保留。"""
    result = []
    for item in targets:
        if not Path(item).is_dir():
            name = canonicalize_name(Requirement(item).name)
            if name in raised:
                result.append(f"{name}>={raised[name]}")
                continue
        result.append(item)
    return result


async def _solve_minimums(
    targets: list[str],
    raised: Mapping[str, Version],
    pins: list[str],
    prepared: Path,
    installed_path: Path,
    current: Mapping[str, str],
):
    """带上版本下限求解并装进候选目录；解不开或出错时返回 None，由调用方按原样启动。

    先只抬下限、别的插件钉住；无解时照安装时的做法放开同族插件再解一次。
    ``current`` 是插件环境里现装的版本（规范化包名 → 版本），用来说明没装成的原因。
    """
    from app.core import Config

    from .precheck import host_dependencies, resolve_environment

    # 抬下限的目标单独求解也无解：索引里拿不到能装的版本。
    unavailable = False
    logger.info(
        "存量配置要的插件低于版本下限，加载插件前一并升级：{}",
        "、".join(f"{name}>={version}" for name, version in raised.items()),
    )
    try:
        result = await resolve_environment(
            targets=_lift_minimums(targets, raised),
            core_version=Config.VERSION,
            dependencies=host_dependencies(),
            constraints=pins,
            destination=prepared,
            partial=True,
        )
        if not result.ok:
            pinned = [
                item
                for item in targets
                if Path(item).is_dir()
                or canonicalize_name(Requirement(item).name) not in raised
            ]
            family = await _family_release(
                [f"{name}>={version}" for name, version in raised.items()],
                pinned,
                pins,
                installed_path=installed_path,
            )
            unavailable = family is None
            released = family or {}
            if released:
                logger.info(
                    "只抬下限无解，放开同族插件再求解：{}",
                    "、".join(
                        f"{name}>={version}" for name, version in released.items()
                    ),
                )
                if prepared.exists():
                    shutil.rmtree(prepared)
                result = await resolve_environment(
                    targets=_lift_minimums(_release_pins(targets, released), raised),
                    core_version=Config.VERSION,
                    dependencies=host_dependencies(),
                    constraints=pins,
                    destination=prepared,
                    partial=True,
                )
    except Exception as error:  # noqa: BLE001
        # 离线、镜像没同步、装包出错都不能挡启动；没达标的插件这一轮不接手。
        logger.opt(exception=True).warning(
            "启动前没能把插件升到版本下限，先按现有版本启动：{}", error
        )
        return None
    if not result.ok:
        logger.warning(
            "启动前没能把插件升到版本下限，先按现有版本启动：{}",
            _minimum_failure(raised, current, result, unavailable),
        )
        return None
    return result


def _library_targets(
    libraries: Sequence[str], existing: Mapping[str, str]
) -> tuple[list[str], list[str]]:
    """宿主内置托管要的库的求解目标：已装且满足的钉 ``==现版本``，其余照需求原样。

    第二项是还没装上或版本不满足的需求。
    """
    targets, missing = [], []
    for text in libraries:
        requirement = Requirement(text)
        name = canonicalize_name(requirement.name)
        version = existing.get(name)
        if version is not None and requirement.specifier.contains(
            version, prereleases=True
        ):
            targets.append(f"{name}=={version}")
        else:
            targets.append(text)
            missing.append(text)
    return targets, missing


async def _solve_libraries(
    targets: list[str], missing: list[str], pins: list[str], prepared: Path
):
    """带上宿主内置托管要的库求解并装进候选目录；解不开或出错时返回 None。

    库装不上不挡启动：调用方退回不带库的原有流程，用到它的功能运行时再报错。
    """
    from app.core import Config

    from .precheck import conflict_summary, host_dependencies, resolve_environment

    if missing:
        logger.info(
            "宿主内置托管要的库还没装上，一并装进插件环境：{}", "、".join(missing)
        )
    try:
        result = await resolve_environment(
            targets=targets,
            core_version=Config.VERSION,
            dependencies=host_dependencies(),
            constraints=pins,
            destination=prepared,
            partial=True,
        )
    except Exception as error:  # noqa: BLE001
        logger.opt(exception=True).warning(
            "宿主内置托管要的库没装上，先照常启动，联网后重启会再装：{}", error
        )
        return None
    if not result.ok:
        summary = conflict_summary(result)
        logger.warning(
            "宿主内置托管要的库没装上，先照常启动：{}{}",
            result.detail,
            f"（涉及 {summary}）" if summary else "",
        )
        return None
    return result


async def prepare_environment(
    minimums: Mapping[str, Version] | None = None,
    libraries: Sequence[str] = (),
) -> None:
    """首次导入前联合修复插件环境；校验成功后替换目录，不触发禁用或清配置。

    ``minimums``：存量配置要的插件（插件 ID → 版本下限）。已装版本低于下限时，这次
    求解带上下限，整族在任何插件模块导入前换成达标的版本；解不开时只记警告、按现有
    版本继续，没达标的插件由插件管理器这一轮不启用。

    ``libraries``：宿主内置托管要的库（需求串，例如 MaaEnd 用的 MFW 解析库）。它们
    不是插件，只作为求解目标装进同一个插件环境；已装且满足时不触发求解，装不上时
    只记警告、照常启动。
    """
    from app.core import Config
    from app.utils.common.tools import to_pep440

    from ..runtime.metadata import validate_install_metadata
    from ..types import CORE_DISTRIBUTION_NAME, CORE_PLUGIN_NAME
    from . import environment
    from .precheck import (
        conflict_summary,
        host_constraints,
        host_dependencies,
        plugin_targets,
        resolve_environment,
    )

    target = site_dir(activate=False)
    sys.path[:] = [item for item in sys.path if item != str(target.resolve())]
    installation = environment.read_installation()
    if await environment.apply_pending():
        # 候选环境在安装时已带上当时要的库；之后才加的托管要的库，这一轮不重建环境
        # （旧环境要留作回滚），换入确认后的下一次启动补装。
        _, missing = _library_targets(
            libraries,
            {
                name: dist.version
                for name, dist in environment.distributions(target).items()
            },
        )
        if missing:
            logger.warning(
                "换入的插件环境里没有宿主内置托管要的库，下次启动补装：{}",
                "、".join(missing),
            )
        return
    if installation is not None and installation.progress.state != "succeeded":
        from app.plugin.runtime import discover

        # 回滚可能移除了新插件；刷新实际发行状态后才生成保留依赖。
        await discover.refresh(installed_path=target)
    pins = host_constraints()
    records = list(Config.plugin_registry.values())
    targets = plugin_targets(records, installed_path=target)
    existing = {
        name: dist.version for name, dist in environment.distributions(target).items()
    }
    fingerprint = {
        "core": Config.VERSION,
        "python": platform.python_version(),
        "platform": sys.platform,
        "host": pins,
        "plugins": targets,
        "installed": existing,
        "sources": {
            item: (Path(item) / "pyproject.toml").read_text(encoding="utf-8")
            for item in targets
            if (Path(item) / "pyproject.toml").is_file()
        },
    }
    marker = target.parent / "environment.json"
    unchanged = False
    if marker.is_file():
        try:
            unchanged = json.loads(marker.read_text(encoding="utf-8")) == fingerprint
        except ValueError:
            logger.warning("插件环境记录损坏，重新准备依赖")
    previous = target.with_suffix(".previous")
    # 环境没变也要求解：已装版本低于存量配置要的下限，不能被指纹短路。
    raised = _below_minimum(records, existing, minimums or {})
    # 宿主内置托管要的库：已装且满足就钉在现版本，指纹里的已装版本照常管住它。
    pinned_libraries, missing = _library_targets(libraries, existing)
    if unchanged and not raised and not missing:
        if previous.exists():
            shutil.rmtree(previous)
        return

    logger.info("正在检查并准备插件依赖环境，完成后加载插件")
    with tempfile.TemporaryDirectory(
        prefix=".prepare-", dir=target.parent
    ) as temporary:
        prepared = Path(temporary) / "site-packages"
        result = None
        if raised:
            result = await _solve_minimums(
                [*targets, *libraries], raised, pins, prepared, target, existing
            )
            if result is None:
                if prepared.exists():
                    shutil.rmtree(prepared)
                if unchanged and not missing:
                    if previous.exists():
                        shutil.rmtree(previous)
                    return
        if result is None and libraries:
            result = await _solve_libraries(
                [*targets, *pinned_libraries], missing, pins, prepared
            )
            if result is None:
                if prepared.exists():
                    shutil.rmtree(prepared)
                if unchanged:
                    if previous.exists():
                        shutil.rmtree(previous)
                    return
        if result is None:
            result = await resolve_environment(
                targets=targets,
                core_version=Config.VERSION,
                dependencies=host_dependencies(),
                constraints=pins,
                destination=prepared,
            )
        if not result.ok:
            # 保留当前版本无解时，才允许联合升级；禁用包仍参与，不降级、不转远端源码包。
            if prepared.exists():
                shutil.rmtree(prepared)
            result = await resolve_environment(
                targets=plugin_targets(records, upgrade=True, installed_path=target),
                core_version=Config.VERSION,
                dependencies=host_dependencies(),
                constraints=pins,
                destination=prepared,
            )
        if not result.ok:
            summary = conflict_summary(result)
            raise PluginError(
                f"插件自动升级失败：{result.detail}"
                + (f"（涉及 {summary}）" if summary else ""),
                payload={"conflicts": list(result.conflicts)},
            )

        # 源码覆盖只选择当前实现，不能顺带卸载被覆盖的发行包；源码移除后仍可回落。
        environment.preserve_local_packages(target, prepared)

        installed = {
            name: dist
            for dist in importlib_metadata.distributions(path=[str(prepared)])
            if (name := environment.distribution_name(dist)) is not None
        }
        retained = {
            canonicalize_name(Requirement(item).name)
            for item in targets
            if not Path(item).is_dir()
        }
        for record in records:
            if (
                record.info.plugin_name == CORE_PLUGIN_NAME
                or record.info.source == "local"
            ):
                continue
            if canonicalize_name(record.info.package_name) not in retained:
                continue
            dist = installed.get(canonicalize_name(record.info.package_name))
            if dist is None:
                raise PluginError(f"插件升级后缺少发行包：{record.info.package_name}")
            validate_install_metadata(
                dist.metadata,
                package_name=record.info.package_name,
                plugin_name=record.info.plugin_name,
            )
            for raw in dist.requires or []:
                requirement = Requirement(raw)
                if canonicalize_name(requirement.name) == canonicalize_name(
                    CORE_DISTRIBUTION_NAME
                ) and (requirement.marker is None or requirement.marker.evaluate()):
                    if not requirement.specifier.contains(
                        to_pep440(Config.VERSION), prereleases=True
                    ):
                        raise PluginError(
                            f"插件升级后仍不兼容主程序：{record.info.plugin_name}"
                        )
        if previous.exists():
            shutil.rmtree(previous)
        # Distribution 保存暂存路径，改名后不能再从该对象读取元数据。
        fingerprint["installed"] = {
            name: dist.version for name, dist in installed.items()
        }
        # 两次同盘改名之间不 await；若进程中断，下次启动会恢复 previous。
        target.rename(previous)
        try:
            prepared.rename(target)
        except OSError:
            previous.rename(target)
            raise
        importlib.invalidate_caches()
        importlib_metadata.MetadataPathFinder.invalidate_caches()
        fingerprint["plugins"] = plugin_targets(records, installed_path=target)
        pending_marker = marker.with_suffix(".tmp")
        pending_marker.write_text(
            json.dumps(fingerprint, ensure_ascii=False), encoding="utf-8"
        )
        pending_marker.replace(marker)
        shutil.rmtree(previous)
    importlib.invalidate_caches()
    logger.info("插件依赖准备完成，开始加载插件")


async def uninstall(package_name: str) -> None:
    """``uv pip uninstall``（目标目录）。"""
    target = site_dir()
    result = await ProcessRunner.run_process(
        ensure(),
        "pip",
        "uninstall",
        package_name,
        "--python",
        sys.executable,
        "--target",
        str(target),
        timeout=300,
    )
    if result.returncode != 0:
        logger.error(f"uv 卸载失败: {package_name}")
        raise PluginError(
            f"uv 卸载失败: {package_name}",
            payload={
                "stdout": (result.stdout or "")[-2000:],
                "stderr": (result.stderr or "")[-2000:],
            },
        )
    importlib.invalidate_caches()
    importlib_metadata.MetadataPathFinder.invalidate_caches()
    logger.info(f"uv 卸载成功: {package_name}")
