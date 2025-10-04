"""
键盘工具模块

提供虚拟键码到keyboard库按键名称的转换功能，以及相关的键盘操作辅助函数。
"""

import asyncio
import keyboard
from typing import List
from app.utils.logger import get_logger

logger = get_logger("键盘工具")


def vk_code_to_key_name(vk_code: int) -> str:
    """
    将Windows虚拟键码转换为keyboard库识别的按键名称

    Args:
        vk_code (int): Windows虚拟键码

    Returns:
        str: keyboard库识别的按键名称

    Examples:
        >>> vk_code_to_key_name(0x1B)
        'esc'
        >>> vk_code_to_key_name(0x70)
        'f1'
        >>> vk_code_to_key_name(0x41)
        'a'
    """
    # Windows虚拟键码到keyboard库按键名称的映射
    vk_mapping = {
        # 常用功能键
        0x1B: "esc",  # VK_ESCAPE
        0x0D: "enter",  # VK_RETURN
        0x20: "space",  # VK_SPACE
        0x08: "backspace",  # VK_BACK
        0x09: "tab",  # VK_TAB
        0x2E: "delete",  # VK_DELETE
        0x24: "home",  # VK_HOME
        0x23: "end",  # VK_END
        0x21: "page up",  # VK_PRIOR
        0x22: "page down",  # VK_NEXT
        0x2D: "insert",  # VK_INSERT
        # 修饰键
        0x10: "shift",  # VK_SHIFT
        0x11: "ctrl",  # VK_CONTROL
        0x12: "alt",  # VK_MENU
        0x5B: "left windows",  # VK_LWIN
        0x5C: "right windows",  # VK_RWIN
        0x5D: "apps",  # VK_APPS (右键菜单键)
        # 方向键
        0x25: "left",  # VK_LEFT
        0x26: "up",  # VK_UP
        0x27: "right",  # VK_RIGHT
        0x28: "down",  # VK_DOWN
        # 功能键 F1-F12
        0x70: "f1",
        0x71: "f2",
        0x72: "f3",
        0x73: "f4",
        0x74: "f5",
        0x75: "f6",
        0x76: "f7",
        0x77: "f8",
        0x78: "f9",
        0x79: "f10",
        0x7A: "f11",
        0x7B: "f12",
        # 数字键 0-9
        0x30: "0",
        0x31: "1",
        0x32: "2",
        0x33: "3",
        0x34: "4",
        0x35: "5",
        0x36: "6",
        0x37: "7",
        0x38: "8",
        0x39: "9",
        # 字母键 A-Z
        0x41: "a",
        0x42: "b",
        0x43: "c",
        0x44: "d",
        0x45: "e",
        0x46: "f",
        0x47: "g",
        0x48: "h",
        0x49: "i",
        0x4A: "j",
        0x4B: "k",
        0x4C: "l",
        0x4D: "m",
        0x4E: "n",
        0x4F: "o",
        0x50: "p",
        0x51: "q",
        0x52: "r",
        0x53: "s",
        0x54: "t",
        0x55: "u",
        0x56: "v",
        0x57: "w",
        0x58: "x",
        0x59: "y",
        0x5A: "z",
        # 数字小键盘
        0x60: "num 0",
        0x61: "num 1",
        0x62: "num 2",
        0x63: "num 3",
        0x64: "num 4",
        0x65: "num 5",
        0x66: "num 6",
        0x67: "num 7",
        0x68: "num 8",
        0x69: "num 9",
        0x6A: "num *",
        0x6B: "num +",
        0x6D: "num -",
        0x6E: "num .",
        0x6F: "num /",
        0x90: "num lock",
        # 标点符号和特殊键
        0xBA: ";",  # VK_OEM_1 (;:)
        0xBB: "=",  # VK_OEM_PLUS (=+)
        0xBC: ",",  # VK_OEM_COMMA (,<)
        0xBD: "-",  # VK_OEM_MINUS (-_)
        0xBE: ".",  # VK_OEM_PERIOD (.>)
        0xBF: "/",  # VK_OEM_2 (/?)
        0xC0: "`",  # VK_OEM_3 (`~)
        0xDB: "[",  # VK_OEM_4 ([{)
        0xDC: "\\",  # VK_OEM_5 (\|)
        0xDD: "]",  # VK_OEM_6 (]})
        0xDE: "'",  # VK_OEM_7 ('")
        # 系统键
        0x14: "caps lock",  # VK_CAPITAL
        0x91: "scroll lock",  # VK_SCROLL
        0x13: "pause",  # VK_PAUSE
        0x2C: "print screen",  # VK_SNAPSHOT
        # 媒体键
        0xA0: "left shift",  # VK_LSHIFT
        0xA1: "right shift",  # VK_RSHIFT
        0xA2: "left ctrl",  # VK_LCONTROL
        0xA3: "right ctrl",  # VK_RCONTROL
        0xA4: "left alt",  # VK_LMENU
        0xA5: "right alt",  # VK_RMENU
    }

    return vk_mapping.get(vk_code, f"vk_{vk_code}")


