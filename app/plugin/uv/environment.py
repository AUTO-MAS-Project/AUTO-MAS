"""插件环境的候选安装、热发布与跨进程切换；旧环境保留至启动验证完成。"""

from __future__ import annotations

import importlib
import importlib.metadata as metadata
import json
import shutil
import sys
from pathlib import Path
from uuid import UUID

from packaging.utils import canonicalize_name
from pydantic import BaseModel, Field

from app.models.schema import PluginInstallation
from app.plugin.errors import PluginError
from app.utils import get_logger

logger = get_logger("插件环境")


class InstallationRecord(BaseModel):
    """保存切换基线和公开进度；磁盘位置始终由宿主计算。"""

    progress: PluginInstallation
    core_version: str
    host_constraints: list[str]
    baseline: dict[str, str]
    healthy_plugins: list[str] = Field(default_factory=list)
    local_sources: dict[str, str] = Field(default_factory=dict)
    previous_record: UUID | None = None
    # 为解开依赖一起升级的其他已装插件：规范化包名 → 新版本。
    co_upgraded: dict[str, str] = Field(default_factory=dict)


def distributions(directory: Path) -> dict[str, metadata.Distribution]:
    """读取指定环境中的实际发行包，排除宿主合成的 SDK。"""
    from app.plugin.types import CORE_DISTRIBUTION_NAME

    return {
        canonicalize_name(dist.name): dist
        for dist in metadata.distributions(path=[str(directory)])
        if canonicalize_name(dist.name) != canonicalize_name(CORE_DISTRIBUTION_NAME)
    }


def read_installation() -> InstallationRecord | None:
    """读取最近一次安装的持久进度，重启期间也可重复查询。"""
    from .ops import site_dir

    path = site_dir(activate=False).parent / "installation.json"
    if not path.is_file():
        return None
    return InstallationRecord.model_validate_json(path.read_text(encoding="utf-8"))


def write_installation(record: InstallationRecord) -> None:
    """原子保存安装进度，避免中断留下半份重启交接记录。"""
    from .ops import site_dir

    path = site_dir(activate=False).parent / "installation.json"
    pending = path.with_suffix(".tmp")
    pending.write_text(record.model_dump_json(), encoding="utf-8")
    pending.replace(path)


def ensure_writable() -> None:
    """等待重启或尚有恢复原件时拒绝另一轮装卸，防止覆盖交接所有权。"""
    from .ops import site_dir

    record = read_installation()
    if record is None:
        return
    target = site_dir(activate=False)
    if record.progress.state in {"waiting_restart", "applying"} or (
        record.progress.state == "failed"
        and (
            target.with_suffix(".previous").exists()
            or (target.parent / f".publish-{record.progress.installationId}").exists()
        )
    ):
        raise PluginError("已有插件安装等待重启或恢复，请先重启后端完成该操作")


