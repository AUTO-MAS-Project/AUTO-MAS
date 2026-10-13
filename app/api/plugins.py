# MIGRATION REFERENCE ONLY: replaced by ConfigEntry/Trigger; remove after migration.
# """插件元信息和页面声明查询 API。"""
# 
# from fastapi import APIRouter, Body
# 
# from app.models.schema import (
#     OutBase,
#     PluginActionIn,
#     PluginInfoItem,
#     PluginListOut,
#     PluginPageDataOut,
#     PluginPageOut,
#     PluginPageUpdateIn,
# )
# from app.plugin.base import GameAdapterPlugin
# from app.plugin.manager import PluginManagerSingleton
# 
# router = APIRouter(prefix="/api/plugins", tags=["插件"])
# 
# 
# @router.get("", response_model=PluginListOut)
# async def list_plugins() -> PluginListOut:
#     return PluginListOut(
#         data=[
#             PluginInfoItem(
#                 plugin_id=plugin.metadata.plugin_id,
#                 name=plugin.metadata.name,
#                 version=plugin.metadata.version,
#                 description=plugin.metadata.description,
#                 pages=[
#                     PluginPageOut(
#                         page_id=page.page_id,
#                         title=page.title,
#                         components=[
#                             {
#                                 "key": component.key,
#                                 "kind": component.kind,
#                                 "label": component.label,
#                                 "width": int(component.width),
#                                 "required": component.required,
#                                 "config_group": component.config_group,
#                                 "config_name": component.config_name,
#                                 "options": list(component.options),
#                                 "props": component.props,
#                             }
#                             for component in page.components
#                         ],
#                     )
#                     for page in plugin.pages
#                 ],
#                 game_types=[
#                     {"value": game_type, "label": plugin.game_type_labels.get(game_type, game_type)}
#                     for game_type in plugin.game_types
#                 ]
#                 if isinstance(plugin, GameAdapterPlugin)
#                 else [],
#                 author=plugin.metadata.author,
#                 license=plugin.metadata.license,
#                 homepage=plugin.metadata.homepage,
#                 repository=plugin.metadata.repository,
#                 api_version=plugin.metadata.api_version,
#                 source=plugin.metadata.source,
#                 status="running",
#                 capabilities=list(plugin.metadata.capabilities),
#             )
#             for plugin in PluginManagerSingleton.plugins
#         ]
#     )
# 
# 
# def _get_page(plugin_id: str, page_id: str):
#     plugin = next(
#         (
#             item
#             for item in PluginManagerSingleton.plugins
#             if item.metadata.plugin_id == plugin_id
#         ),
#         None,
#     )
#     if plugin is None:
#         raise ValueError(f"插件未运行: {plugin_id}")
#     page = next((item for item in plugin.pages if item.page_id == page_id), None)
#     if page is None:
#         raise ValueError(f"插件页面不存在: {page_id}")
#     return plugin, page
# 
# 
# @router.get(
#     "/{plugin_id}/pages/{page_id}",
#     response_model=PluginPageDataOut,
#     summary="读取插件页面配置",
# )
# async def get_plugin_page(plugin_id: str, page_id: str) -> PluginPageDataOut:
#     try:
#         plugin, page = _get_page(plugin_id, page_id)
#         if plugin.config is None:
#             return PluginPageDataOut()
#         values = {
#             component.key: plugin.config.get(
#                 component.config_group, component.config_name
#             )
#             for component in page.components
#             if component.config_group is not None and component.config_name is not None
#         }
#         return PluginPageDataOut(values=values)
#     except Exception as error:
#         return PluginPageDataOut(code=404, status="error", message=str(error))
# 
# 
# @router.post(
#     "/{plugin_id}/pages/{page_id}",
#     response_model=OutBase,
#     summary="保存插件页面配置",
# )
# async def update_plugin_page(
#     plugin_id: str,
#     page_id: str,
#     payload: PluginPageUpdateIn = Body(...),
# ) -> OutBase:
#     try:
#         plugin, page = _get_page(plugin_id, page_id)
#         if plugin.config is None:
#             raise ValueError("插件未声明可持久化配置")
#         components = {
#             component.key: component
#             for component in page.components
#             if component.config_group is not None and component.config_name is not None
#         }
#         unknown = set(payload.values) - components.keys()
#         if unknown:
#             raise ValueError(f"页面未声明配置项: {', '.join(sorted(unknown))}")
#         grouped: dict[str, dict[str, object]] = {}
#         for key, value in payload.values.items():
#             component = components[key]
#             grouped.setdefault(component.config_group, {})[component.config_name] = (
#                 value
#             )
#         await plugin.config.update(grouped)
#         return OutBase()
#     except Exception as error:
#         return OutBase(code=400, status="error", message=str(error))
# 
# 
# @router.post(
#     "/{plugin_id}/actions/execute",
#     response_model=OutBase,
#     summary="鎵ц鎻掍欢澹版槑鍔ㄤ綔",
# )
# async def execute_plugin_action(
#     plugin_id: str,
#     payload: PluginActionIn = Body(...),
# ) -> OutBase:
#     try:
#         plugin = next(
#             (
#                 item
#                 for item in PluginManagerSingleton.plugins
#                 if item.metadata.plugin_id == plugin_id
#             ),
#             None,
#         )
#         if plugin is None:
#             raise ValueError(f"鎻掍欢鏈繍琛? {plugin_id}")
#         message = await plugin.execute_action(payload.action_id)
#         return OutBase(message=message or "鎿嶄綔瀹屾垚")
#     except Exception as error:
#         return OutBase(code=400, status="error", message=str(error))
