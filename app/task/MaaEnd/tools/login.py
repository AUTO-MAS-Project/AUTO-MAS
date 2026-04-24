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
from contextlib import suppress

import win32gui
import win32con
from maa.controller import MaaWin32ScreencapMethodEnum, MaaWin32InputMethodEnum

from app.models.emulator import DeviceInfo
from app.utils import get_logger

logger = get_logger("终末地登录")


async def login(
    id: str, password: str, emulator_info: DeviceInfo | None = None
) -> bool:
    """
    登录终末地，模拟器相关暂未实现。

    Args:
        id(str): 账号
        password(str): 账号密码
        emulator_info(DeviceInfo | None): 模拟器信息

    Returns:
        bool: 登录是否成功
    """
    if emulator_info is None:
        logger.info("开始登录: 终末地PC端")

        from app.core import MaaFWManager

        pipeline_override = {
            "输入账号[EndFieldPC]": {"action": {"param": {"input_text": id}}},
            "输入密码[EndFieldPC]": {"action": {"param": {"input_text": password}}},
            "检查账号[EndFieldPC]": {
                "recognition": {
                    "param": {"expected": [f"{id[:3]}[a-zA-Z0-9 *]*{id[-4:]}"]}
                }
            },
            "选中账号[EndFieldPC]": {
                "recognition": {
                    "param": {"expected": [f"{id[:3]}[a-zA-Z0-9 *]*{id[-4:]}"]}
                }
            },
            "验证账号[EndFieldPC]": {
                "recognition": {
                    "param": {
                        "custom_recognition_param": {
                            "id": f"{id[:3]}[a-zA-Z0-9 *]*{id[-4:]}"
                        }
                    }
                }
            },
        }

        # 获取主窗口的控制器
        try:
            hwnd = win32gui.FindWindow("UnityWndClass", "Endfield")
            main_tasker = await MaaFWManager.get_win32_tasker(
                hwnd=hwnd,
                screencap_method=MaaWin32ScreencapMethodEnum.PrintWindow,
                mouse_method=MaaWin32InputMethodEnum.PostMessageWithCursorPos,
                keyboard_method=MaaWin32InputMethodEnum.PostMessageWithCursorPos,
            )
        except Exception as e:
            logger.error(f"获取终末地的 win32 控制器时出现异常: {e}")
            return False

        # 调出终末地登录框
        if win32gui.FindWindow("Qt5158QWindowToolSaveBits", "Form") == 0:
            try:
                await MaaFWManager.do_job(
                    main_tasker.post_task(
                        "切换账号-调出登录框[EndFieldPC]", pipeline_override
                    )
                )
                logger.info("已调出终末地登录框")
            except Exception as e:
                logger.error(f"终末地调出登录框时出现异常: {e}")
                return False
            except asyncio.CancelledError:
                with suppress(Exception):
                    await MaaFWManager.do_job(main_tasker.post_stop())
                raise

        # 获取登录框的控制器
        try:
            hwnd = win32gui.FindWindow("Qt5158QWindowToolSaveBits", "Form")
            form_tasker = await MaaFWManager.get_win32_tasker(
                hwnd=hwnd,
                screencap_method=MaaWin32ScreencapMethodEnum.PrintWindow,
                mouse_method=MaaWin32InputMethodEnum.PostMessageWithCursorPos,
                keyboard_method=MaaWin32InputMethodEnum.PostMessageWithCursorPos,
            )
        except Exception as e:
            logger.error(f"获取终末地登录表单的 win32 控制器时出现异常: {e}")
            return False

        # 验证目标账号是否已登录
        try:
            await MaaFWManager.do_job(
                form_tasker.post_task(
                    "切换账号-验证账号[EndFieldPC]", pipeline_override
                )
            )
            logger.info("当前账号即为目标账号")
            await MaaFWManager.do_job(
                main_tasker.post_task(
                    "账号切换-等待加载完成[EndFieldPC]", pipeline_override
                )
            )
            logger.success("终末地登录成功: 目标账号已登录")
            return True
        except Exception as e:
            logger.info("当前账号不是目标账号")
        except asyncio.CancelledError:
            with suppress(Exception):
                await MaaFWManager.do_job(main_tasker.post_stop())
                await MaaFWManager.do_job(form_tasker.post_stop())
            raise

        # # 通过下拉框切换账号
        # # 展开下拉框
        # try:
        #     await MaaFWManager.do_job(
        #         form_tasker.post_task(
        #             "切换账号-展开下拉框[EndFieldPC]", pipeline_override
        #         )
        #     )
        #     logger.info("已展开登录下拉框")
        # except Exception as e:
        #     logger.error(f"终末地展开下拉框时出现异常: {e}")
        #     return False
        # except asyncio.CancelledError:
        #     with suppress(Exception):
        #         await MaaFWManager.do_job(form_tasker.post_stop())
        #     raise
        # # 获取登录下拉框的控制器
        # try:
        #     hwnd = win32gui.FindWindow("Qt5158QWindowToolSaveBits", "Endfield")
        #     combo_tasker = await MaaFWManager.get_win32_tasker(
        #         hwnd=hwnd,
        #         screencap_method=MaaWin32ScreencapMethodEnum.PrintWindow,
        #         mouse_method=MaaWin32InputMethodEnum.Seize,
        #         keyboard_method=MaaWin32InputMethodEnum.Seize,
        #     )
        # except Exception as e:
        #     logger.error(f"获取终末地登录下拉框的 win32 控制器时出现异常: {e}")
        #     return False
        # # 选择目标账号
        # try:
        #     await MaaFWManager.do_job(
        #         combo_tasker.post_task(
        #             "切换账号-下拉框切换[EndFieldPC]", pipeline_override
        #         )
        #     )
        #     logger.info("已通过下拉框选择中目标账号")
        #     hwnd = win32gui.FindWindow("Qt5158QWindowToolSaveBits", "Endfield")
        #     if hwnd != 0:
        #         win32gui.SendMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        #     logger.info("已收起下拉框")
        #     await MaaFWManager.do_job(
        #         form_tasker.post_task(
        #             "切换账号-验证账号[EndFieldPC]", pipeline_override
        #         )
        #     )
        #     logger.info("已验证切换账号后的账号信息")
        #     await MaaFWManager.do_job(
        #         main_tasker.post_task(
        #             "账号切换-等待加载完成[EndFieldPC]", pipeline_override
        #         )
        #     )
        #     logger.success("终末地登录成功: 通过下拉框切换至目标账号")
        #     return True
        # except Exception as e:
        #     logger.info("未找到目标账号登录记录")
        # except asyncio.CancelledError:
        #     with suppress(Exception):
        #         await MaaFWManager.do_job(main_tasker.post_stop())
        #         await MaaFWManager.do_job(form_tasker.post_stop())
        #         await MaaFWManager.do_job(combo_tasker.post_stop())
        #     raise

        # 通过账号密码登录账号
        if id != "" and "*" not in id and password != "":
            try:
                hwnd = win32gui.FindWindow("Qt5158QWindowToolSaveBits", "Endfield")
                if hwnd != 0:
                    win32gui.SendMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                    logger.info("已收起下拉框")
                await MaaFWManager.do_job(
                    form_tasker.post_task(
                        "切换账号-账号密码切换[EndFieldPC]", pipeline_override
                    )
                )
                logger.info("已通过账号密码登录至目标账号")
                await MaaFWManager.do_job(
                    main_tasker.post_task(
                        "账号切换-等待加载完成[EndFieldPC]", pipeline_override
                    )
                )
                logger.success("终末地登录成功: 通过账号密码登录至目标账号")
                return True
            except Exception as e:
                error_msg = str(e)
                if id:
                    error_msg = error_msg.replace(id, "id***")
                if password:
                    error_msg = error_msg.replace(password, "password***")
                logger.error(f"终末地切换账号时出现异常: {error_msg}")
                return False
            except asyncio.CancelledError:
                with suppress(Exception):
                    await MaaFWManager.do_job(main_tasker.post_stop())
                    await MaaFWManager.do_job(form_tasker.post_stop())
                raise

    return False
