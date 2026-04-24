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


import json
import asyncio
import win32gui
from contextlib import suppress
from maa.context import Context
from maa.controller import MaaWin32ScreencapMethodEnum, MaaWin32InputMethodEnum
from maa.custom_recognition import CustomRecognition


from app.core import Config, MaaFWManager
from app.utils import get_logger

logger = get_logger("终末地PC工具")


@MaaFWManager.resource.custom_recognition("CheckForm")
class CheckForm(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg):
        hwnd = win32gui.FindWindow("Qt5158QWindowToolSaveBits", "Form")
        return (
            CustomRecognition.AnalyzeResult(box=(0, 0, 0, 0), detail={"hwnd": hwnd})
            if hwnd
            else None
        )


@MaaFWManager.resource.custom_recognition("CheckComboxBox")
class CheckComboxBox(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg):
        hwnd = win32gui.FindWindow("Qt5158QWindowToolSaveBits", "Endfield")
        return (
            CustomRecognition.AnalyzeResult(box=(0, 0, 0, 0), detail={"hwnd": hwnd})
            if hwnd
            else None
        )


@MaaFWManager.resource.custom_recognition("CheckAccount")
class CheckAccount(CustomRecognition):
    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg):

        try:
            id = json.loads(argv.custom_recognition_param)["id"]
        except Exception:
            return None

        pipeline_override = {
            "仅检查账号[EndFieldPC]": {"recognition": {"param": {"expected": [id]}}}
        }

        # 获取登录框的控制器
        try:
            hwnd = win32gui.FindWindow("Qt5158QWindowToolSaveBits", "Form")
            tasker = asyncio.run_coroutine_threadsafe(
                MaaFWManager.get_win32_tasker(
                    hwnd=hwnd,
                    screencap_method=MaaWin32ScreencapMethodEnum.PrintWindow,
                    mouse_method=MaaWin32InputMethodEnum.PostMessageWithCursorPos,
                    keyboard_method=MaaWin32InputMethodEnum.PostMessageWithCursorPos,
                ),
                Config.loop,
            ).result()
        except Exception:
            return None

        # 验证目标账号是否已登录
        try:
            asyncio.run_coroutine_threadsafe(
                MaaFWManager.do_job(
                    tasker.post_task("切换账号-检查账号[EndFieldPC]", pipeline_override)
                ),
                Config.loop,
            ).result()
            return CustomRecognition.AnalyzeResult(box=(0, 0, 0, 0), detail={"id": id})
        except Exception:
            return None
        except asyncio.CancelledError:
            with suppress(Exception):
                asyncio.run_coroutine_threadsafe(
                    MaaFWManager.do_job(tasker.post_stop()), Config.loop
                ).result()
            raise
