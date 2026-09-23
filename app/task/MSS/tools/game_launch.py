#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


"""MSS 桌面端的游戏启停与 Unity 分辨率临时覆盖。

桌面端的外壳是按窗口找游戏的（`interface.json` 里声明了 `window_regex`），所以
MAS 这边只需要保证「游戏在运行」这一件事：

- ``DirectExe``：由本模块启动游戏，并在本轮结束后关闭它；但发现游戏**已经在跑**
  时只接管、不启动也不关闭，免得把用户自己开着的游戏关掉。
- ``AttachOnly``：游戏由别的方式启停，本模块既不启动也不关闭。

Unity 分辨率的临时覆盖只在「本轮由本软件启动」时生效，游戏关闭后恢复原值。MSS
官方只支持 16:9 的客户端，这一项对它的价值比别处大。

分辨率覆盖复用 MaaFW 的实现：那是纯注册表工具、不读宿主配置，复制一份只会让
两边各自漂移。日后它若上提到共享位置，这里跟着改导入路径即可。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.task.MaaFW.tools.embedded.game_resolution import (
    UnityGameResolutionOverride,
    parse_resolution_option,
)
from app.task.proxy_helpers import split_args
from app.utils import ProcessInfo, ProcessManager, get_logger, is_process_running

logger = get_logger("MSS 游戏")

__all__ = ["MSSGameSession"]


class MSSGameSession:
    """一次运行期间的游戏生命周期。"""

    def __init__(self, script_config: Any) -> None:
        """按脚本级配置初始化会话。

        Args:
            script_config: ``MSSConfig``，只读它的 ``Game`` 段。
        """

        self.launch_mode = str(script_config.get("Game", "LaunchMode") or "DirectExe")
        self.launch_path = str(script_config.get("Game", "LaunchPath") or "").strip()
        self.arguments = split_args(script_config.get("Game", "Arguments"))
        self.wait_time = int(script_config.get("Game", "WaitTime") or 0)
        self.resolution = parse_resolution_option(
            script_config.get("Game", "UnityResolution")
        )

        self.process_manager: ProcessManager | None = None
        ## 只有本轮由本软件启动的游戏才由本软件关闭；接管来的不碰
        self.opened_game = False
        self._resolution_override: UnityGameResolutionOverride | None = None

    async def ensure_running(self) -> None:
        """确保游戏可用。

        Raises:
            RuntimeError: 启动方式要求本软件启动游戏，但路径没填或不存在。
        """

        if self.launch_mode != "DirectExe":
            logger.info("启动方式为「只接管已运行的游戏」，本软件不启动游戏")
            return

        if not self.launch_path:
            raise RuntimeError("启动方式为「由本软件启动游戏」，但没有填写游戏路径")

        exe_path = Path(self.launch_path)
        if not exe_path.is_file():
            raise RuntimeError(f"游戏路径不存在: {exe_path}")

        process_name = exe_path.name
        if is_process_running(process_name):
            logger.info(f"游戏已在运行，本轮只接管、不重复启动: {process_name}")
            return

        self._apply_resolution(exe_path)

        logger.info(
            f"启动游戏: {exe_path}"
            + (f" 参数: {' '.join(self.arguments)}" if self.arguments else "")
        )
        self.process_manager = ProcessManager()
        await self.process_manager.open_process(
            exe_path,
            *self.arguments,
            target_process=ProcessInfo(
                name=process_name, exe=str(exe_path), cmdline=None
            ),
        )
        self.opened_game = True

        if self.wait_time > 0:
            logger.info(f"等待游戏窗口就绪（{self.wait_time} 秒）")
            await asyncio.sleep(self.wait_time)

    async def close(self) -> None:
        """本轮收尾：关掉自己启动的游戏，并恢复分辨率。"""

        try:
            if self.opened_game and self.process_manager is not None:
                logger.info("关闭本轮由本软件启动的游戏")
                await self.process_manager.kill()
        except Exception as e:
            logger.opt(exception=True).warning(f"关闭游戏失败: {e}")
        finally:
            self.process_manager = None
            self._restore_resolution()

    def _apply_resolution(self, exe_path: Path) -> None:
        """启动前临时把 Unity 播放器的窗口尺寸改成配置值。

        分辨率只是锦上添花：注册表读不到、写不进去都不该拦住整轮运行。
        """

        if self.resolution is None:
            return

        width, height = self.resolution
        try:
            override = UnityGameResolutionOverride.for_executable(
                exe_path, width, height
            )
            if override is None:
                logger.info("按 exe 反查不到 Unity 注册表信息，跳过分辨率临时覆盖")
                return
            override.apply()
        except Exception as e:
            logger.warning(f"临时改写分辨率失败，按游戏原分辨率继续: {e}")
            return

        self._resolution_override = override
        logger.info(f"已临时把游戏窗口分辨率改为 {override.label}")

    def _restore_resolution(self) -> None:
        """恢复分辨率原值；失败只告警，不影响收尾。"""

        override = self._resolution_override
        self._resolution_override = None
        if override is None:
            return

        try:
            override.restore()
            logger.info("已恢复游戏窗口分辨率")
        except Exception as e:
            logger.opt(exception=True).warning(f"恢复游戏分辨率失败: {e}")
