#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

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


import asyncio
import win32gui
from contextlib import suppress
from maa.controller import MaaWin32ScreencapMethodEnum, MaaWin32InputMethodEnum


from app.models.emulator import DeviceInfo, DeviceStatus

from app.utils import get_logger

logger = get_logger("终末地登录")


async def login(
    id: str, password: str, emulator_info: DeviceInfo | None = None
) -> bool:
    """
    登录终末地, 模拟器相关暂时为实现

    Args:
        id(str): 账号ID
        password(str): 账号密码
        emulator_info(DeviceInfo | None): 模拟器信息

    Returns:
        bool: 登录是否成功
    """

    if emulator_info is None:

        logger.info(f"开始登录: 终末地PC端")

        from app.core import Config, MaaFWManager

        pipeline_override = {
            "输入账号[EndFieldPC]": {"action": {"param": {"input_text": id}}},
            "输入密码[EndFieldPC]": {"action": {"param": {"input_text": password}}},
        }

        try:
            hwnd = win32gui.FindWindow(None, "Endfield")
            tasker = await MaaFWManager.get_win32_tasker(
                hwnd=hwnd,
                screencap_method=MaaWin32ScreencapMethodEnum.PrintWindow,
                mouse_method=MaaWin32InputMethodEnum.PostMessageWithCursorPos,
                keyboard_method=MaaWin32InputMethodEnum.PostMessageWithCursorPos,
            )
        except Exception as e:
            logger.error(f"获取终末地的 win32 控制器时出现异常: {e}")
            return False

        try:
            await MaaFWManager.do_job(
                tasker.post_task("切换账号-调出登录框[EndFieldPC]", pipeline_override)
            )
        except Exception as e:
            logger.error(f"终末地调出登录框时出现异常: {e}")
            return False
        except asyncio.CancelledError:
            with suppress(Exception):
                await MaaFWManager.do_job(tasker.post_stop())
            raise

        try:
            hwnd = win32gui.FindWindow(None, "Form")
            tasker = await MaaFWManager.get_win32_tasker(
                hwnd=hwnd,
                screencap_method=MaaWin32ScreencapMethodEnum.PrintWindow,
                mouse_method=MaaWin32InputMethodEnum.PostMessageWithCursorPos,
                keyboard_method=MaaWin32InputMethodEnum.PostMessageWithCursorPos,
            )
        except Exception as e:
            logger.error(f"获取终末地登录表单的 win32 控制器时出现异常: {e}")
            return False

        try:
            await MaaFWManager.do_job(
                tasker.post_task("切换账号-账号登录[EndFieldPC]", pipeline_override)
            )
            logger.success(f"终末地登录成功")
            del tasker
            await asyncio.sleep(10)  # 等待资源释放
            return True
        except Exception as e:
            errorMsg = str(e)
            if id:
                errorMsg = errorMsg.replace(id, "id***")
            if password:
                errorMsg = errorMsg.replace(password, "password***")
            logger.error(f"终末地切换账号时出现异常: {errorMsg}")
            del tasker
            return False
        except asyncio.CancelledError:
            with suppress(Exception):
                await MaaFWManager.do_job(tasker.post_stop())
                del tasker
            raise

    return False
