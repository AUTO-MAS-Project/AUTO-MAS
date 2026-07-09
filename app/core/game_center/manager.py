#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""游戏中心任务管理器

管理每款游戏的检查更新 / 安装 / 启动等操作, 每游戏同时仅允许一个操作。
进度通过 WebSocket 推送到前端 (id = "game_center/{uid}")。
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from app.utils import get_logger

from .base import GameProvider, ProgressEvent
from .presets import GamePreset, get_preset
from .registry import create_provider, _register_builtin_providers

logger = get_logger("游戏中心")


@dataclass
class TaskState:
    """单游戏任务状态"""

    running: bool = False
    phase: str = ""
    percent: float = 0.0
    downloaded: int = 0
    total: int = 0
    speed: float = 0.0
    detail: str = ""

    def update_from_event(self, event: ProgressEvent) -> None:
        self.phase = event.phase
        self.percent = event.percent
        self.downloaded = event.downloaded
        self.total = event.total
        self.speed = event.speed
        self.detail = event.message

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "phase": self.phase,
            "percent": self.percent,
            "downloaded": self.downloaded,
            "total": self.total,
            "speed": self.speed,
            "detail": self.detail,
        }


class GameCenterManager:
    """游戏中心管理器

    管理游戏 provider 的创建、后台任务、进度推送与取消。
    生命周期跟随应用, 在 main.py lifespan 中创建并注册清理。
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._states: dict[str, TaskState] = {}
        self._initialized = False

    def init(self) -> None:
        """注册内置 provider (幂等)"""
        if self._initialized:
            return
        _register_builtin_providers()
        self._initialized = True
        logger.info("游戏中心管理器已初始化")

    def _get_config(self, game_id: str) -> Any:
        """获取指定游戏的 GameConfig 实例"""
        from app.core import Config

        uid = uuid.UUID(game_id)
        return Config.GameConfig[uid]

    def _get_preset(self, config: Any) -> Optional[GamePreset]:
        """从配置中读取 PresetKey 并返回对应预设"""
        preset_key = config.get("Info", "PresetKey")
        if not preset_key:
            return None
        return get_preset(preset_key)

    def _create_provider(self, game_id: str) -> Optional[GameProvider]:
        """为指定游戏创建 provider"""
        config = self._get_config(game_id)
        preset = self._get_preset(config)
        provider_name = config.get("Info", "Provider")
        return create_provider(provider_name, config, preset)

    def _make_progress_cb(self, game_id: str):
        """创建进度回调, 推送 WS 消息"""

        def _cb(event: ProgressEvent) -> None:
            state = self._states.setdefault(game_id, TaskState())
            state.update_from_event(event)
            # 异步推送 WS (fire and forget)
            asyncio.ensure_future(self._send_progress(game_id, event))

        return _cb

    async def _send_progress(self, game_id: str, event: ProgressEvent) -> None:
        """推送进度到前端"""
        from app.core import Config

        await Config.send_websocket_message(
            id=f"game_center/{game_id}",
            type="Update",
            data=event.to_dict(),
        )

    def _get_state(self, game_id: str) -> TaskState:
        return self._states.setdefault(game_id, TaskState())

    # ======================== 公开 API ========================

    async def check(self, game_id: str) -> dict[str, Any]:
        """检查更新 (同步调用, 不启动后台任务)

        Returns:
            dict with local_version, latest_version, needs_update, installed
        """
        provider = self._create_provider(game_id)
        if provider is None:
            return {
                "code": 500,
                "status": "error",
                "message": f"无法创建 provider",
            }

        try:
            installed = await provider.is_installed()
            local_ver = await provider.check_local_version()
            latest = await provider.check_latest()

            # 写缓存
            config = self._get_config(game_id)
            from datetime import datetime

            await config.set("Cache", "LocalVersion", local_ver)
            await config.set("Cache", "LatestVersion", latest.version)
            await config.set("Cache", "NeedsUpdate", latest.needs_update)
            import json

            await config.set(
                "Cache", "LatestInfo", json.dumps(latest.raw, ensure_ascii=False)
            )
            await config.set(
                "Cache", "LastChecked", datetime.now().strftime("%Y-%m-%d %H:%M")
            )

            return {
                "code": 200,
                "status": "ok",
                "local_version": local_ver,
                "latest_version": latest.version,
                "needs_update": latest.needs_update,
                "installed": installed,
            }
        except Exception as e:
            logger.error(f"检查更新失败 [{game_id}]: {e}")
            return {
                "code": 500,
                "status": "error",
                "message": f"{type(e).__name__}: {e}",
            }

    def is_running(self, game_id: str) -> bool:
        """检查是否有运行中的任务"""
        task = self._tasks.get(game_id)
        return task is not None and not task.done()

    async def install(self, game_id: str) -> dict[str, Any]:
        """启动安装/更新后台任务

        Returns:
            dict with code 200 (已启动) / 409 (冲突) / 500 (错误)
        """
        if self.is_running(game_id):
            return {
                "code": 409,
                "status": "conflict",
                "message": "该游戏已有任务运行中, 请先取消",
            }

        provider = self._create_provider(game_id)
        if provider is None:
            return {
                "code": 500,
                "status": "error",
                "message": "无法创建 provider",
            }

        cancel_event = asyncio.Event()
        self._cancel_events[game_id] = cancel_event
        state = self._get_state(game_id)
        state.running = True
        state.phase = "check"
        state.detail = "准备中..."

        task = asyncio.create_task(
            self._run_install(game_id, provider, cancel_event)
        )
        self._tasks[game_id] = task
        return {"code": 200, "status": "ok", "message": "安装任务已启动"}

    async def _run_install(
        self,
        game_id: str,
        provider: GameProvider,
        cancel_event: asyncio.Event,
    ) -> None:
        """实际执行安装的后台任务"""
        state = self._get_state(game_id)
        cb = self._make_progress_cb(game_id)

        try:
            await provider.install_or_update(cb, cancel_event)
            state.running = False
            state.phase = "done"
            state.detail = "完成"
            cb(ProgressEvent(phase="done", percent=100.0, message="安装完成"))
        except asyncio.CancelledError:
            state.running = False
            state.phase = "cancelled"
            state.detail = "已取消"
            logger.info(f"安装任务已取消: {game_id}")
            cb(ProgressEvent(phase="cancelled", percent=0.0, message="已取消"))
        except Exception as e:
            state.running = False
            state.phase = "error"
            state.detail = str(e)
            logger.error(f"安装任务失败 [{game_id}]: {e}")
            cb(ProgressEvent(phase="error", percent=0.0, message=str(e)))
        finally:
            self._tasks.pop(game_id, None)
            self._cancel_events.pop(game_id, None)

    async def cancel(self, game_id: str) -> dict[str, Any]:
        """取消运行中的任务"""
        event = self._cancel_events.get(game_id)
        if event:
            event.set()
            return {"code": 200, "status": "ok", "message": "取消信号已发送"}

        task = self._tasks.get(game_id)
        if task and not task.done():
            task.cancel()
            return {"code": 200, "status": "ok", "message": "任务已取消"}

        return {"code": 200, "status": "ok", "message": "无运行中的任务"}

    async def launch(self, game_id: str) -> dict[str, Any]:
        """启动游戏"""
        provider = self._create_provider(game_id)
        if provider is None:
            return {"code": 500, "status": "error", "message": "无法创建 provider"}

        try:
            await provider.launch()
            return {"code": 200, "status": "ok", "message": "已启动"}
        except Exception as e:
            logger.error(f"启动失败 [{game_id}]: {e}")
            return {
                "code": 500,
                "status": "error",
                "message": f"{type(e).__name__}: {e}",
            }

    async def close(self, game_id: str) -> dict[str, Any]:
        """关闭游戏"""
        if self.is_running(game_id):
            return {
                "code": 409,
                "status": "conflict",
                "message": "该游戏有安装任务运行中, 请先取消",
            }

        provider = self._create_provider(game_id)
        if provider is None:
            return {"code": 500, "status": "error", "message": "无法创建 provider"}

        try:
            await provider.close()
            return {"code": 200, "status": "ok", "message": "已关闭"}
        except Exception as e:
            logger.error(f"关闭失败 [{game_id}]: {e}")
            return {
                "code": 500,
                "status": "error",
                "message": f"{type(e).__name__}: {e}",
            }

    async def open_official_launcher(self, game_id: str) -> dict[str, Any]:
        """打开官方启动器 (鹰角回退路径)"""
        provider = self._create_provider(game_id)
        if provider is None:
            return {"code": 500, "status": "error", "message": "无法创建 provider"}

        try:
            # 只有 hypergryph provider 有此方法
            if hasattr(provider, "open_official_launcher"):
                provider.open_official_launcher()  # sync method
                return {"code": 200, "status": "ok", "message": "已打开官方启动器"}
            return {
                "code": 400,
                "status": "error",
                "message": "该游戏不支持打开官方启动器",
            }
        except Exception as e:
            logger.error(f"打开官方启动器失败 [{game_id}]: {e}")
            return {
                "code": 500,
                "status": "error",
                "message": f"{type(e).__name__}: {e}",
            }

    async def install_local_apk(
        self, game_id: str, apk_path: str
    ) -> dict[str, Any]:
        """手动安装本地 APK (ADB provider)"""
        provider = self._create_provider(game_id)
        if provider is None:
            return {"code": 500, "status": "error", "message": "无法创建 provider"}

        try:
            if hasattr(provider, "install_local_apk"):
                await provider.install_local_apk(apk_path)
                return {"code": 200, "status": "ok", "message": "APK 安装完成"}
            return {
                "code": 400,
                "status": "error",
                "message": "该游戏不支持手动安装 APK",
            }
        except Exception as e:
            logger.error(f"本地 APK 安装失败 [{game_id}]: {e}")
            return {
                "code": 500,
                "status": "error",
                "message": f"{type(e).__name__}: {e}",
            }

    def task_status(self, game_id: str) -> dict[str, Any]:
        """获取任务状态"""
        state = self._get_state(game_id)
        return {"code": 200, "status": "ok", **state.to_dict()}

    async def cleanup(self) -> None:
        """清理所有运行中的任务 (应用退出时调用)"""
        logger.info("游戏中心: 正在清理所有任务...")

        # 发送取消信号
        for game_id, event in self._cancel_events.items():
            event.set()

        # 取消所有 task
        for game_id, task in list(self._tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass

        self._tasks.clear()
        self._cancel_events.clear()
        logger.info("游戏中心: 清理完成")


# 全局单例
game_center_manager = GameCenterManager()
