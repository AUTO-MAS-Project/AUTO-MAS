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

"""游戏中心 Provider 抽象基类

所有 provider (miHoYo / 鹰角 / ADB APK) 继承 GameProvider,
实现版本检查、安装/更新、启动等核心逻辑。
"""

from __future__ import annotations

import abc
import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import psutil

from app.utils import get_logger

logger = get_logger("游戏中心")


@dataclass
class ProgressEvent:
    """单次操作进度事件, 通过 WebSocket 推送到前端

    phase 取值:
      check     - 版本检查中
      download  - 下载中
      verify    - 校验中
      patch     - 打补丁中
      install   - 安装中
      done      - 完成
      cancelled - 已取消
      error     - 出错
    """

    phase: str = "check"
    percent: float = 0.0
    downloaded: int = 0
    total: int = 0
    speed: float = 0.0
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "percent": self.percent,
            "downloaded": self.downloaded,
            "total": self.total,
            "speed": self.speed,
            "message": self.message,
        }


@dataclass
class LatestInfo:
    """版本检查结果"""

    version: str = ""
    needs_update: bool = False
    size: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


class GameProvider(abc.ABC):
    """游戏 provider 抽象基类

    每个 provider 实例绑定一个 GameConfig 实例 (通过 set_config 注入)。
    生命周期: create_provider(cfg) -> check -> install_or_update / launch
    """

    def __init__(self) -> None:
        self._config: Any = None
        self._preset: Any = None

    def set_config(self, config: Any, preset: Any = None) -> None:
        """注入 GameConfig 实例和预设参数"""
        self._config = config
        self._preset = preset

    @property
    def config(self) -> Any:
        if self._config is None:
            raise RuntimeError("Provider 未绑定 config, 请先调用 set_config()")
        return self._config

    @property
    def preset(self) -> Any:
        return self._preset

    @abc.abstractmethod
    async def is_installed(self) -> bool:
        """判断游戏是否已安装(目录存在 / APK 已装)"""
        ...

    @abc.abstractmethod
    async def check_local_version(self) -> str:
        """返回本地已安装版本号, 未安装时返回空串"""
        ...

    @abc.abstractmethod
    async def check_latest(self) -> LatestInfo:
        """查询最新版本, 返回 LatestInfo"""
        ...

    @abc.abstractmethod
    async def install_or_update(
        self,
        progress_cb: Callable[[ProgressEvent], Any],
        cancel_event: asyncio.Event,
    ) -> None:
        """执行安装/更新, 通过 progress_cb 回调进度, cancel_event 取消"""
        ...

    @abc.abstractmethod
    async def launch(self) -> None:
        """启动游戏"""
        ...

    @abc.abstractmethod
    async def close(self) -> None:
        """关闭游戏"""
        ...


def kill_processes_under(directory: Path) -> int:
    """结束可执行文件位于指定目录下的所有进程 (PC 游戏关闭用)

    参考 app/utils/emulator/mumu.py 的 psutil 清理模式,
    按 exe 路径前缀匹配, 连带结束游戏拉起的子进程。

    Args:
        directory: 游戏目录

    Returns:
        结束的进程数
    """
    root = str(directory.resolve()).lower().rstrip("\\/") + os.sep
    killed = 0
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            exe = proc.info.get("exe") or ""
            if not exe or not str(Path(exe).resolve()).lower().startswith(root):
                continue
            proc.kill()
            killed += 1
            logger.info(f"已结束游戏进程: {proc.info.get('name')} (PID {proc.info.get('pid')})")
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as e:
            logger.warning(f"结束游戏进程失败: {e}")
    return killed
