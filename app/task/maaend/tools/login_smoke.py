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


import argparse
import asyncio
import sys
from pathlib import Path

import win32gui

# 允许直接运行该脚本时仍能导入 app 包。
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.task.maaend.tools.login import login


def _find_window_handle(window_keyword: str) -> int | None:
    hwnd = win32gui.FindWindow(None, window_keyword)
    if hwnd:
        return hwnd

    matched: list[int] = []

    def _enum_cb(handle: int, _param):
        if not win32gui.IsWindowVisible(handle):
            return
        title = (win32gui.GetWindowText(handle) or "").strip()
        if window_keyword.lower() in title.lower():
            matched.append(handle)

    win32gui.EnumWindows(_enum_cb, None)
    return matched[0] if matched else None


async def _wait_and_focus_window(
    window_keyword: str, timeout_seconds: float, interval_seconds: float
) -> bool:
    checks = max(1, int(timeout_seconds / interval_seconds))
    for _ in range(checks):
        hwnd = _find_window_handle(window_keyword)
        if hwnd:
            try:
                # 9 = SW_RESTORE
                win32gui.ShowWindow(hwnd, 9)
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            return True
        await asyncio.sleep(interval_seconds)
    return False


async def _main_async(args: argparse.Namespace) -> int:
    # 独立运行时，MaaFWManager 仍依赖 Config.loop。
    from app.core import Config

    Config.loop = asyncio.get_running_loop()

    if args.wait_window:
        ready = await _wait_and_focus_window(
            args.window_keyword, args.window_timeout, args.window_interval
        )
        if not ready:
            print(
                f"[login_smoke] 未检测到目标窗口: keyword='{args.window_keyword}', timeout={args.window_timeout}s"
            )
            return 2

    ok = await login(args.account, args.password)
    print(f"[login_smoke] 登录结果: {'成功' if ok else '失败'}")
    return 0 if ok else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="最小化 MaaEnd 登录验证，不进入完整 AUTO-MAS 流程。"
    )
    parser.add_argument("--account", required=True, help="登录账号。")
    parser.add_argument("--password", required=True, help="登录密码。")
    parser.add_argument(
        "--wait-window",
        action="store_true",
        help="调用登录前先等待游戏窗口出现。",
    )
    parser.add_argument(
        "--window-keyword",
        default="Endfield",
        help="启用 --wait-window 时使用的窗口标题关键字。",
    )
    parser.add_argument(
        "--window-timeout",
        type=float,
        default=45.0,
        help="等待窗口的超时时间，单位秒。",
    )
    parser.add_argument(
        "--window-interval",
        type=float,
        default=0.5,
        help="轮询窗口的间隔时间，单位秒。",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())
