"""设备任务会话的公共借用接口。"""

from app.task.game import current_emulator, game_device_id, game_target_id

__all__ = ["game_target_id", "game_device_id", "current_emulator"]
