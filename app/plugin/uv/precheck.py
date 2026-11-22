"""宿主、全部保留插件和拟新增插件的联合依赖解析。"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import platform
import site
import sys
import tempfile
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from zipfile import ZIP_DEFLATED, ZipFile

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

from app.utils import ProcessRunner, get_logger
from app.utils.common.tools import to_pep440

from ..errors import PluginError, PluginPrecheckError, VersionConflict
from ..types import CORE_DISTRIBUTION_NAME, CORE_PLUGIN_NAME, PluginCodeDrift
from .ops import candidates, ensure, mark_ok

logger = get_logger("插件依赖预检")


@dataclass(frozen=True)
class CoreCompat:
    ok: bool
    required: str = ""
    detail: str = ""


def host_dependencies() -> list[str]:
    """从宿主项目元数据读取运行依赖，作为当前 core 兼容性预检的依赖基线。"""
    from app.core import Config

    with (Config.source_path / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)["project"]["dependencies"]


def host_constraints() -> list[str]:
    """沿主程序运行依赖收集实际安装版本，插件不得覆盖这部分环境。"""
    installed = {
        canonicalize_name(dist.name): dist
        for dist in importlib_metadata.distributions(path=site.getsitepackages())
    }
    pending = [Requirement(dep) for dep in host_dependencies()]
    visited: set[tuple[str, str]] = set()
    versions: dict[str, str] = {}
    while pending:
        requirement = pending.pop()
        if requirement.marker and not requirement.marker.evaluate():
            continue
        name = canonicalize_name(requirement.name)
        if name not in installed:
            raise PluginError(f"主程序运行依赖缺失：{name}")
        dist = installed[name]
        if not requirement.specifier.contains(dist.version, prereleases=True):
            raise PluginError(f"主程序运行依赖不满足声明：{requirement}")
        versions[name] = dist.version
        for extra in {"", *requirement.extras}:
            if (name, extra) in visited:
                continue
            visited.add((name, extra))
            for raw in dist.requires or []:
                child = Requirement(raw)
                if child.marker and not child.marker.evaluate({"extra": extra}):
                    continue
                child.marker = None
                pending.append(child)
    return [f"{name}=={version}" for name, version in sorted(versions.items())]


async def locked_dependencies(
    *, project: str, lockfile: str, python_version: str
) -> list[str]:
    """导出目标主程序的锁定运行依赖，并按目标 Python 和当前平台筛选条件。"""
    declaration = tomllib.loads(project)["project"]
    lock = tomllib.loads(lockfile)
    if not SpecifierSet(lock["requires-python"]).contains(python_version):
        raise ValueError("目标 Python 版本不满足锁文件声明")
    root_package = next(
        (
            item
            for item in lock["package"]
            if canonicalize_name(item["name"]) == canonicalize_name(declaration["name"])
        ),
        None,
    )
    if root_package is None or root_package["version"] != declaration["version"]:
        raise ValueError("目标锁文件与主程序版本不一致")
    declared = [Requirement(raw) for raw in declaration["dependencies"]]
    locked = []
    for item in root_package["metadata"]["requires-dist"]:
        extras = f"[{','.join(item['extras'])}]" if item.get("extras") else ""
        requirement = f"{item['name']}{extras}{item.get('specifier', '')}"
        if item.get("marker"):
            requirement += f"; {item['marker']}"
        locked.append(Requirement(requirement))
    for requirements in (declared, locked):
        for requirement in requirements:
            requirement.name = canonicalize_name(requirement.name)
    if {str(item) for item in declared} != {str(item) for item in locked}:
        raise ValueError("目标锁文件与主程序依赖声明不一致")
    with tempfile.TemporaryDirectory(prefix="auto-mas-host-lock-") as temporary:
        root = Path(temporary)
        (root / "pyproject.toml").write_text(project, encoding="utf-8")
        (root / "uv.lock").write_text(lockfile, encoding="utf-8")
        result = await ProcessRunner.run_process(
            ensure(),
            "export",
            "--project",
            str(root),
            "--frozen",
            "--no-default-groups",
            "--no-emit-workspace",
            "--no-hashes",
            "--no-header",
            "--no-annotate",
            "--offline",
            timeout=60,
            kill_tree_on_cancel=True,
        )
        if result.returncode != 0:
            logger.warning("目标锁定依赖导出失败：{}", str(result.stderr)[-2000:])
            raise PluginError(
                "无法读取目标主程序锁定依赖", payload={"detail": result.stderr}
            )
        environment = cast(dict[str, str], default_environment())
        environment.update(
            python_full_version=python_version,
            python_version=".".join(python_version.split(".")[:2]),
            implementation_version=python_version,
        )
        dependencies = []
        for line in str(result.stdout).splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            requirement = Requirement(line)
            if requirement.marker and not requirement.marker.evaluate(environment):
                continue
            requirement.marker = None
            dependencies.append(str(requirement))
        return dependencies


def plugin_targets(
    plugins: Iterable,
    *,
    replacing: str | None = None,
    upgrade: bool = False,
    installed_path: Path | None = None,
) -> list[str]:
    """禁用插件仍保留安装，和启用插件同样参与共享依赖解析。"""
    targets = []
    for record in plugins:
        if record.info.plugin_name == CORE_PLUGIN_NAME:
            continue
        package = record.info.package_name
        if (
            package
            and replacing
            and canonicalize_name(package) == canonicalize_name(replacing)
        ):
            continue
        if record.info.source == "local":
            # 源码移除后只保留展示记录，不能将未发布的本地工程转成远端发行包。
            if record._project_dir is None:
                if record.info.code_drift == PluginCodeDrift.PACKAGE_REMOVED:
                    continue
                raise PluginError(f"插件缺少本地源码：{record.info.plugin_name}")
            path = record._project_dir
            if not (path / "pyproject.toml").is_file():
                path = path.parent
            if not (path / "pyproject.toml").is_file():
                raise PluginError(f"插件缺少发行元数据：{record.info.plugin_name}")
            project = tomllib.loads(
                (path / "pyproject.toml").read_text(encoding="utf-8")
            )["project"]
            requirements = project.get("dependencies", [])
            if not any(
                canonicalize_name(Requirement(dep).name)
                == canonicalize_name(CORE_DISTRIBUTION_NAME)
                for dep in requirements
            ):
                raise PluginError(f"插件未声明 SDK 依赖：{record.info.plugin_name}")
            targets.append(str(path.resolve()))
        elif package:
            # 导入失败不代表已经卸载，以发行元数据确认共享环境中实际保留的版本。
            try:
                if installed_path is None:
                    version = importlib_metadata.version(package)
                else:
                    dist = next(
                        (
                            dist
                            for dist in importlib_metadata.distributions(
                                path=[str(installed_path), *site.getsitepackages()]
                            )
                            if canonicalize_name(dist.name)
                            == canonicalize_name(package)
                        ),
                        None,
                    )
                    if dist is None:
                        raise importlib_metadata.PackageNotFoundError(package)
                    version = dist.version
            except importlib_metadata.PackageNotFoundError as error:
                if record.info.code_drift == PluginCodeDrift.PACKAGE_REMOVED:
                    continue
                raise PluginError(f"插件缺少已安装的发行元数据：{package}") from error
            targets.append(
                f"{package}>={version}" if upgrade else f"{package}=={version}"
            )
        elif record.info.code_drift != PluginCodeDrift.PACKAGE_REMOVED:
            raise PluginError(f"插件无法确定保留的发行版本：{record.info.plugin_name}")
    # 本地源码库以目录参与求解：依赖它的插件由它满足，它自己的包不装进共享环境。
    from app.plugin.runtime.discover import local_libraries

    for library in local_libraries():
        if str(library) not in targets:
            targets.append(str(library))
    return targets


def _write_core_metadata(
    directory: Path, version: str, dependencies: Sequence[str]
) -> Path:
    """生成仅携带目标 core 版本和依赖声明的临时 wheel，供解析器联合求解而不安装实际程序。"""
    safe = CORE_DISTRIBUTION_NAME.replace("-", "_")
    info = f"{safe}-{version}.dist-info"
    path = directory / f"{safe}-{version}-py3-none-any.whl"
    with ZipFile(path, "w", ZIP_DEFLATED) as wheel:
        wheel.writestr(
            f"{info}/METADATA",
            "\n".join(
                [
                    "Metadata-Version: 2.1",
                    f"Name: {CORE_DISTRIBUTION_NAME}",
                    f"Version: {version}",
                    "Summary: Bundled AUTO-MAS SDK dependency contract",
                    *(f"Requires-Dist: {Requirement(dep)}" for dep in dependencies),
                    "",
                    "",
                ]
            ),
        )
        wheel.writestr(
            f"{info}/WHEEL",
            "Wheel-Version: 1.0\nGenerator: auto-mas\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        wheel.writestr(f"{info}/RECORD", "")
    return path


async def resolve_environment(
    *,
    targets: Sequence[str],
    core_version: str,
    dependencies: Sequence[str],
    destination: Path | None = None,
    constraints: Sequence[str] = (),
    python_version: str | None = None,
) -> CoreCompat:
    """联合求解后仅安装插件侧发行包，固定并排除主程序已有依赖与自带 SDK。"""
    version = to_pep440(core_version)
    with tempfile.TemporaryDirectory(prefix="auto-mas-resolve-") as temporary:
        root = Path(temporary)
        links = root / "links"
        links.mkdir()
        sdk = _write_core_metadata(links, version, dependencies)
        requirements = root / "requirements.in"
        requirements.write_text(
            "\n".join(
                [f"{CORE_DISTRIBUTION_NAME} @ {sdk.as_uri()}", *constraints, *targets]
            ),
            encoding="utf-8",
        )
        resolved = root / "requirements.txt"
        excluded = [
            CORE_DISTRIBUTION_NAME,
            *(Requirement(dep).name for dep in constraints),
        ]
        for target in targets:
            project = Path(target) / "pyproject.toml"
            if project.is_file():
                excluded.append(
                    tomllib.loads(project.read_text(encoding="utf-8"))["project"][
                        "name"
                    ]
                )
        incomplete = False
        architecture = {"amd64": "x86_64", "arm64": "aarch64", "i386": "i686"}.get(
            platform.machine().lower(), platform.machine().lower()
        )
        python_platform = (
            architecture
            + {
                "win32": "-pc-windows-msvc",
                "darwin": "-apple-darwin",
                "linux": "-unknown-linux-gnu",
            }[sys.platform]
        )
        for mirror in candidates():
            args = [
                ensure(),
                "pip",
                "compile",
                str(requirements),
                "--python",
                sys.executable,
                "--python-version",
                python_version or platform.python_version(),
                "--python-platform",
                python_platform,
                "--output-file",
                str(resolved),
                "--no-header",
                "--no-annotate",
                "--find-links",
                str(links),
                "--index-url",
                mirror,
                "--prerelease",
                "allow",
            ]
            for package in excluded:
                args.extend(["--no-emit-package", package])
            result = await ProcessRunner.run_process(
                *args, timeout=600, kill_tree_on_cancel=True
            )
            if result.returncode != 0:
                # 镜像未收录目标版本时继续尝试，不能提前判定永久冲突。
                detail = str(result.stderr or result.stdout or "")
                logger.warning("插件依赖解析失败（{}）：{}", mirror, detail[-2000:])
                # uv 的无解诊断与执行错误分开；任一来源未完成时不能确认全体来源均无解。
                incomplete |= (
                    result.returncode != 1 or "No solution found" not in detail
                )
                continue
            if destination is None:
                await mark_ok(mirror)
                return CoreCompat(ok=True)

            destination.mkdir(parents=True, exist_ok=True)
            result = await ProcessRunner.run_process(
                ensure(),
                "pip",
                "install",
                "--python",
                sys.executable,
                "--target",
                str(destination),
                "--no-deps",
                "--requirements",
                str(resolved),
                "--index-url",
                mirror,
                "--prerelease",
                "allow",
                timeout=600,
                kill_tree_on_cancel=True,
            )
            if result.returncode != 0:
                incomplete = True
                logger.warning(
                    "插件依赖安装失败（{}）：{}",
                    mirror,
                    str(result.stderr or result.stdout or "")[-2000:],
                )
                continue
            installed = {
                canonicalize_name(dist.name): dist.version
                for dist in importlib_metadata.distributions(path=[str(destination)])
            }
            for line in resolved.read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.startswith("#"):
                    continue
                requirement = Requirement(line)
                if requirement.marker and not requirement.marker.evaluate():
                    continue
                actual = installed.get(canonicalize_name(requirement.name))
                if actual is None or not requirement.specifier.contains(
                    actual, prereleases=True
                ):
                    raise PluginError(f"插件安装结果与求解版本不一致：{requirement}")
            await mark_ok(mirror)
            return CoreCompat(ok=True)
        if incomplete:
            raise PluginPrecheckError("兼容性检查未完成，请检查网络或稍后重试")
        return CoreCompat(
            ok=False,
            required="shared-environment",
            detail="目标主程序与插件的依赖无法同时满足，请调整插件版本后重试",
        )


async def check_core(
    *,
    package=None,
    version=None,
    path=None,
    core_version: str,
    dependencies: Sequence[str] | None = None,
) -> CoreCompat:
    """将指定包版本或本地源码与目标 core 依赖一起解析，返回安装或升级的兼容性结论。"""
    target = str(path.resolve()) if path is not None else f"{package}=={version}"
    return await resolve_environment(
        targets=[target],
        core_version=core_version,
        dependencies=dependencies if dependencies is not None else host_dependencies(),
        constraints=host_constraints(),
    )


async def precheck_core_bump(
    new_version: str,
    *,
    plugins: Iterable,
    dependencies: Sequence[str],
    python_version: str,
) -> list[VersionConflict]:
    """联合解析目标 core 与插件，只将确定无解转换为冲突列表，检查故障交由调用方报告。"""
    targets = plugin_targets(plugins, upgrade=True)
    result = await resolve_environment(
        targets=targets,
        core_version=new_version,
        dependencies=dependencies,
        constraints=dependencies,
        python_version=python_version,
    )
    if result.ok:
        return []
    return [
        VersionConflict(
            "", CORE_DISTRIBUTION_NAME, result.required, new_version, result.detail
        )
    ]