def preserve_local_packages(target: Path, prepared: Path) -> None:
    """保留被本地源码覆盖的发行副本，不允许候选包覆盖其文件。"""
    from app.core import Config
    from app.plugin.types import CORE_PLUGIN_NAME

    packages = {
        canonicalize_name(record.info.package_name)
        for record in Config.plugin_registry.values()
        if record.info.source == "local"
        and record._project_dir is not None
        and record.info.plugin_name != CORE_PLUGIN_NAME
    }
    for name, distribution in distributions(target).items():
        if name not in packages:
            continue
        if distribution.files is None:
            raise PluginError(f"发行包缺少文件清单，无法保留本地覆盖副本：{name}")
        for file in distribution.files:
            source = Path(distribution.locate_file(file)).resolve()
            destination = prepared / source.relative_to(target.resolve())
            if destination.exists():
                raise PluginError(f"本地源码的发行副本与新环境文件冲突：{file}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def changed_loaded_dependencies(prepared: Path, replacing: str) -> list[str]:
    """比较候选环境与已导入文件的发行归属，只对实际换版的在用依赖要求重启。"""
    from .ops import site_dir

    current = distributions(site_dir(activate=False))
    proposed = distributions(prepared)
    loaded = {
        Path(file).resolve()
        for module in tuple(sys.modules.values())
        if (file := getattr(module, "__file__", None)) is not None
    }
    restart = []
    for name, distribution in current.items():
        other = proposed.get(name)
        if name == canonicalize_name(replacing):
            # 插件自身由既有生命周期重载；已加载的原生扩展仍须交给新进程。
            files = distribution.files or []
            if not any(
                str(path).casefold().endswith((".pyd", ".so", ".dll")) for path in files
            ):
                continue
        elif other is not None and other.version == distribution.version:
            continue
        else:
            files = distribution.files
            if files is None:
                raise PluginError(f"发行包缺少文件清单，无法确认加载归属：{name}")
        if any(
            Path(distribution.locate_file(file)).resolve() in loaded for file in files
        ):
            restart.append(name)
    return restart


def _remove_empty_parents(root: Path, files: set[Path]) -> None:
    """清除已删除文件的空父目录，避免残留空 dist-info 被识别为发行包。"""
    directories = {
        root / parent
        for path in files
        for parent in path.parents
        if parent != Path(".")
    }
    for directory in sorted(
        directories, key=lambda path: len(path.parts), reverse=True
    ):
        if directory.is_dir() and next(directory.iterdir(), None) is None:
            directory.rmdir()


def _clear_bytecode(root: Path, files: set[Path]) -> None:
    """清除变更模块的字节码，防止同时间戳和文件长度使旧代码被再次复用。"""
    for relative in files:
        if relative.suffix != ".py":
            continue
        directory = root / relative.parent / "__pycache__"
        for cache in directory.glob(f"{relative.stem}.*.pyc"):
            cache.unlink(missing_ok=True)
        if directory.is_dir() and next(directory.iterdir(), None) is None:
            directory.rmdir()


def publish_hot(prepared: Path, replacing: str) -> None:
    """只替换发生变化的发行包；文件发布失败时恢复原件，未变化的已加载库不动。"""
    from .ops import site_dir

    target = site_dir()
    current = distributions(target)
    proposed = distributions(prepared)
    changed = {
        name
        for name in current.keys() | proposed.keys()
        if name == canonicalize_name(replacing)
        or name not in current
        or name not in proposed
        or current[name].version != proposed[name].version
    }
    old_files: set[Path] = set()
    new_files: set[Path] = set()
    for packages, root, paths in (
        (current, target, old_files),
        (proposed, prepared, new_files),
    ):
        for name in changed & packages.keys():
            distribution = packages[name]
            if distribution.files is None:
                raise PluginError(f"发行包缺少文件清单：{name}")
            for file in distribution.files:
                source = Path(distribution.locate_file(file)).resolve()
                relative = source.relative_to(root.resolve())
                if source.is_file():
                    paths.add(relative)
    # 先备份全部原件，任何备份失败均不改变在线环境。
    record = read_installation()
    assert record is not None
    backup = target.parent / f".publish-{record.progress.installationId}"
    original = backup / "original"
    for relative in old_files:
        destination = original / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target / relative, destination)
    fresh = backup / "new"
    fresh.mkdir(parents=True, exist_ok=True)
    for relative in new_files:
        destination = fresh / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(prepared / relative, destination)
    manifest = backup / "files.json"
    temporary_manifest = manifest.with_suffix(".tmp")
    temporary_manifest.write_text(
        json.dumps(
            {
                "old": [str(path) for path in old_files],
                "new": [str(path) for path in new_files],
            }
        ),
        encoding="utf-8",
    )
    temporary_manifest.replace(manifest)
    try:
        for relative in sorted(new_files):
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            (fresh / relative).replace(destination)
        for relative in old_files - new_files:
            (target / relative).unlink(missing_ok=True)
        _clear_bytecode(target, old_files | new_files)
        _remove_empty_parents(target, old_files - new_files)
    except BaseException:
        restore_hot(record)
        raise
    importlib.invalidate_caches()
    metadata.MetadataPathFinder.invalidate_caches()
    (target.parent / "environment.json").unlink(missing_ok=True)


def restore_hot(record: InstallationRecord) -> bool:
    """恢复未确认的热发布；恢复失败时保留全部原件，下次启动继续处理。"""
    from .ops import site_dir

    target = site_dir(activate=False)
    backup = target.parent / f".publish-{record.progress.installationId}"
    manifest = backup / "files.json"
    if not manifest.is_file():
        if backup.exists():
            # 恢复清单尚未提交时在线文件还没有变化，只需回收未完成的备份。
            shutil.rmtree(backup)
        return False
    files = json.loads(manifest.read_text(encoding="utf-8"))
    old, new = ({Path(path) for path in files[key]} for key in ("old", "new"))
    # 恢复清单也是文件输入，所有目标必须仍位于插件环境与原件目录内。
    for relative in old | new:
        (target / relative).resolve().relative_to(target.resolve())
        (backup / "original" / relative).resolve().relative_to(
            (backup / "original").resolve()
        )
    for relative in new - old:
        (target / relative).unlink(missing_ok=True)
    for relative in old:
        source = backup / "original" / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_file() and destination.read_bytes() == source.read_bytes():
            continue
        shutil.copy2(source, destination)
    _clear_bytecode(target, old | new)
    _remove_empty_parents(target, new - old)
    shutil.rmtree(backup)
    importlib.invalidate_caches()
    metadata.MetadataPathFinder.invalidate_caches()
    return True


