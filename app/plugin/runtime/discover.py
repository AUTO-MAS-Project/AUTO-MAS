"""插件发行版和本地工程发现。"""

from __future__ import annotations

import asyncio
import importlib
import importlib.metadata as importlib_metadata
import pkgutil
import site
from dataclasses import dataclass
from pathlib import Path

from packaging.utils import canonicalize_name
from pyproject_metadata import StandardMetadata

from app.config import config_manager
from app.core.config import Config
from app.models.config import PluginRecord
from app.utils import get_logger
from app.utils.common.io import read_file
from app.utils.common.tools import to_pep440

from ..errors import PluginPrecheckError
from ..types import MARKET_GATE_TAG, PluginCodeDrift, SourceChange
from .metadata import parse_to_plugin_record

logger = get_logger("插件发现")

_DISCOVERY_INFO_KEYS = (
    "plugin_name",
    "package_name",
    "version",
    "docs_url",
    "homepage",
    "repository",
    "author",
    "license",
    "requires_dist",
    "display_name_i18n",
    "description_i18n",
    "tags_i18n",
    "import_name",
    "source",
    "is_local",
    "is_core",
)
# 锁顺序硬约束：Manager._busy → refresh_lock；发现阶段不得反向获取 _busy。
refresh_lock = asyncio.Lock()


@dataclass(frozen=True)
class RefreshScope:
    """变化工程及代码标记；发现始终检查完整候选，避免增量刷新绕过冲突校验。"""

    changes: tuple[SourceChange, ...] | None = None


async def _parse_installed_package(
    dist: importlib_metadata.Distribution,
) -> PluginRecord | None:
    # 先检查发行包门禁，避免遍历所有普通依赖的文件列表。
    """筛选带插件标记的已安装发行包，解析元数据并定位导入根目录，生成待加载注册记录。"""
    metadata = dist.metadata
    if hasattr(metadata, "get"):
        keywords = metadata.get("Keywords")
        if MARKET_GATE_TAG not in str(keywords or ""):
            return None
    elif hasattr(metadata, "Keywords"):
        keywords = getattr(metadata, "Keywords")
        if MARKET_GATE_TAG not in str(keywords or ""):
            return None
    else:
        # 非标准 Distribution 测试替身可能没有 metadata 映射；继续按文件结构解析。
        keywords = ""
    if keywords is None:
        return None
    try:
        files = dist.files
    except Exception:
        files = None
    tops: list[str] = []
    for item in files or []:
        parts = Path(str(item)).parts
        if not parts:
            continue
        top = parts[0]
        if top.endswith((".dist-info", ".data")) or top == "__pycache__":
            continue
        if len(parts) == 1 and top.endswith(".py"):
            top = top[:-3]
        if top and top not in tops:
            tops.append(top)
    if not tops:
        fallback = (dist.name or "").replace("-", "_").lower()
        if fallback:
            tops = [fallback]
    if len(tops) != 1:
        raise ValueError(f"发行版 top-level 不唯一: {tops}")
    load_search_root = Path(str(dist.locate_file("."))).resolve()
    package_dir = load_search_root / tops[0]
    if not load_search_root.is_dir() or not (package_dir / "__init__.py").is_file():
        raise ValueError(f"无法定位普通插件包: {package_dir}")
    draft_record = parse_to_plugin_record(
        dist.metadata, import_name=tops[0], source="installed"
    )
    if draft_record is not None:
        draft_record._project_dir = load_search_root
    return draft_record