def vk_codes_to_key_names(vk_codes: List[int]) -> List[str]:
    """
    将多个虚拟键码转换为keyboard库识别的按键名称列表

    Args:
        vk_codes (List[int]): Windows虚拟键码列表

    Returns:
        List[str]: keyboard库识别的按键名称列表

    Examples:
        >>> vk_codes_to_key_names([0x11, 0x12, 0x44])
        ['ctrl', 'alt', 'd']
    """
    return [vk_code_to_key_name(vk) for vk in vk_codes]


async def send_key_combination(key_names: List[str], hold_time: float = 0.05) -> bool:
    """
    发送按键组合

    Args:
        key_names (List[str]): 按键名称列表
        hold_time (float): 按键保持时间（秒），默认 0.05 秒

    Returns:
        bool: 操作是否成功

    Examples:
        >>> await send_key_combination(['ctrl', 'alt', 'd'])
        True
        >>> await send_key_combination(['f1'])
        True
    """
    try:
        if not key_names:
            logger.warning("按键名称列表为空")
            return False

        if len(key_names) == 1:
            # 单个按键
            keyboard.press_and_release(key_names[0])
            logger.debug(f"发送单个按键: {key_names[0]}")
        else:
            # 组合键：按下所有键，然后释放
            logger.debug(f"发送组合键: {'+'.join(key_names)}")
            for key in key_names:
                keyboard.press(key)
            await asyncio.sleep(hold_time)  # 保持按键状态
            for key in reversed(key_names):
                keyboard.release(key)

        return True

    except Exception as e:
        logger.error(f"发送按键组合失败: {e}")
        return False


async def send_vk_combination(vk_codes: List[int], hold_time: float = 0.05) -> bool:
    """
    发送虚拟键码组合

    Args:
        vk_codes (List[int]): Windows虚拟键码列表
        hold_time (float): 按键保持时间（秒），默认 0.05 秒

    Returns:
        bool: 操作是否成功

    Examples:
        >>> await send_vk_combination([0x11, 0x12, 0x44])  # Ctrl+Alt+D
        True
        >>> await send_vk_combination([0x70])  # F1
        True
    """
    try:
        key_names = vk_codes_to_key_names(vk_codes)
        return await send_key_combination(key_names, hold_time)
    except Exception as e:
        logger.error(f"发送虚拟键码组合失败: {e}")
        return False


def get_common_boss_keys() -> dict[str, List[int]]:
    """
    获取常见的BOSS键组合

    Returns:
        dict[str, List[int]]: 常见BOSS键组合的名称和对应的虚拟键码
    """
    return {
        "alt_tab": [0x12, 0x09],  # Alt+Tab
        "ctrl_alt_d": [0x11, 0x12, 0x44],  # Ctrl+Alt+D
        "win_d": [0x5B, 0x44],  # Win+D (显示桌面)
        "win_m": [0x5B, 0x4D],  # Win+M (最小化所有窗口)
        "f1": [0x70],  # F1
        "f2": [0x71],  # F2
        "f3": [0x72],  # F3
        "f4": [0x73],  # F4
        "alt_f4": [0x12, 0x73],  # Alt+F4 (关闭窗口)
        "ctrl_shift_esc": [0x11, 0x10, 0x1B],  # Ctrl+Shift+Esc (任务管理器)
    }


def describe_vk_combination(vk_codes: List[int]) -> str:
    """
    描述虚拟键码组合

    Args:
        vk_codes (List[int]): Windows虚拟键码列表

    Returns:
        str: 组合键的描述字符串

    Examples:
        >>> describe_vk_combination([0x11, 0x12, 0x44])
        'Ctrl+Alt+D'
        >>> describe_vk_combination([0x70])
        'F1'
    """
    key_names = vk_codes_to_key_names(vk_codes)
    return "+".join(name.title() for name in key_names)
