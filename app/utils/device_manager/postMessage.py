import ctypes
import asyncio

# 加载 user32.dll
user32 = ctypes.windll.user32

# Windows 消息常量
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101


async def post_key_to_hwnd(hwnd: int, vk_code: int) -> bool:
    """
    使用 PostMessage 向指定窗口句柄发送一个完整的按键（按下 + 释放）。
    !由于 PostMessage 是异步的，并不能保证按键一定被处理。

    参数:
        hwnd (int): 目标窗口句柄
        vk_code (int): 虚拟键码

    注意:
        - 此函数不检查 hwnd 是否有效，也不等待消息处理（异步）。
        - 如果 hwnd 无效，PostMessage 会静默失败。
    """
    if hwnd <= 0:
        raise ValueError("hwnd 必须是正整数")
    if not (0 <= vk_code <= 0xFFFF):
        raise ValueError("vk_code 必须是有效的虚拟键码（0~65535）")

    user32.PostMessageW(hwnd, WM_KEYDOWN, vk_code, 0)
    user32.PostMessageW(hwnd, WM_KEYUP, vk_code, 0)
    return True


async def send_key_to_hwnd_sync(hwnd: int, vk_code: int) -> bool:
    """
    使用 SendMessage 向指定窗口句柄同步发送一个完整的按键（按下 + 释放）。

    参数:
        hwnd (int): 目标窗口句柄
        vk_code (int): 虚拟键码

    返回:
        bool:
            - 对于 SendMessage，返回值是目标窗口过程（WindowProc）对消息的返回值。
            - 通常非零表示成功，但具体含义由目标窗口定义。
            - 如果 hwnd 无效，会返回 0。

    注意:
        - 此调用是**同步阻塞**的：当前线程会等待目标窗口处理完消息才返回。
        - 如果目标窗口无响应（hung），当前程序也会卡住！
    """
    if hwnd <= 0:
        raise ValueError("hwnd 必须是正整数")
    if not (0 <= vk_code <= 0xFFFF):
        raise ValueError("vk_code 必须是有效的虚拟键码（0~65535）")

    # 发送 WM_KEYDOWN
    result_down = user32.SendMessageW(hwnd, WM_KEYDOWN, vk_code, 0)
    # 发送 WM_KEYUP
    result_up = user32.SendMessageW(hwnd, WM_KEYUP, vk_code, 0)

    return bool(result_down and result_up)


async def post_keys_to_hwnd(
    hwnd: int, vk_codes: list[int], hold_time: float = 0.05
) -> bool:
    """
    使用 PostMessage 向指定窗口句柄同时发送多个按键
    !由于 PostMessage 是异步的，并不能保证按键一定被处理。

    参数:
        hwnd (int): 目标窗口句柄
        vk_codes (List[int]): 虚拟键码列表
        hold_time (float): 按键保持时间（秒），默认 0.05 秒

    返回:
        bool: 总是返回 True（PostMessage 不提供错误反馈）

    注意:
        - 此函数不检查 hwnd 是否有效，也不等待消息处理（异步）。
        - 如果 hwnd 无效，PostMessage 会静默失败。
        - 按键顺序：先按下所有键，等待，然后按相反顺序释放所有键。
    """
    if hwnd <= 0:
        raise ValueError("hwnd 必须是正整数")
    if not vk_codes:
        raise ValueError("vk_codes 不能为空")

    # 验证所有虚拟键码
    for vk_code in vk_codes:
        if not (0 <= vk_code <= 0xFFFF):
            raise ValueError(f"vk_code {vk_code} 必须是有效的虚拟键码（0~65535）")

    # 按下所有按键
    for vk_code in vk_codes:
        user32.PostMessageW(hwnd, WM_KEYDOWN, vk_code, 0)

    # 保持按键状态
    await asyncio.sleep(hold_time)

    # 按相反顺序释放所有按键（模拟真实按键行为）
    for vk_code in reversed(vk_codes):
        user32.PostMessageW(hwnd, WM_KEYUP, vk_code, 0)

    return True


async def post_keys_to_hwnd_sync(
    hwnd: int, vk_codes: list[int], hold_time: float = 0.05
) -> bool:
    """
    使用 SendMessage 向指定窗口句柄同步发送多个按键
    先按下所有按键，等待指定时间，然后释放所有按键。

    参数:
        hwnd (int): 目标窗口句柄
        vk_codes (List[int]): 虚拟键码列表
        hold_time (float): 按键保持时间（秒），默认 0.05 秒

    返回:
        bool: 如果所有消息都成功发送则返回 True

    注意:
        - 此调用是**同步阻塞**的：当前线程会等待目标窗口处理完每个消息才继续。
        - 如果目标窗口无响应（hung），当前程序也会卡住！
        - 按键顺序：先按下所有键，等待，然后按相反顺序释放所有键。
    """
    if hwnd <= 0:
        raise ValueError("hwnd 必须是正整数")
    if not vk_codes:
        raise ValueError("vk_codes 不能为空")

    # 验证所有虚拟键码
    for vk_code in vk_codes:
        if not (0 <= vk_code <= 0xFFFF):
            raise ValueError(f"vk_code {vk_code} 必须是有效的虚拟键码（0~65535）")

    # 按下所有按键
    down_results = []
    for vk_code in vk_codes:
        result = user32.SendMessageW(hwnd, WM_KEYDOWN, vk_code, 0)
        down_results.append(result)

    # 保持按键状态
    await asyncio.sleep(hold_time)

    # 按相反顺序释放所有按键（模拟真实按键行为）
    up_results = []
    for vk_code in reversed(vk_codes):
        result = user32.SendMessageW(hwnd, WM_KEYUP, vk_code, 0)
        up_results.append(result)

    # 如果所有按键操作都成功，则返回 True
    return all(down_results) and all(up_results)