async def _parse_source_package(path: Path) -> PluginRecord | None:
    """检查本地插件目录结构，将项目元数据转换为插件记录；core SDK 源码版本随宿主版本同步。"""
    if not path.is_dir() or path.name.startswith(".") or path.name == "pypi":
        return None
    pyproject, src = path / "pyproject.toml", path / "src"
    if not pyproject.is_file() or not src.is_dir():
        raise ValueError("缺少 pyproject.toml 或 src/")
    data = read_file(pyproject)
    if not isinstance(data, dict):
        raise ValueError("pyproject 不是表")
    if path.resolve() == (Config.source_path / "plugins" / "auto_mas_core").resolve():
        data["project"]["version"] = to_pep440(Config.VERSION)
        from app.plugin.uv.precheck import host_dependencies

        data["project"]["dependencies"] = host_dependencies()
        data["project"].pop("dynamic", None)
    tops = [name for _, name, _ in pkgutil.iter_modules([str(src)])]
    if len(tops) != 1:
        raise ValueError(f"src 顶层模块不唯一: {tops!r}")
    package_dir = src / tops[0]
    if not package_dir.is_dir() or not (package_dir / "__init__.py").is_file():
        raise ValueError(f"无法定位普通插件包: {package_dir}")
    metadata = StandardMetadata.from_pyproject(data, project_dir=path)
    if metadata.version is None:
        raise ValueError("pyproject 缺少 version")
    record = parse_to_plugin_record(
        metadata.as_rfc822(), import_name=tops[0], source="local"
    )
    if record is not None:
        record._project_dir = src.resolve()
    return record


def _source_projects() -> set[Path]:
    return {
        child.resolve()
        for root in (Config.plugins_path, Config.source_path / "plugins")
        if root.is_dir()
        for child in root.iterdir()
    }


