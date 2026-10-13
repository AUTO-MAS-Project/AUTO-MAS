# MIGRATION REFERENCE ONLY: replaced by ConfigEntry/Trigger; remove after migration.
# """MuMu 游戏适配器插件。"""
# 
# from app.utils.emulator.mumu import MumuManager
# 
# from ..base import GameAdapterPlugin
# from ..types import PluginMetadata
# 
# 
# class MumuPlugin(GameAdapterPlugin):
#     metadata = PluginMetadata(
#         plugin_id="mumu",
#         name="MuMu 模拟器",
#         version="1.0.0",
#         description="提供 MuMu 实例的设备控制能力。",
#         author="AUTO-MAS Team",
#         license="AGPL-3.0",
#         homepage="https://auto-mas.top",
#         repository="https://github.com/AUTO-MAS-Project/AUTO-MAS",
#         capabilities=("game", "emulator", "device-control"),
#     )
#     game_types = {"mumu": MumuManager}
#     game_type_labels = {"mumu": "MuMu Emulator"}
