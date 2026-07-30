#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


#   Contact: DLmaster_361@163.com


import os
import sys
import time
import ctypes
import psutil
import asyncio
import win32gui
import pyautogui
import pygetwindow
from pynput import keyboard

from maa.tasker import Tasker
from maa.context import Context
from maa.controller import (
    MaaWin32ScreencapMethodEnum,
    MaaWin32InputMethodEnum,
)
from maa.custom_action import CustomAction


from app.core import Config, MaaFWManager
from app.utils import get_logger, busy_wait

logger = get_logger("明日方舟PC工具")


class _ArknightWin32Toolkit:

    def __init__(self):

        self.arknights_hwnd = -1
        self.arknights_window = None

        self.tasker = Tasker()
        self.listener = keyboard.Listener()

        Config.ToolsConfig.arknights_pc_get_connected = self.get_connect_status
        Config.ToolsConfig.bind("ArknightsPC", "Enabled", self.on_enabled_change)

        self.p = psutil.Process(os.getpid())
        self.original_nice = self.p.nice()

    async def init(self) -> None:

        pyautogui.PAUSE = 0
        pyautogui.FAILSAFE = False

        await self.on_enabled_change(Config.ToolsConfig.get("ArknightsPC", "Enabled"))

    async def on_enabled_change(self, enabled: bool) -> None:
        """启用状态改变回调"""

        Config.ToolsConfig.arknights_pc_running = False

        if enabled:
            # 提高进程优先级，启用1ms定时器精度
            self.p.nice(psutil.HIGH_PRIORITY_CLASS)
            if sys.platform == "win32":
                ctypes.windll.winmm.timeBeginPeriod(1)

            # 启动键盘监听
            self.arknights_hwnd = -1
            self.listener.stop()
            self.listener = keyboard.Listener(on_release=self.on_key_release)
            self.listener.start()
            logger.success("已启用明日方舟PC工具")
        else:
            # 恢复进程优先级，恢复定时器精度
            self.p.nice(self.original_nice)
            if sys.platform == "win32":
                ctypes.windll.winmm.timeEndPeriod(1)

            # 停止键盘监听
            self.listener.stop()
            logger.success("已禁用明日方舟PC工具")

    async def scheduled_task(self) -> None:
        """定时任务"""

        new_hwnd = win32gui.FindWindow(None, "明日方舟")

        if self.arknights_hwnd != new_hwnd:

            self.arknights_hwnd = new_hwnd

            if new_hwnd == 0:
                logger.warning("未检测到明日方舟窗口，暂停任务器")
                if self.tasker.inited:
                    await MaaFWManager.do_job(self.tasker.post_stop())

            else:
                await self.connect_arknights()

        if not self.get_connect_status() and self.arknights_hwnd > 0:
            await self.connect_arknights()

    def get_connect_status(self) -> bool:
        """获取连接状态"""

        if self.arknights_hwnd <= 0:
            return False
        if not self.arknights_window:
            return False
        if not self.tasker.inited:
            return False
        if not self.tasker.controller.connected:
            return False
        return True

    async def connect_arknights(self) -> None:
        """连接明日方舟"""

        if self.get_connect_status():
            logger.info("已连接到明日方舟，无需重复连接")
            return

        try:
            logger.info("正在连接明日方舟")
            self.arknights_window = pygetwindow.getWindowsWithTitle("明日方舟")
            await MaaFWManager.reconnect_win32_tasker(
                self.tasker,
                self.arknights_hwnd,
                screencap_method=MaaWin32ScreencapMethodEnum.FramePool,
                mouse_method=MaaWin32InputMethodEnum.Seize,
                keyboard_method=MaaWin32InputMethodEnum.Seize,
            )
            logger.success("已连接到明日方舟")
        except Exception as e:
            logger.error(f"连接明日方舟失败: {e}")
            await Config.send_websocket_message(
                id="ArknightsPCToolkit",
                type="Info",
                data={"error": f"无法连接明日方舟: {str(e)}"},
            )

    def on_key_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        """pynput 回调"""

        if isinstance(key, keyboard.KeyCode):
            k = key.char.lower() if key.char else key.vk
        elif isinstance(key, keyboard.Key):
            k = key.name.lower()
        else:
            return

        if k == Config.ToolsConfig.get("ArknightsPC", "PauseKey"):
            logger.info("触发暂停键位")
            Config.ToolsConfig.arknights_pc_running = (
                not Config.ToolsConfig.arknights_pc_running
            )
            if Config.ToolsConfig.arknights_pc_running:
                logger.info("已恢复")
            else:
                logger.info("已暂停")
            return

        if not Config.ToolsConfig.arknights_pc_running:
            return

        if k in Config.ToolsConfig.arknights_pc_keys and not self.get_connect_status():
            logger.warning("未连接到明日方舟客户端，按键操作无效")
            return

        if k == Config.ToolsConfig.get("ArknightsPC", "SelectDeployedKey"):
            logger.info("触发选中已部署干员")
            self.tasker.post_task("选中已部署干员[ArknightsPC]")
        elif k == Config.ToolsConfig.get("ArknightsPC", "UseSkillKey"):
            logger.info("触发释放技能")
            self.tasker.post_task("释放技能[ArknightsPC]")
        elif k == Config.ToolsConfig.get("ArknightsPC", "RetreatKey"):
            logger.info("触发撤退干员")
            self.tasker.post_task("撤退干员[ArknightsPC]")
        elif k == Config.ToolsConfig.get("ArknightsPC", "NextFrameKey"):
            logger.info("触发下一帧")
            self.tasker.post_task("下一帧[ArknightsPC]")
        elif k == Config.ToolsConfig.get("ArknightsPC", "AnotherQuitKey"):
            logger.info("触发退出/暂停额外键位")
            asyncio.run_coroutine_threadsafe(self.click_pause_button(), Config.loop)

    async def click_pause_button(self) -> None:
        cur_x, cur_y = pyautogui.position()
        x, y = self.get_pause_position()

        pyautogui.click(x, y)
        busy_wait(17)
        pyautogui.moveTo(cur_x, cur_y)

    def get_pause_position(self):

        if not self.arknights_window:
            raise RuntimeError("未连接到明日方舟窗口")

        else:
            win = self.arknights_window[0]  # 取第一个匹配窗口

            # 确保窗口存在且可见
            if win.isMinimized:
                win.restore()
            if not win.isActive:
                win.activate()

            return int(win.left + 1200 / 1280 * win.width), int(
                win.top + 50 / 720 * win.height
            )


