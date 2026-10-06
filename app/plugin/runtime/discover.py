"""插件发行版和本地工程发现。"""

from __future__ import annotations

import asyncio
import importlib
import importlib.metadata as importlib_metadata
import pkgutil
from dataclasses import dataclass
from pathlib import Path

from pyproject_metadata import StandardMetadata

from app.core.config import Config
from app.models.config import PluginRecord
from app.utils import get_logger
from app.utils.io import read_file

from ..types import PluginCodeDrift, SourceChange
from .metadata import parse_to_plugin_record

logger = get_logger("插件发现")

_DISCOVERY_INFO_KEYS = (
    "plugin_name",
    "package_name",
    "version",
    "docs_url",
    "import_name",
    "source",
    "is_local",
    "is_core",
)
# 锁顺序硬约束：Manager._busy → refresh_lock；发现阶段不得反向获取 _busy。
refresh_lock = asyncio.Lock()


@dataclass(frozen=True)
class RefreshScope:
    """refresh 扫描范围；``None`` 表示全量扫描。"""

    changes: tuple[SourceChange, ...] | None = None


async def _parse_installed_package(
    dist: importlib_metadata.Distribution,
) -> PluginRecord | None:
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
    if not path.is_dir() or path.name.startswith(".") or path.name == "pypi":
        return None
    pyproject, src = path / "pyproject.toml", path / "src"
    if not pyproject.is_file() or not src.is_dir():
        raise ValueError("缺少 pyproject.toml 或 src/")
    data = read_file(pyproject)
    if not isinstance(data, dict):
        raise ValueError("pyproject 不是表")
    tops = [name for _, name, _ in pkgutil.iter_modules([str(src)])]
    if len(tops) != 1:
        raise ValueError(f"src 顶层模块不唯一: {tops!r}")
    package_dir = src / tops[0]
    if not package_dir.is_dir() or not (package_dir / "__init__.py").is_file():
        raise ValueError(f"无法定位普通插件包: {package_dir}")
    metadata = StandardMetadata.from_pyproject(data, project_dir=path)
    if metadata.version is None:
        raise ValueError("pyproject 缺少 version")
    return parse_to_plugin_record(
        metadata.as_rfc822(), import_name=tops[0], source="local"
    )


async def refresh(*, scope: RefreshScope | None = None) -> None:
    """发现插件元数据并统一应用到注册表，不导入插件代码。"""
    importlib.invalidate_caches()
    scope = scope or RefreshScope()
    async with refresh_lock:
        drafts: dict[str, tuple[PluginRecord, Path | None, bool]] = {}
        if scope.changes is None:
            for dist in importlib_metadata.distributions():
                try:
                    draft_record = await _parse_installed_package(dist)
                    if draft_record is not None:
                        drafts[draft_record.info.plugin_name] = (
                            draft_record,
                            draft_record._project_dir,
                            False,
                        )
                except Exception as exc:
                    logger.debug(f"扫描已安装发行版失败: {exc}")
            if Config.plugin_path.is_dir():
                for child in sorted(Config.plugin_path.iterdir()):
                    try:
                        draft_record = await _parse_source_package(child)
                        if draft_record is not None:
                            drafts[draft_record.info.plugin_name] = (
                                draft_record,
                                (child / "src").resolve(),
                                False,
                            )
                    except Exception as exc:
                        logger.debug(f"解析本地插件失败: {child}: {exc}")
            for record in list(Config.plugin_registry.values()):
                if record.info.plugin_name and record.info.plugin_name not in drafts:
                    draft_record = PluginRecord.build(
                        info=record.info.model_dump(mode="python")
                    )
                    draft_record.info.code_drift = PluginCodeDrift.PACKAGE_REMOVED
                    drafts[record.info.plugin_name] = (draft_record, None, False)
        else:
            for change in scope.changes:
                child, src = (
                    Path(change.local_dir).resolve(),
                    Path(change.local_dir).resolve() / "src",
                )
                matched = next(
                    (
                        item
                        for item in Config.plugin_registry.values()
                        if item._project_dir is not None
                        and item._project_dir.resolve() == src
                    ),
                    None,
                )
                try:
                    draft_record = await _parse_source_package(child)
                except Exception as exc:
                    logger.debug(f"解析本地插件失败: {child}: {exc}")
                    draft_record = None
                if draft_record is not None:
                    drafts[draft_record.info.plugin_name] = (
                        draft_record,
                        src,
                        change.code_touched,
                    )
                    continue
                if matched is None or not matched.info.package_name:
                    continue
                try:
                    draft_record = await _parse_installed_package(
                        importlib_metadata.distribution(matched.info.package_name)
                    )
                except Exception as exc:
                    logger.debug(f"已安装发行版回退解析失败: {exc}")
                    draft_record = None
                if draft_record is not None:
                    draft_record.info.code_drift = PluginCodeDrift.NEEDS_RELOAD
                    drafts[matched.info.plugin_name] = (
                        draft_record,
                        draft_record._project_dir,
                        change.code_touched,
                    )
                    continue
                draft_record = PluginRecord.build(
                    info=matched.info.model_dump(mode="python")
                )
                draft_record.info.code_drift = PluginCodeDrift.PACKAGE_REMOVED
                drafts[matched.info.plugin_name] = (
                    draft_record,
                    None,
                    change.code_touched,
                )

        for name, (draft, project_dir, code_touched) in drafts.items():
            existing = Config.plugin_registry.by_name(name)
            draft_drift = draft.info.code_drift
            if existing is None:
                if draft_drift == PluginCodeDrift.PACKAGE_REMOVED:
                    continue
                Config.plugin_registry.add(
                    PluginRecord,
                    payload={
                        "info": {
                            **{
                                key: getattr(draft.info, key)
                                for key in _DISCOVERY_INFO_KEYS
                            },
                            "code_drift": PluginCodeDrift.NORMAL,
                        }
                    },
                )
                await Config.plugin_registry.commit()
                added = Config.plugin_registry.by_name(name)
                if added is not None:
                    added._project_dir = project_dir
                continue
            if draft_drift == PluginCodeDrift.PACKAGE_REMOVED:
                drift = PluginCodeDrift.PACKAGE_REMOVED
            elif (
                existing.info.code_drift
                in (PluginCodeDrift.PACKAGE_REMOVED, PluginCodeDrift.NEEDS_RELOAD)
                or draft_drift == PluginCodeDrift.NEEDS_RELOAD
                or code_touched
            ):
                drift = PluginCodeDrift.NEEDS_RELOAD
            else:
                drift = PluginCodeDrift.NORMAL
            await existing.update(
                PluginRecord.build(
                    info={
                        **{
                            key: getattr(draft.info, key)
                            for key in _DISCOVERY_INFO_KEYS
                        },
                        "code_drift": drift,
                    }
                )
            )
            existing._project_dir = project_dir
        from app.core.i18n import i18n

        await i18n.invalidate()
