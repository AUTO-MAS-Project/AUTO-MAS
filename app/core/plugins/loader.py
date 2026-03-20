#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

import importlib.util
import inspect
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, Iterable, Optional, Literal

from app.utils import get_logger
from app.utils.constants import UTC8

from .context import PluginContext
from .pypi_site import ensure_pypi_site_packages_on_syspath, iter_plugin_entry_points
from .runtime_api import RuntimeAPI


logger = get_logger("插件加载器")


def _utc8_now_iso() -> str:
    """返回当前 UTC+8 时间的 ISO8601 字符串。"""
    return datetime.now(tz=UTC8).isoformat()


class PluginDefinitionError(Exception):
    """Expected plugin authoring errors that should not print traceback."""


@dataclass
class PluginRecord:
    instance_id: str
    plugin_name: str
    path: Optional[Path]
    display_name: str = ""
    status: str = "discovered"
    module: Optional[ModuleType] = None
    context: Optional[PluginContext] = None
    dispose: Optional[Callable[[], Any]] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=_utc8_now_iso)
    discovered_at: str = field(default_factory=_utc8_now_iso)
    loaded_at: Optional[str] = None
    activated_at: Optional[str] = None
    disposed_at: Optional[str] = None
    unloaded_at: Optional[str] = None
    last_error: Optional[str] = None
    last_error_at: Optional[str] = None