ArknightWin32Toolkit = _ArknightWin32Toolkit()


@MaaFWManager.resource.custom_action("PlaySelectDeployed[ArknightsPC]")
class PlaySelectDeployed(CustomAction):

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:

        logger.info("开始执行战斗时选中已部署干员动作")

        try:
            cur_x, cur_y = pyautogui.position()
            x, y = ArknightWin32Toolkit.get_pause_position()

            pyautogui.click()
            busy_wait(17)
            pyautogui.click(x, y)
            busy_wait(17)
            pyautogui.moveTo(cur_x, cur_y)

        except Exception as e:
            logger.exception(f"执行战斗时选中已部署干员动作时出错: {e}")
            return False

        logger.success("成功执行战斗时选中已部署干员动作")
        return True


@MaaFWManager.resource.custom_action("PauseSelectDeployed[ArknightsPC]")
class PauseSelectDeployed(CustomAction):

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:

        logger.info("开始执行暂停时选中已部署干员动作")

        try:
            cur_x, cur_y = pyautogui.position()
            x, y = ArknightWin32Toolkit.get_pause_position()

            pyautogui.click(x, y)
            busy_wait(17)
            pyautogui.click(cur_x, cur_y)
            busy_wait(17)
            pyautogui.click(x, y)
            busy_wait(17)
            pyautogui.moveTo(cur_x, cur_y)

        except Exception as e:
            logger.exception(f"执行暂停时选中已部署干员动作时出错: {e}")
            return False

        logger.success("成功执行暂停时选中已部署干员动作")
        return True


@MaaFWManager.resource.custom_action("PlaySkill[ArknightsPC]")
class PlaySkill(CustomAction):

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:

        logger.info("开始执行战斗时释放技能动作")
        try:
            x, y = ArknightWin32Toolkit.get_pause_position()

            pyautogui.click()
            busy_wait(17)
            pyautogui.click(x, y)
            time.sleep(0.2)

        except Exception as e:
            logger.exception(f"执行战斗时释放技能动作时出错: {e}")
            return False

        logger.success("成功执行战斗时释放技能动作")
        return True


