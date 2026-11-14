"""宿主、全部保留插件和拟新增插件的联合依赖解析。"""

from __future__ import annotations

import sys
import tempfile
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from app.utils import ProcessRunner
from app.utils.common.tools import to_pep440

from ..errors import PluginError, VersionConflict
from ..types import CORE_DISTRIBUTION_NAME, CORE_PLUGIN_NAME
from .ops import candidates, ensure, mark_ok


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


def plugin_targets(plugins: Iterable, *, replacing: str | None = None) -> list[str]:
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
        if record.info.source == "local" and record._project_dir is not None:
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
        elif package and record.info.version:
            targets.append(f"{package}=={record.info.version}")
        elif record.info.code_drift.value != "package_removed":
            raise PluginError(f"插件无法确定保留的发行版本：{record.info.plugin_name}")
    return targets


def _write_core_metadata(
    directory: Path, version: str, dependencies: Sequence[str]
) -> None:
    """生成仅携带目标 core 版本和依赖声明的临时 wheel，供解析器联合求解而不安装实际程序。"""
    safe = CORE_DISTRIBUTION_NAME.replace("-", "_")
    info = f"{safe}-{version}.dist-info"
    with ZipFile(
        directory / f"{safe}-{version}-py3-none-any.whl", "w", ZIP_DEFLATED
    ) as wheel:
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


async def resolve_environment(
    *,
    targets: Sequence[str],
    core_version: str,
    dependencies: Sequence[str],
    destination: Path | None = None,
) -> CoreCompat:
    """预检使用空目标，实际安装复用同一组联合输入；不覆盖 SDK 源码。"""
    version = to_pep440(core_version)
    with tempfile.TemporaryDirectory(prefix="auto-mas-resolve-") as temporary:
        root = Path(temporary)
        links = root / "links"
        links.mkdir()
        _write_core_metadata(links, version, dependencies)
        target = destination or root / "target"
        target.mkdir(parents=True, exist_ok=True)
        last_error = ""
        for mirror in candidates():
            args = [
                ensure(),
                "pip",
                "install",
                f"{CORE_DISTRIBUTION_NAME}=={version}",
                *targets,
                "--python",
                sys.executable,
                "--target",
                str(target),
                "--find-links",
                str(links),
                "--index-url",
                mirror,
                "--prerelease",
                "allow",
            ]
            if destination is None:
                args.append("--dry-run")
            result = await ProcessRunner.run_process(*args, timeout=600)
            if result.returncode == 0:
                await mark_ok(mirror)
                return CoreCompat(ok=True)
            last_error = str(result.stderr or result.stdout or "")[-2000:]
            # 依赖无解不会因换镜像而消失；网络与索引暂不可用才切换。
            if "No solution found" in last_error:
                break
        return CoreCompat(ok=False, required="shared-environment", detail=last_error)


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
    )


async def precheck_core_bump(
    new_version: str, *, plugins: Iterable, dependencies: Sequence[str]
) -> list[VersionConflict]:
    """联合解析目标 core 与当前插件依赖，将解析失败或版本约束冲突转换为前端可展示的冲突列表。"""
    try:
        targets = plugin_targets(plugins)
        result = await resolve_environment(
            targets=targets, core_version=new_version, dependencies=dependencies
        )
    except (PluginError, ValueError, OSError) as error:
        return [
            VersionConflict(
                "",
                CORE_DISTRIBUTION_NAME,
                "shared-environment",
                new_version,
                str(error),
            )
        ]
    if result.ok:
        return []
    return [
        VersionConflict(
            "", CORE_DISTRIBUTION_NAME, result.required, new_version, result.detail
        )
    ]