class PluginLoader:
    """从plugins/目录中发现、加载和卸载插件。"""

    @dataclass
    class PluginSource:
        """插件来源描述。"""

        source: Literal["local", "pypi"]
        path: Optional[Path] = None
        entry_point: Any = None
        module_name: Optional[str] = None
        distribution: Optional[str] = None
        version: Optional[str] = None

    def __init__(self, events, runtime: Any = None, plugins_dir: Optional[Path] = None):
        self.events = events
        self.runtime = {} if runtime is None else runtime
        self.plugins_dir = plugins_dir or (Path.cwd() / "plugins")
        self.pypi_site_packages_dir = ensure_pypi_site_packages_on_syspath(self.plugins_dir)
        self.records: Dict[str, PluginRecord] = {}
        self.discovered_plugins: Dict[str, PluginLoader.PluginSource] = {}
        self.startup_failed_instances: Dict[str, str] = {}
        self.startup_missing_instances: set[str] = set()

    def _iter_entry_points(self) -> list[Any]:
        """读取 plugins/pypi/site-packages 中的插件 Entry Points。"""
        try:
            return list(iter_plugin_entry_points(self.plugins_dir))
        except Exception as e:
            logger.warning(f"读取本地 PyPI Entry Points 失败: {e}")
            return []

    def discover(self) -> Dict[str, PluginSource]:
        """发现插件（本地目录优先，同时兼容 PyPI Entry Point）。"""
        ensure_pypi_site_packages_on_syspath(self.plugins_dir)
        discovered: Dict[str, PluginLoader.PluginSource] = {}

        if self.plugins_dir.exists():
            for item in sorted(self.plugins_dir.iterdir()):
                plugin_py = item / "plugin.py"
                if item.is_dir() and plugin_py.exists():
                    discovered[item.name] = self.PluginSource(source="local", path=item)
        else:
            logger.info(f"插件目录不存在，仅扫描 PyPI 插件: {self.plugins_dir}")

        for ep in self._iter_entry_points():
            plugin_name = str(getattr(ep, "name", "") or "").strip()
            if not plugin_name:
                continue

            if plugin_name in discovered:
                logger.warning(f"检测到同名 PyPI 插件，已忽略（本地优先）: {plugin_name}")
                continue

            dist = getattr(ep, "dist", None)
            distribution = getattr(dist, "name", None)
            version = getattr(dist, "version", None)

            discovered[plugin_name] = self.PluginSource(
                source="pypi",
                entry_point=ep,
                module_name=getattr(ep, "module", None),
                distribution=distribution,
                version=version,
            )

        self.discovered_plugins = discovered
        logger.info(f"插件扫描完成，共发现 {len(discovered)} 个插件")
        return discovered

    def _load_plugin_config(self, plugin_name: str, plugin_source: PluginSource) -> Dict[str, Any]:
        if plugin_source.source != "local" or plugin_source.path is None:
            return {}

        plugin_path = plugin_source.path
        config_path = plugin_path / "config.json"
        if not config_path.exists():
            return {}

        try:
            with config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            logger.warning(f"插件配置格式错误（非对象），已忽略: {plugin_name}")
            return {}
        except Exception as e:
            logger.error(f"读取插件配置失败: {plugin_name}, error={e}")
            return {}

    def _import_local_plugin_module(self, plugin_name: str, plugin_py: Path) -> ModuleType:
        module_name = f"mas_plugin_{plugin_name}"
        spec = importlib.util.spec_from_file_location(module_name, str(plugin_py))
        if spec is None or spec.loader is None:
            raise ImportError(f"无法创建插件模块规格: {plugin_name}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _load_setup_from_entry_point(self, plugin_name: str, entry_point: Any) -> tuple[Optional[ModuleType], Callable[..., Any]]:
        """从 PyPI Entry Point 加载插件 setup。"""
        loaded = entry_point.load()
        if inspect.ismodule(loaded):
            setup = getattr(loaded, "setup", None)
            if callable(setup):
                return loaded, setup
            raise PluginDefinitionError(f"插件缺少可调用入口 setup(ctx): {plugin_name}")

        if callable(loaded):
            module = inspect.getmodule(loaded)
            return module, loaded

        raise PluginDefinitionError(f"插件 Entry Point 返回了不支持的对象: {plugin_name}")

    def _clear_cached_pypi_module(self, plugin_name: str, plugin_source: PluginSource) -> None:
        """清理 PyPI 插件模块缓存，确保重载使用最新代码。"""
        if plugin_source.source != "pypi":
            return

        module_name = str(plugin_source.module_name or "").strip()
        if not module_name:
            entry_point = plugin_source.entry_point
            module_name = str(getattr(entry_point, "module", "") or "").strip()
        if not module_name:
            return

        target_keys = [
            key
            for key in list(sys.modules.keys())
            if key == module_name or key.startswith(f"{module_name}.")
        ]
        for key in target_keys:
            sys.modules.pop(key, None)

        if target_keys:
            logger.info(
                f"已清理 PyPI 插件模块缓存: plugin={plugin_name}, modules={len(target_keys)}"
            )

    def _resolve_plugin_module_and_setup(
        self,
        plugin_name: str,
        plugin_source: PluginSource,
    ) -> tuple[Optional[ModuleType], Callable[..., Any]]:
        """解析插件模块与 setup 入口。"""
        if plugin_source.source == "local":
            if plugin_source.path is None:
                raise PluginDefinitionError(f"本地插件路径缺失: {plugin_name}")
            plugin_py = plugin_source.path / "plugin.py"
            module = self._import_local_plugin_module(plugin_name, plugin_py)
            setup = getattr(module, "setup", None)
            if not callable(setup):
                raise PluginDefinitionError(
                    f"插件缺少可调用入口 setup(ctx): {plugin_name}"
                )
            return module, setup

        if plugin_source.entry_point is None:
            raise PluginDefinitionError(f"PyPI 插件缺少 Entry Point: {plugin_name}")
        self._clear_cached_pypi_module(plugin_name, plugin_source)
        return self._load_setup_from_entry_point(plugin_name, plugin_source.entry_point)

    async def _call_dispose(self, dispose: Callable[[], Any]) -> None:
        """调用插件 dispose，并兼容异步返回值。"""
        result = dispose()
        if inspect.isawaitable(result):
            await result

    def _mark_status(self, record: PluginRecord, status: str) -> None:
        """更新插件实例状态并记录对应时间戳。"""
        record.status = status

        status_time_map = {
            "discovered": "discovered_at",
            "loaded": "loaded_at",
            "active": "activated_at",
            "disposed": "disposed_at",
            "unloaded": "unloaded_at",
        }
        time_field = status_time_map.get(status)
        if time_field is not None:
            setattr(record, time_field, _utc8_now_iso())

        if status in {"active", "unloaded"}:
            record.error = None

    def _mark_error(self, record: PluginRecord, message: str) -> None:
        """记录插件错误并切换为 error 状态。"""
        record.error = message
        record.last_error = message
        record.last_error_at = _utc8_now_iso()
        record.status = "error"

    async def load_plugin(self, plugin_name: str) -> PluginRecord:
        if not self.discovered_plugins:
            self.discover()

        if plugin_name not in self.discovered_plugins:
            self.discover()
        if plugin_name not in self.discovered_plugins:
            raise KeyError(f"未发现插件: {plugin_name}")

        plugin_source = self.discovered_plugins[plugin_name]
        record = PluginRecord(
            instance_id=plugin_name,
            plugin_name=plugin_name,
            path=plugin_source.path,
            display_name=plugin_name,
        )
        self._mark_status(record, "discovered")
        self.records[record.instance_id] = record

        try:
            record.module, setup = self._resolve_plugin_module_and_setup(
                plugin_name,
                plugin_source,
            )
            self._mark_status(record, "loaded")

            plugin_logger = get_logger(f"插件:{plugin_name}")
            plugin_config = self._load_plugin_config(plugin_name, plugin_source)
            runtime_api = RuntimeAPI(
                plugin_name=plugin_name,
                instance_id=plugin_name,
                config=plugin_config,
                logger=plugin_logger,
                runtime_capabilities=self.runtime,
            )
            runtime_info = runtime_api.get_runtime_info()
            if not runtime_info.get("interpreter_check", {}).get("ok", False):
                reason = runtime_info.get("interpreter_check", {}).get("reason", "解释器检查失败")
                raise PluginDefinitionError(f"插件解释器不可用: {reason}")

            record.context = PluginContext(
                plugin_name=plugin_name,
                instance_id=plugin_name,
                config=plugin_config,
                logger=plugin_logger,
                events=self.events,
                runtime=runtime_api,
            )

            dispose = setup(record.context)
            if dispose is not None and not callable(dispose):
                raise PluginDefinitionError(
                    f"插件 {plugin_name} 返回的 dispose 不可调用"
                )

            record.dispose = dispose
            self._mark_status(record, "active")
            logger.info(f"插件已激活: {plugin_name}")
        except PluginDefinitionError as e:
            self._mark_error(record, str(e))
            logger.error(f"插件加载失败: {plugin_name}, error={e}")
        except Exception as e:
            self._mark_error(record, f"{type(e).__name__}: {e}")
            logger.exception(f"插件加载失败: {plugin_name}, error={e}")

        return record

    async def load_instance(
        self,
        *,
        instance_id: str,
        plugin_name: str,
        instance_name: str,
        config: Dict[str, Any],
    ) -> PluginRecord:
        """加载单个插件实例，不抛出实例级故障到上层。"""
        if not self.discovered_plugins:
            self.discover()

        if plugin_name not in self.discovered_plugins:
            self.discover()
        if plugin_name not in self.discovered_plugins:
            record = PluginRecord(
                instance_id=instance_id,
                plugin_name=plugin_name,
                path=None,
                display_name=instance_name or instance_id,
            )
            self._mark_status(record, "discovered")
            self._mark_error(record, f"未发现插件: {plugin_name}")
            self.records[instance_id] = record
            return record

        plugin_source = self.discovered_plugins[plugin_name]
        record = PluginRecord(
            instance_id=instance_id,
            plugin_name=plugin_name,
            path=plugin_source.path,
            display_name=instance_name or instance_id,
        )
        self._mark_status(record, "discovered")
        self.records[instance_id] = record

        try:
            record.module, setup = self._resolve_plugin_module_and_setup(
                plugin_name,
                plugin_source,
            )
            self._mark_status(record, "loaded")

            plugin_logger = get_logger(f"插件:{instance_id}")
            runtime_api = RuntimeAPI(
                plugin_name=plugin_name,
                instance_id=instance_id,
                config=config,
                logger=plugin_logger,
                runtime_capabilities=self.runtime,
            )
            runtime_info = runtime_api.get_runtime_info()
            if not runtime_info.get("interpreter_check", {}).get("ok", False):
                reason = runtime_info.get("interpreter_check", {}).get("reason", "解释器检查失败")
                raise PluginDefinitionError(f"插件解释器不可用: {reason}")

            record.context = PluginContext(
                plugin_name=plugin_name,
                instance_id=instance_id,
                config=config,
                logger=plugin_logger,
                events=self.events,
                runtime=runtime_api,
            )

            dispose = setup(record.context)
            if dispose is not None and not callable(dispose):
                raise PluginDefinitionError(
                    f"插件实例 {instance_id} 返回的 dispose 不可调用"
                )

            record.dispose = dispose
            self._mark_status(record, "active")
            logger.info(f"插件实例已激活: {instance_id} ({plugin_name})")
        except PluginDefinitionError as e:
            self._mark_error(record, str(e))
            logger.error(f"插件实例加载失败: {instance_id}, error={e}")
        except Exception as e:
            self._mark_error(record, f"{type(e).__name__}: {e}")
            logger.error(f"插件实例加载失败: {instance_id}, error={type(e).__name__}: {e}")

        return record

    async def load_all(self) -> Dict[str, PluginRecord]:
        self.discover()
        for plugin_name in list(self.discovered_plugins.keys()):
            await self.load_plugin(plugin_name)
        return self.records

    async def load_instances(self, instances: Iterable[Any]) -> Dict[str, PluginRecord]:
        """批量加载插件实例，并记录启动失败状态供上层修复配置。"""
        if not self.discovered_plugins:
            self.discover()
        self.startup_failed_instances = {}
        self.startup_missing_instances = set()

        for instance in instances:
            enabled = bool(getattr(instance, "enabled", False))
            if not enabled:
                continue

            instance_id = str(getattr(instance, "id"))
            plugin_name = str(getattr(instance, "plugin"))
            instance_name = str(getattr(instance, "name", "") or "")
            config = dict(getattr(instance, "config", {}) or {})

            record = await self.load_instance(
                instance_id=instance_id,
                plugin_name=plugin_name,
                instance_name=instance_name,
                config=config,
            )
            if record.status == "error":
                error_text = str(record.error or "未知错误")
                self.startup_failed_instances[instance_id] = error_text
                if error_text.startswith("未发现插件:"):
                    self.startup_missing_instances.add(instance_id)
                logger.error(
                    f"插件实例加载失败但已忽略（继续启动）: instance_id={instance_id}, plugin={plugin_name}, error='{error_text}'"
                )
        return self.records

    async def unload_plugin(self, plugin_name: str) -> None:
        record = self.records.get(plugin_name)
        if record is None:
            return

        if record.dispose is not None:
            try:
                await self._call_dispose(record.dispose)
                self._mark_status(record, "disposed")
            except Exception as e:
                self._mark_error(record, f"{type(e).__name__}: {e}")
                logger.exception(f"插件卸载失败: {plugin_name}, error={e}")
                return
        else:
            self._mark_status(record, "disposed")

        self._mark_status(record, "unloaded")
        logger.info(f"插件已卸载: {plugin_name}")

    async def unload_instance(self, instance_id: str) -> None:
        await self.unload_plugin(instance_id)

    async def unload_all(self) -> None:
        for plugin_name in list(self.records.keys()):
            await self.unload_plugin(plugin_name)