@MaaFWManager.resource.custom_action("PauseSkill[ArknightsPC]")
class PauseSkill(CustomAction):

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:

        logger.info("开始执行暂停时释放技能动作")

        try:
            cur_x, cur_y = pyautogui.position()
            x, y = ArknightWin32Toolkit.get_pause_position()

            pyautogui.click(x, y)
            busy_wait(17)
            pyautogui.click(cur_x, cur_y)
            busy_wait(17)
            pyautogui.click(x, y)
            time.sleep(0.2)

        except Exception as e:
            logger.exception(f"执行暂停时释放技能动作时出错: {e}")
            return False

        logger.success("成功执行暂停时释放技能动作")
        return True


@MaaFWManager.resource.custom_action("PlayRetreat[ArknightsPC]")
class PlayRetreat(CustomAction):

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:

        logger.info("开始执行战斗时撤退干员动作")

        try:
            x, y = ArknightWin32Toolkit.get_pause_position()

            pyautogui.click()
            busy_wait(17)
            pyautogui.click(x, y)
            time.sleep(0.2)

        except Exception as e:
            logger.exception(f"执行战斗时撤退干员动作时出错: {e}")
            return False

        logger.success("成功执行战斗时撤退干员动作")
        return True


@MaaFWManager.resource.custom_action("PauseRetreat[ArknightsPC]")
class PauseRetreat(CustomAction):

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:

        logger.info("开始执行暂停时撤退干员动作")

        try:
            cur_x, cur_y = pyautogui.position()
            x, y = ArknightWin32Toolkit.get_pause_position()

            pyautogui.click(x, y)
            busy_wait(17)
            pyautogui.click(cur_x, cur_y)
            busy_wait(17)
            pyautogui.click(x, y)
            time.sleep(0.2)

        except Exception as e:
            logger.exception(f"执行暂停时撤退干员动作时出错: {e}")
            return False

        logger.success("成功执行暂停时撤退干员动作")
        return True


@MaaFWManager.resource.custom_action("NextFrame-0.2x[ArknightsPC]")
class NextFrame_0_2x(CustomAction):

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:

        logger.info("开始执行0.2倍速下一帧动作")

        try:
            cur_x, cur_y = pyautogui.position()
            x, y = ArknightWin32Toolkit.get_pause_position()

            pyautogui.click(x, y)
            busy_wait(165)
            pyautogui.click(x, y)
            busy_wait(17)
            pyautogui.moveTo(cur_x, cur_y)

        except Exception as e:
            logger.exception(f"执行0.2倍速下一帧动作时出错: {e}")
            return False

        logger.success("成功执行0.2倍速下一帧动作")
        return True


@MaaFWManager.resource.custom_action("NextFrame-1x[ArknightsPC]")
class NextFrame_1x(CustomAction):

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:

        logger.info("开始执行1倍速下一帧动作")

        try:
            cur_x, cur_y = pyautogui.position()
            x, y = ArknightWin32Toolkit.get_pause_position()

            pyautogui.click(x, y)
            busy_wait(32)
            pyautogui.click(x, y)
            busy_wait(17)
            pyautogui.moveTo(cur_x, cur_y)

        except Exception as e:
            logger.exception(f"执行1倍速下一帧动作时出错: {e}")
            return False

        logger.success("成功执行1倍速下一帧动作")
        return True


@MaaFWManager.resource.custom_action("NextFrame-2x[ArknightsPC]")
class NextFrame_2x(CustomAction):

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:

        logger.info("开始执行2倍速下一帧动作")

        try:
            cur_x, cur_y = pyautogui.position()
            x, y = ArknightWin32Toolkit.get_pause_position()

            pyautogui.click(x, y)
            busy_wait(17)
            pyautogui.click(x, y)
            busy_wait(17)
            pyautogui.moveTo(cur_x, cur_y)

        except Exception as e:
            logger.exception(f"执行2倍速下一帧动作时出错: {e}")
            return False

        logger.success("成功执行2倍速下一帧动作")
        return True
