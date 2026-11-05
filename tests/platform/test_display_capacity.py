"""显示器容量判据的纯逻辑回归

Win32 桌面游戏任务要回答的问题是「桌面上有没有一块屏放得下目标窗口」。判据必须
按 DPI 换算非客户区：150% 缩放下标题栏约 48px、100% 下约 31px，写死余量在高 DPI
显示器上必然误判。

这里只测纯几何判据，不碰真实窗口。
"""

import pytest

from app.utils import IS_WINDOWS

pytestmark = pytest.mark.skipif(not IS_WINDOWS, reason="显示器查询仅 Windows 实现")


def _monitor(width: int, height: int, dpi: int = 96, taskbar: int = 0):
    from app.utils import display as _utils_display

    return _utils_display.MonitorInfo(
        device="\\\\.\\DISPLAYTEST",
        handle=0,
        bounds=(0, 0, width, height),
        work=(0, 0, width, height - taskbar),
        dpi=dpi,
        primary=True,
    )


def test_exactly_sized_screen_cannot_host_because_of_titlebar() -> None:
    """屏幕正好等于目标客户区时放不下——非客户区还要占地方。

    这正是写死余量或直接拿分辨率比大小会判错的那一档。
    """

    from app.utils import display as _utils_display

    assert not _utils_display.can_host_client(_monitor(1280, 720), 1280, 720)
    assert _utils_display.can_host_client(_monitor(1920, 1080), 1280, 720)


def test_taskbar_is_excluded_from_usable_area() -> None:
    """判据看的是工作区，不是整块屏；任务栏占掉的高度不能算进去。"""

    from app.utils import display as _utils_display

    _, frame_height = _utils_display.frame_size_for_client(1280, 720, 96)
    # 屏高刚好只比外框多 10px，任务栏一占就不够了。
    screen_height = frame_height + 10
    assert _utils_display.can_host_client(_monitor(1920, screen_height), 1280, 720)
    assert not _utils_display.can_host_client(
        _monitor(1920, screen_height, taskbar=40), 1280, 720
    )
