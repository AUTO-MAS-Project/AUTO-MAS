# MIGRATION REFERENCE ONLY: replaced by ConfigEntry/Trigger; remove after migration.
# """插件发现、路由挂载与生命周期管理。"""
# 
# from __future__ import annotations
# 
# import asyncio
# import re
# from importlib.metadata import entry_points
# from typing import TYPE_CHECKING
# 
# from fastapi import FastAPI
# 
# from app.models.emulator import DeviceBase
# from app.utils import get_logger
# 
# from .base import GameAdapterPlugin, PluginBase
# 
# logger = get_logger("插件管理")
# PLUGIN_ENTRY_POINT_GROUP = "auto_mas.plugins"
# PLUGIN_ID_PATTERN = re.compile(r"[a-z][a-z0-9._-]{0,63}\Z")
# 
# if TYPE_CHECKING:
#     from app.models.config import EmulatorConfig
# 
# 
# class PluginManager:
#     """隔离插件启动失败并管理插件路由与生命周期。"""
# 
#     def __init__(self) -> None:
#         self._plugins: dict[str, PluginBase] = {}
#         self._started: list[PluginBase] = []
#         self._lock = asyncio.Lock()
#         self._discovered = False
#         self._startup_complete = False
# 
#     @property
#     def plugins(self) -> tuple[PluginBase, ...]:
#         return tuple(self._started)
# 
#     def discover(self) -> None:
#         """从安装包的 ``auto_mas.plugins`` entry point 加载插件类。"""
#         if self._discovered:
#             return
#         from .games.mumu import MumuPlugin
# 
#         self._register(MumuPlugin)
#         points = sorted(
#             entry_points(group=PLUGIN_ENTRY_POINT_GROUP), key=lambda item: item.name
#         )
#         for point in points:
#             try:
#                 plugin_type = point.load()
#                 if not isinstance(plugin_type, type) or not issubclass(
#                     plugin_type, PluginBase
#                 ):
#                     raise TypeError("entry point 必须指向 PluginBase 子类")
#                 self._register(plugin_type)
#             except Exception:
#                 logger.exception(f"加载插件入口失败: {point.name}")
#         self._discovered = True
# 
#     def _register(self, plugin_type: type[PluginBase]) -> None:
#         plugin = plugin_type()
#         plugin_id = plugin.metadata.plugin_id
#         if not PLUGIN_ID_PATTERN.fullmatch(plugin_id) or plugin_id in self._plugins:
#             raise ValueError(f"插件 id 无效或重复: {plugin_id!r}")
#         self._plugins[plugin_id] = plugin
# 
#     def get_game_manager(
#         self, game_type: str, config: EmulatorConfig
#     ) -> DeviceBase | None:
#         """按游戏类型构造已注册插件提供的控制器。"""
#         for plugin in self._started:
#             if not isinstance(plugin, GameAdapterPlugin):
#                 continue
#             manager_type = plugin.game_types.get(game_type)
#             if manager_type is not None:
#                 return manager_type(config)
#         return None
# 
#     async def startup(self, app: FastAPI) -> None:
#         """挂载有效插件路由并逐个运行启动钩子。"""
#         async with self._lock:
#             if self._startup_complete:
#                 return
#             if not self._plugins:
#                 self.discover()
#             for plugin in self._plugins.values():
#                 try:
#                     if plugin.config_class is not None:
#                         from app.core import Config
# 
#                         plugin.config = plugin.config_class()
#                         await plugin.config.connect(
#                             Config.config_path
#                             / "plugins"
#                             / f"{plugin.metadata.plugin_id}.json"
#                         )
#                     await plugin.startup()
#                 except asyncio.CancelledError:
#                     raise
#                 except Exception:
#                     logger.exception(
#                         f"插件启动失败: {plugin.metadata.plugin_id}"
#                     )
#                     continue
#                 self._started.append(plugin)
#                 if plugin.router is not None:
#                     app.include_router(
#                         plugin.router,
#                         prefix=f"/api/plugins/{plugin.metadata.plugin_id}",
#                     )
#             self._startup_complete = True
# 
#     async def shutdown(self) -> None:
#         """按启动逆序关闭插件；单个插件失败不阻断其余清理。"""
#         async with self._lock:
#             for plugin in reversed(self._started):
#                 try:
#                     await plugin.shutdown()
#                 except asyncio.CancelledError:
#                     raise
#                 except Exception:
#                     logger.exception(
#                         f"插件关闭失败: {plugin.metadata.plugin_id}"
#                     )
#             self._started.clear()
#             self._startup_complete = False
# 
# 
# PluginManagerSingleton = PluginManager()