async def refresh(
    *, scope: RefreshScope | None = None, installed_path: Path | None = None
) -> None:
    """发现插件元数据并统一应用到注册表，不导入插件代码。"""
    importlib.invalidate_caches()
    importlib_metadata.MetadataPathFinder.invalidate_caches()
    scope = scope or RefreshScope()
    async with refresh_lock:
        registry = Config.plugin_registry
        candidates: list[PluginRecord] = []
        seen: set[tuple[Path | None, str, str, str]] = set()
        distributions = (
            importlib_metadata.distributions()
            if installed_path is None
            else importlib_metadata.distributions(
                path=[str(installed_path), *site.getsitepackages()]
            )
        )
        for dist in distributions:
            try:
                draft = await _parse_installed_package(dist)
            except Exception as exc:
                logger.debug(f"扫描已安装发行版失败: {exc}")
                continue
            if draft is None:
                continue
            # 重复搜索路径可返回同一发行包；不同版本、位置或声明仍属于不同候选。
            origin = (
                draft._project_dir,
                canonicalize_name(draft.info.package_name),
                draft.info.version,
                str(dist.metadata),
            )
            if origin not in seen:
                seen.add(origin)
                candidates.append(draft)

        for child in sorted(_source_projects()):
            try:
                draft = await _parse_source_package(child)
            except Exception as exc:
                logger.debug(f"解析本地插件失败: {child}: {exc}")
                continue
            if draft is not None:
                candidates.append(draft)

        # 先检查整次发现结果，不让后扫描来源覆盖先扫描来源。
        grouped: dict[str, list[PluginRecord]] = {}
        imports: dict[str, str] = {}
        packages: dict[str, str] = {}
        for draft in candidates:
            name = draft.info.plugin_name
            package = canonicalize_name(draft.info.package_name)
            for key, owners, label in (
                (draft.info.import_name, imports, "导入名"),
                (package, packages, "发行包"),
            ):
                owner = owners.get(key)
                if owner is not None and owner != name:
                    raise PluginPrecheckError(
                        f"插件 `{owner}` 与 `{name}` 使用了相同的{label} `{key}`"
                    )
                owners[key] = name
            grouped.setdefault(name, []).append(draft)

        touched = {
            Path(change.local_dir).resolve()
            for change in scope.changes or ()
            if change.code_touched
        }
        drafts: dict[str, tuple[PluginRecord, Path | None, bool]] = {}
        for name, group in grouped.items():
            local = [item for item in group if item.info.source == "local"]
            installed = [item for item in group if item.info.source == "installed"]
            reason = ""
            if len({canonicalize_name(item.info.package_name) for item in group}) > 1:
                reason = "同一身份对应多个发行包"
            elif len(local) > 1:
                reason = "同一插件存在多个本地工程"
            elif len(installed) > 1:
                reason = "同一插件存在多个安装版本或位置"
            if reason:
                origins = "；".join(
                    f"{item.info.package_name} {item.info.version}: {item._project_dir}"
                    for item in group
                )
                raise PluginPrecheckError(
                    f"插件 `{name}` 发现冲突：{reason}（{origins}）"
                )
            draft = local[0] if local else installed[0]
            project_dir = draft._project_dir
            drafts[name] = (
                draft,
                project_dir,
                draft.info.source == "local"
                and project_dir is not None
                and project_dir.parent in touched,
            )

        for record in registry.values():
            if record.info.plugin_name and record.info.plugin_name not in drafts:
                draft = PluginRecord.build(info=record.info.model_dump(mode="python"))
                draft.info.code_drift = PluginCodeDrift.PACKAGE_REMOVED
                drafts[record.info.plugin_name] = (draft, None, False)

        # 已加载实现即使来源已移除，也在显式卸载/重载前占用原导入名。
        for record in registry.values():
            if record._plugin_cls is None:
                continue
            namespaces = {
                record.info.import_name,
                record._plugin_cls.__module__.split(".", 1)[0],
            }
            for namespace in namespaces:
                owner = imports.get(namespace)
                if owner is not None and owner != record.info.plugin_name:
                    raise PluginPrecheckError(
                        f"导入名 `{namespace}` 仍被已加载插件 `{record.info.plugin_name}` 使用，不能分配给 `{owner}`"
                    )

        paths: dict[str, Path | None] = {}
        async with config_manager.transaction():
            for name, (draft, project_dir, code_touched) in drafts.items():
                existing = registry.by_name(name)
                draft_drift = draft.info.code_drift
                info = {key: getattr(draft.info, key) for key in _DISCOVERY_INFO_KEYS}
                if existing is None:
                    registry.add(
                        PluginRecord,
                        payload={
                            "info": {
                                **info,
                                "code_drift": PluginCodeDrift.NORMAL,
                                "enabled": draft.info.enabled,
                            }
                        },
                    )
                    await registry.commit()
                    paths[name] = project_dir
                    continue
                source_changed = (
                    existing.info.source != draft.info.source
                    or existing.info.import_name != draft.info.import_name
                    or existing.info.version != draft.info.version
                    or canonicalize_name(existing.info.package_name)
                    != canonicalize_name(draft.info.package_name)
                    or existing._project_dir is not None
                    and existing._project_dir != project_dir
                )
                if draft_drift == PluginCodeDrift.PACKAGE_REMOVED:
                    drift = PluginCodeDrift.PACKAGE_REMOVED
                elif (
                    existing.info.code_drift
                    in (PluginCodeDrift.PACKAGE_REMOVED, PluginCodeDrift.NEEDS_RELOAD)
                    or draft_drift == PluginCodeDrift.NEEDS_RELOAD
                    or code_touched
                    or source_changed
                ):
                    drift = PluginCodeDrift.NEEDS_RELOAD
                else:
                    drift = PluginCodeDrift.NORMAL
                await existing.update(
                    PluginRecord.build(info={**info, "code_drift": drift})
                )
                paths[name] = project_dir
        # 私有运行时路径不参与配置事务，只在整批元数据提交成功后替换。
        for name, project_dir in paths.items():
            record = registry.by_name(name)
            assert record is not None
            record._project_dir = project_dir
        from app.core.i18n import I18n

        I18n.set_plugin_sources(
            {
                record.info.plugin_name: record._project_dir
                / record.info.import_name
                / "i18n"
                for record in registry.values()
                if record._project_dir is not None
                and record.info.import_name
                and record.info.code_drift != PluginCodeDrift.PACKAGE_REMOVED
            }
        )
        await I18n.get_locales()
