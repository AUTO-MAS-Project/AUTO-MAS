"""显示器容量判据的纯逻辑回归

Win32 桌面游戏任务要回答的问题是「桌面上有没有一块屏放得下目标窗口」。判据必须
按 DPI 换算非客户区：150% 缩放下标题栏约 48px、100% 下约 31px，写死余量在高 DPI
显示器上必然误判。

这里只测纯几何判据，不碰真实窗口。
"""

import pytest

from app.utils.platform import IS_WINDOWS

pytestmark = pytest.mark.skipif(not IS_WINDOWS, reason="显示器查询仅 Windows 实现")


def _monitor(width: int, height: int, dpi: int = 96, taskbar: int = 0):
    from app.utils.platform.display import MonitorInfo

    return MonitorInfo(
        device="\\\\.\\DISPLAYTEST",
        handle=0,
        bounds=(0, 0, width, height),
        work=(0, 0, width, height - taskbar),
        dpi=dpi,
        primary=True,
    )


def test_frame_is_larger_than_client_and_grows_with_dpi() -> None:
    """外框必须比客户区大，且高 DPI 下的非客户区更厚。"""

    from app.utils.platform.display import frame_size_for_client

    width_96, height_96 = frame_size_for_client(1280, 720, 96)
    width_144, height_144 = frame_size_for_client(1280, 720, 144)

    assert width_96 > 1280 and height_96 > 720
    assert height_144 > height_96, "150% 缩放下标题栏更高，换算必须跟着变"


def test_exactly_sized_screen_cannot_host_because_of_titlebar() -> None:
    """屏幕正好等于目标客户区时放不下——非客户区还要占地方。

    这正是写死余量或直接拿分辨率比大小会判错的那一档。
    """

    from app.utils.platform.display import can_host_client

    assert not can_host_client(_monitor(1280, 720), 1280, 720)
    assert can_host_client(_monitor(1920, 1080), 1280, 720)


def test_taskbar_is_excluded_from_usable_area() -> None:
    """判据看的是工作区，不是整块屏；任务栏占掉的高度不能算进去。"""

    from app.utils.platform.display import can_host_client, frame_size_for_client

    _, frame_height = frame_size_for_client(1280, 720, 96)
    # 屏高刚好只比外框多 10px，任务栏一占就不够了。
    screen_height = frame_height + 10
    assert can_host_client(_monitor(1920, screen_height), 1280, 720)
    assert not can_host_client(_monitor(1920, screen_height, taskbar=40), 1280, 720)


def test_headless_fallback_resolution_cannot_host_720p_window() -> None:
    """很小的安全分辨率放不下 1280x720 窗口。

    这是无输出**冷启动**时 Windows 起来的样子（运行中断开输出并不会改分辨率，
    只会留下一块保持原分辨率的幻影屏）。桌面被压小 -> 游戏窗口跟着变小 ->
    脚本侧的分辨率闸门把整轮任务打掉。

    注意这只是插屏之后的次要尺寸校验；触发是否插屏的主判据是「有没有真实显示输出」，
    见 tests/core/test_desktop_guard.py。
    """

    from app.utils.platform.display import can_host_client

    assert not can_host_client(_monitor(1024, 768), 1280, 720)


def test_ultrawide_virtual_display_can_host_even_though_not_16_9() -> None:
    """屏幕不需要是 16:9，够大就行。

    16:9 是对游戏窗口客户区的要求（Win32 controller 截的就是客户区），不是对
    屏幕的要求。UU远程那种 2796x1290 的虚拟屏放得下 1280x720 窗口。
    """

    from app.utils.platform.display import can_host_client

    assert can_host_client(_monitor(2796, 1290), 1280, 720)
