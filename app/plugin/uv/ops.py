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
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from app.utils import ProcessRunner, get_logger

from ..errors import PluginError

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


async def install(package_spec: str, *, dry_run: bool = False) -> None:
    """安装前后使用同一联合解析：宿主、全部保留插件与目标发行包。"""
    from packaging.requirements import Requirement

    from app.core import Config

    from .precheck import (
        host_constraints,
        host_dependencies,
        plugin_targets,
        resolve_environment,
    )

    replacing = Requirement(package_spec).name
    targets = [
        *plugin_targets(Config.plugin_registry.values(), replacing=replacing),
        package_spec,
    ]
    result = await resolve_environment(
        targets=targets,
        core_version=Config.VERSION,
        dependencies=host_dependencies(),
        constraints=host_constraints(),
        destination=None if dry_run else site_dir(),
    )
    if not result.ok:
        raise PluginError(
            "插件与共享环境的依赖无法共同满足", payload={"detail": result.detail}
        )
    if not dry_run:
        importlib.invalidate_caches()
        importlib_metadata.MetadataPathFinder.invalidate_caches()
        (site_dir().parent / "environment.json").unlink(missing_ok=True)


async def prepare_environment() -> None:
    """首次导入前联合修复插件环境；校验成功后替换目录，不触发禁用或清配置。"""
    from app.core import Config
    from app.utils.common.tools import to_pep440

    from ..runtime.metadata import validate_install_metadata
    from ..types import CORE_DISTRIBUTION_NAME, CORE_PLUGIN_NAME
    from .precheck import (
        host_constraints,
        host_dependencies,
        plugin_targets,
        resolve_environment,
    )

    target = site_dir(activate=False)
    sys.path[:] = [item for item in sys.path if item != str(target.resolve())]
    pins = host_constraints()
    records = list(Config.plugin_registry.values())
    targets = plugin_targets(records, installed_path=target)
    existing = {
        canonicalize_name(dist.name): dist.version
        for dist in importlib_metadata.distributions(path=[str(target)])
        if canonicalize_name(dist.name) != canonicalize_name(CORE_DISTRIBUTION_NAME)
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
    if marker.is_file():
        try:
            if json.loads(marker.read_text(encoding="utf-8")) == fingerprint:
                previous = target.with_suffix(".previous")
                if previous.exists():
                    shutil.rmtree(previous)
                return
        except ValueError:
            logger.warning("插件环境记录损坏，重新准备依赖")

    logger.info("正在检查并准备插件依赖环境，完成后加载插件")
    previous = target.with_suffix(".previous")
    with tempfile.TemporaryDirectory(
        prefix=".prepare-", dir=target.parent
    ) as temporary:
        prepared = Path(temporary) / "site-packages"
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
            raise PluginError(f"插件自动升级失败：{result.detail}")

        # 源码覆盖只选择当前实现，不能顺带卸载被覆盖的发行包；源码移除后仍可回落。
        local_packages = {
            canonicalize_name(record.info.package_name)
            for record in records
            if record.info.source == "local"
            and record._project_dir is not None
            and record.info.plugin_name != CORE_PLUGIN_NAME
        }
        for distribution in importlib_metadata.distributions(path=[str(target)]):
            if canonicalize_name(distribution.name) not in local_packages:
                continue
            files = distribution.files
            if files is None:
                raise PluginError(
                    f"发行包缺少文件清单，无法保留本地覆盖副本：{distribution.name}"
                )
            for file in files:
                source = Path(str(distribution.locate_file(file))).resolve()
                relative = source.relative_to(target.resolve())
                destination = prepared / relative
                if destination.exists():
                    raise PluginError(
                        f"被本地源码覆盖的发行包与新环境文件冲突：{relative}"
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

        installed = {
            canonicalize_name(dist.name): dist
            for dist in importlib_metadata.distributions(path=[str(prepared)])
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
