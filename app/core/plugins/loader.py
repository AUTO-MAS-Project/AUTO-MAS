#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

import importlib.util
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, Optional

from app.utils import get_logger

from .context import PluginContext


logger = get_logger("插件加载器")


class PluginDefinitionError(Exception):
    """Expected plugin authoring errors that should not print traceback."""


@dataclass
class PluginRecord:
    name: str
    path: Path
    status: str = "discovered"
    module: Optional[ModuleType] = None
    context: Optional[PluginContext] = None
    dispose: Optional[Callable[[], Any]] = None
    error: Optional[str] = None


class PluginLoader:
    """从plugins/目录中发现、加载和卸载插件。"""

    def __init__(self, events, runtime: Any = None, plugins_dir: Optional[Path] = None):
        self.events = events
        self.runtime = {} if runtime is None else runtime
        self.plugins_dir = plugins_dir or (Path.cwd() / "plugins")
        self.records: Dict[str, PluginRecord] = {}

    def discover(self) -> Dict[str, PluginRecord]:
        discovered: Dict[str, PluginRecord] = {}
        if not self.plugins_dir.exists():
            logger.info(f"插件目录不存在，跳过加载: {self.plugins_dir}")
            self.records = discovered
            return discovered

        for item in sorted(self.plugins_dir.iterdir()):
            plugin_py = item / "plugin.py"
            if item.is_dir() and plugin_py.exists():
                discovered[item.name] = PluginRecord(name=item.name, path=item)

        self.records = discovered
        logger.info(f"插件扫描完成，共发现 {len(discovered)} 个插件")
        return discovered

    def _load_plugin_config(self, plugin_name: str, plugin_path: Path) -> Dict[str, Any]:
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

    def _import_plugin_module(self, plugin_name: str, plugin_py: Path) -> ModuleType:
        module_name = f"mas_plugin_{plugin_name}"
        spec = importlib.util.spec_from_file_location(module_name, str(plugin_py))
        if spec is None or spec.loader is None:
            raise ImportError(f"无法创建插件模块规格: {plugin_name}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    async def _call_dispose(self, dispose: Callable[[], Any]) -> None:
        result = dispose()
        if inspect.isawaitable(result):
            await result

    async def load_plugin(self, plugin_name: str) -> PluginRecord:
        if plugin_name not in self.records:
            raise KeyError(f"未发现插件: {plugin_name}")

        record = self.records[plugin_name]
        plugin_py = record.path / "plugin.py"

        try:
            record.module = self._import_plugin_module(plugin_name, plugin_py)
            record.status = "loaded"

            setup = getattr(record.module, "setup", None)
            if not callable(setup):
                raise PluginDefinitionError(
                    f"插件缺少可调用入口 setup(ctx): {plugin_name}"
                )

            plugin_logger = get_logger(f"插件:{plugin_name}")
            plugin_config = self._load_plugin_config(plugin_name, record.path)
            record.context = PluginContext(
                plugin_name=plugin_name,
                config=plugin_config,
                logger=plugin_logger,
                events=self.events,
                runtime=self.runtime,
            )

            dispose = setup(record.context)
            if dispose is not None and not callable(dispose):
                raise PluginDefinitionError(
                    f"插件 {plugin_name} 返回的 dispose 不可调用"
                )

            record.dispose = dispose
            record.status = "active"
            logger.info(f"插件已激活: {plugin_name}")
        except PluginDefinitionError as e:
            record.error = str(e)
            record.status = "error"
            logger.error(f"插件加载失败: {plugin_name}, error={e}")
        except Exception as e:
            record.error = f"{type(e).__name__}: {e}"
            record.status = "error"
            logger.exception(f"插件加载失败: {plugin_name}, error={e}")

        return record

    async def load_all(self) -> Dict[str, PluginRecord]:
        self.discover()
        for plugin_name in list(self.records.keys()):
            await self.load_plugin(plugin_name)
        return self.records

    async def unload_plugin(self, plugin_name: str) -> None:
        record = self.records.get(plugin_name)
        if record is None:
            return

        if record.dispose is not None:
            try:
                await self._call_dispose(record.dispose)
                record.status = "disposed"
            except Exception as e:
                record.error = f"{type(e).__name__}: {e}"
                record.status = "error"
                logger.exception(f"插件卸载失败: {plugin_name}, error={e}")
                return
        else:
            record.status = "disposed"

        record.status = "unloaded"
        logger.info(f"插件已卸载: {plugin_name}")

    async def unload_all(self) -> None:
        for plugin_name in list(self.records.keys()):
            await self.unload_plugin(plugin_name)
