"""游戏中心插件服务实现

包装 app.core.game_center 的管理器与配置 CRUD, 以 "game_center" 服务名
发布到插件服务注册表。app/api/game_center.py 与其他插件均通过
PluginManager.service.get("game_center") 消费本服务。
"""

from __future__ import annotations

from typing import Any, Optional


class GameCenterService:
    """游戏中心服务门面

    暴露给其他插件的核心能力: install (更新游戏) / launch (启动游戏) /
    close (关闭游戏)。安卓模拟器游戏会先自动启动关联模拟器再执行
    更新/启动 (仅支持 MuMu / 雷电)。
    """

    def __init__(self, manager: Any) -> None:
        self._manager = manager

    # ======================== 配置 CRUD ========================

    async def get_config(self, game_id: Optional[str]) -> tuple[list, dict]:
        """获取游戏配置 (game_id 为 None 时返回全部)"""
        from app.core import Config

        return await Config.get_game(game_id)

    async def add(self, preset_key: Optional[str] = None) -> tuple[Any, Any]:
        """添加游戏项, 指定预设时以预设值预填新条目

        Raises:
            ValueError: 预设 key 未知。
        """
        from app.core import Config
        from app.core.game_center import get_preset

        uid, config = await Config.add_game()
        if preset_key:
            preset = get_preset(preset_key)
            if preset is None:
                raise ValueError(f"未知预设: {preset_key}")
            await config.set("Info", "Name", preset.name)
            await config.set("Info", "Platform", preset.platform)
            await config.set("Info", "Provider", preset.provider)
            await config.set("Info", "PresetKey", preset.key)
            if preset.package_name:
                await config.set("Data", "PackageName", preset.package_name)
        return uid, config

    async def update(self, game_id: str, data: dict) -> None:
        from app.core import Config

        await Config.update_game(game_id, data)

    async def delete(self, game_id: str) -> None:
        from app.core import Config

        await Config.del_game(game_id)

    async def reorder(self, index_list: list[str]) -> None:
        from app.core import Config

        await Config.reorder_game(index_list)

    def presets(self) -> list[dict]:
        """内置游戏预设列表"""
        from app.core.game_center import list_presets

        return list_presets()

    # ======================== 游戏操作 ========================

    async def check(self, game_id: str) -> dict[str, Any]:
        """检查更新, 返回 local_version / latest_version / needs_update / installed"""
        return await self._manager.check(game_id)

    async def install(self, game_id: str) -> dict[str, Any]:
        """安装/更新游戏 (后台任务, 进度经 WS id=game_center/{game_id} 推送)"""
        return await self._manager.install(game_id)

    async def cancel(self, game_id: str) -> dict[str, Any]:
        """取消运行中的安装/更新任务"""
        return await self._manager.cancel(game_id)

    async def launch(self, game_id: str) -> dict[str, Any]:
        """启动游戏 (模拟器游戏未启动模拟器时先自动拉起)"""
        return await self._manager.launch(game_id)

    async def close(self, game_id: str) -> dict[str, Any]:
        """关闭游戏"""
        return await self._manager.close(game_id)

    async def open_official_launcher(self, game_id: str) -> dict[str, Any]:
        """打开官方启动器 (鹰角回退路径)"""
        return await self._manager.open_official_launcher(game_id)

    async def install_local_apk(self, game_id: str, apk_path: str) -> dict[str, Any]:
        """手动安装本地 APK (模拟器游戏)"""
        return await self._manager.install_local_apk(game_id, apk_path)

    def task_status(self, game_id: str) -> dict[str, Any]:
        """查询任务状态 (轮询兜底)"""
        return self._manager.task_status(game_id)

    # ======================== 扩展点 ========================

    def register_provider(self, name: str, provider_cls: Any) -> None:
        """注册自定义游戏 provider (供其他插件扩展游戏来源)"""
        from app.core.game_center.registry import register_provider

        register_provider(name, provider_cls)