async def apply_pending() -> bool:
    """新进程首次导入前切换候选；上次启动未确认成功时恢复旧环境。"""
    from app.core import Config

    from .ops import site_dir
    from .precheck import host_constraints, plugin_targets

    record = read_installation()
    if record is None or record.progress.state == "succeeded":
        return False
    target = site_dir(activate=False)
    previous = target.with_suffix(".previous")
    pending = target.with_suffix(".pending")
    if record.progress.state in {"applying", "failed"}:
        restored = restore_hot(record)
        if previous.exists():
            failed = target.with_suffix(".failed")
            if failed.exists():
                shutil.rmtree(failed)
            target.rename(failed)
            previous.rename(target)
            importlib.invalidate_caches()
            metadata.MetadataPathFinder.invalidate_caches()
            (target.parent / "environment.json").unlink(missing_ok=True)
            restored = True
        if restored and record.previous_record is None:
            created = Config.plugin_registry.by_name(record.progress.pluginName)
            if (
                created is not None
                and created.info.source == "installed"
                and canonicalize_name(created.info.package_name)
                == canonicalize_name(record.progress.packageName)
            ):
                Config.plugin_registry.remove(created.uid)
                await Config.plugin_registry.commit()
        record.progress.state = "failed"
        record.progress.message = "插件环境启动未完成，已保留原环境，请检查后重试"
        write_installation(record)
        return False
    actual = {name: dist.version for name, dist in distributions(target).items()}
    current_sources = {
        str(project.resolve()): project.read_text(encoding="utf-8")
        for item in plugin_targets(
            Config.plugin_registry.values(),
            replacing=record.progress.packageName,
            installed_path=target,
        )
        if (project := Path(item) / "pyproject.toml").is_file()
    }
    current_plugin = Config.plugin_registry.by_name(record.progress.pluginName)
    if (
        Config.VERSION != record.core_version
        or host_constraints() != record.host_constraints
        or actual != record.baseline
        or current_sources != record.local_sources
        or (
            current_plugin is not None
            and current_plugin.info.source == "local"
            and current_plugin._project_dir is not None
        )
        or not pending.is_dir()
        or any(
            not Path(path).is_file()
            or Path(path).read_text(encoding="utf-8") != declaration
            for path, declaration in record.local_sources.items()
        )
    ):
        record.progress.state = "failed"
        record.progress.message = "插件环境已变化，候选安装已停止，请重新安装"
        write_installation(record)
        return False
    if previous.exists():
        shutil.rmtree(previous)
    # 先写切换意图：任意一步中断，下一次启动都按旧环境恢复。
    record.progress.state = "applying"
    write_installation(record)
    target.rename(previous)
    try:
        pending.rename(target)
    except OSError:
        previous.rename(target)
        raise
    importlib.invalidate_caches()
    metadata.MetadataPathFinder.invalidate_caches()
    (target.parent / "environment.json").unlink(missing_ok=True)
    return True


def finish_installation() -> None:
    """在插件完成加载和启用后确认安装；故障保留旧环境供下次启动恢复。"""
    from app.core import Config
    from app.plugin.types import PluginState

    from .ops import site_dir

    record = read_installation()
    if record is None or record.progress.state != "applying":
        return
    for name in {record.progress.pluginName, *record.healthy_plugins}:
        plugin = Config.plugin_registry.by_name(name)
        # pre_enable 失败会保留 disabled；只有达到用户保存的启用意图才算新环境可用。
        if plugin is None or plugin.info.state != (
            PluginState.ENABLED if plugin.info.enabled else PluginState.DISABLED
        ):
            record.progress.state = "failed"
            record.progress.message = "新插件环境加载失败，下次启动将恢复原环境"
            write_installation(record)
            raise PluginError(record.progress.message)
    record.progress.state = "succeeded"
    record.progress.message = None
    write_installation(record)
    previous = site_dir(activate=False).with_suffix(".previous")
    backup = previous.parent / f".publish-{record.progress.installationId}"
    for directory in (previous, backup):
        if not directory.exists():
            continue
        try:
            shutil.rmtree(directory)
        except OSError:
            logger.warning("旧插件环境暂未清理，下次启动继续回收")
