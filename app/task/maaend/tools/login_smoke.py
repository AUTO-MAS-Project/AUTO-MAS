import argparse
import asyncio
import sys
from pathlib import Path

import win32gui

# Ensure "app" package is importable when running this file directly.
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
    # MaaFWManager relies on Config.loop in standalone runs.
    from app.core import Config

    Config.loop = asyncio.get_running_loop()

    if args.wait_window:
        ready = await _wait_and_focus_window(
            args.window_keyword, args.window_timeout, args.window_interval
        )
        if not ready:
            print(
                f"[login_smoke] window not ready: keyword='{args.window_keyword}', timeout={args.window_timeout}s"
            )
            return 2

    ok = await login(args.account, args.password)
    print(f"[login_smoke] login result: {'success' if ok else 'failed'}")
    return 0 if ok else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Minimal MaaEnd login smoke test without entering full MAS flow."
    )
    parser.add_argument("--account", required=True, help="Account ID for login.")
    parser.add_argument("--password", required=True, help="Account password for login.")
    parser.add_argument(
        "--wait-window",
        action="store_true",
        help="Wait for game window before calling login.",
    )
    parser.add_argument(
        "--window-keyword",
        default="Endfield",
        help="Window title keyword used when --wait-window is enabled.",
    )
    parser.add_argument(
        "--window-timeout",
        type=float,
        default=45.0,
        help="Window wait timeout seconds.",
    )
    parser.add_argument(
        "--window-interval",
        type=float,
        default=0.5,
        help="Window polling interval seconds.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    sys.exit(main())
