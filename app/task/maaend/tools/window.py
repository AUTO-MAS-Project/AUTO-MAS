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

WINDOW_READY_TIMEOUT_SECONDS = 45


async def wait_and_focus_window(window_title: str) -> bool:
    deadline = asyncio.get_running_loop().time() + WINDOW_READY_TIMEOUT_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        hwnd = win32gui.FindWindow(None, window_title)
        if hwnd:
            try:
                win32gui.ShowWindow(hwnd, 9)
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            return True
        await asyncio.sleep(0.5)
    return False
