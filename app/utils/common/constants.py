#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 ClozyA
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


import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC4 = timezone(timedelta(hours=4))
"""东4区时区对象"""

UTC8 = timezone(timedelta(hours=8))
"""东8区时区对象"""

TYPE_BOOK = {
    "MaaConfig": "MAA",
    "SrcConfig": "SRC",
    "MaaEndConfig": "MaaEnd",
    "GeneralConfig": "通用",
    "OkwwConfig": "ok-ww",
    "OkNteConfig": "OK-NTE",
    "M9AConfig": "M9A",
    "M9AUserConfig": "M9A",
    "MaaFWConfig": "MFW",
    "HSRConfig": "HSR",
    "BetterGIConfig": "BetterGI",
    "ZzzOdConfig": "ZZZ-OD",
    "BAAHConfig": "BAAH",
    "WhimboxConfig": "奇想盒",
    "MSSConfig": "MSS",
}
"""配置类型映射表"""

PLAN_CONSUMER_VALUES = ("maa", "maaend", "baah", "mss")
"""计划表消费方列表；PLAN_BOOK 按下标引用此项，往中间插入会把已有类型指到别的
消费方，所以新消费方只能追加到末尾（baah 早于 mss 加入，因此排在它前面）"""


EMULATOR_PATH_BOOK = {
    "mumu": {
        "name": "MuMu模拟器",
        "executables": ["MuMuManager.exe", "MuMuPlayer.exe"],
        # DisplayName 子串匹配；避免裸 "MuMu" 以防误匹配 MuMuPlugin 等。
        "registry_display_keywords": [
            "MuMu Player",
            "MuMuPlayer",
            "Netease MuMu",
            "MuMu模拟器",
            "YXArkNights",
            "YXReverse1999",
        ],
        "registry_paths": [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ],
    },
    "ldplayer": {
        "name": "雷电模拟器",
        "executables": ["ldconsole.exe", "LDPlayer.exe", "dnplayer.exe"],
        # 关键词用完整产品名/英文，避免单字「雷电」误匹配。
        "registry_display_keywords": [
            "LDPlayer",
            "雷电模拟器",
            "leidian",
            "XuanZhi LDPlayer",
        ],
        "registry_paths": [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ],
    },
    "nox": {
        "name": "夜神模拟器",
        # executables[0] 为多开管理器；卸载项常见旁路为 Nox.exe（同 bin 目录）
        "executables": ["MultiPlayerManager.exe", "Nox.exe", "NoxVMHandle.exe"],
        "registry_display_keywords": [
            "NoxPlayer",
            "Nox APP Player",
            "BigNox",
        ],
        "registry_paths": [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ],
    },
    "memu": {
        "name": "逍遥模拟器",
        "executables": ["MEmuConsole.exe", "MEmu.exe", "MemuManager.exe"],
        "registry_display_keywords": [
            "MEmu",
            "Microvirt",
            "逍遥",
            "逍遥模拟器",
        ],
        "registry_paths": [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ],
    },
    "bluestacks": {
        "name": "BlueStacks",
        # executables[0] 为多开管理器；卸载项/快捷方式常见旁路为 HD-Player.exe
        "executables": [
            "HD-MultiInstanceManager.exe",
            "HD-Player.exe",
            "BlueStacks.exe",
        ],
        "registry_display_keywords": [
            "BlueStacks",
            "BlueStacks_nxt",
            "BlueStacks X",
        ],
        "registry_paths": [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ],
    },
}
"""模拟器文件常规路径信息"""


TIME_FIELDS = {
    "%Y": "year",
    "%m": "month",
    "%d": "day",
    "%H": "hour",
    "%M": "minute",
    "%S": "second",
    "%f": "microsecond",
}
"""时间字段映射表"""

RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}
"""Windows保留名称列表"""

ILLEGAL_CHARS = set('<>:"/\\|?*')
"""文件名非法字符集合"""

KEYBOARD_KEYS = frozenset(
    [
        "\t",
        "\n",
        "\r",
        " ",
        "!",
        '"',
        "#",
        "$",
        "%",
        "&",
        "'",
        "(",
        ")",
        "*",
        "+",
        ",",
        "-",
        ".",
        "/",
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        ":",
        ";",
        "<",
        "=",
        ">",
        "?",
        "@",
        "[",
        "\\",
        "]",
        "^",
        "_",
        "`",
        "a",
        "b",
        "c",
        "d",
        "e",
        "f",
        "g",
        "h",
        "i",
        "j",
        "k",
        "l",
        "m",
        "n",
        "o",
        "p",
        "q",
        "r",
        "s",
        "t",
        "u",
        "v",
        "w",
        "x",
        "y",
        "z",
        "{",
        "|",
        "}",
        "~",
        "accept",
        "add",
        "alt",
        "altleft",
        "altright",
        "apps",
        "backspace",
        "browserback",
        "browserfavorites",
        "browserforward",
        "browserhome",
        "browserrefresh",
        "browsersearch",
        "browserstop",
        "capslock",
        "clear",
        "convert",
        "ctrl",
        "ctrlleft",
        "ctrlright",
        "decimal",
        "del",
        "delete",
        "divide",
        "down",
        "end",
        "enter",
        "esc",
        "escape",
        "execute",
        "f1",
        "f10",
        "f11",
        "f12",
        "f13",
        "f14",
        "f15",
        "f16",
        "f17",
        "f18",
        "f19",
        "f2",
        "f20",
        "f21",
        "f22",
        "f23",
        "f24",
        "f3",
        "f4",
        "f5",
        "f6",
        "f7",
        "f8",
        "f9",
        "final",
        "fn",
        "hanguel",
        "hangul",
        "hanja",
        "help",
        "home",
        "insert",
        "junja",
        "kana",
        "kanji",
        "launchapp1",
        "launchapp2",
        "launchmail",
        "launchmediaselect",
        "left",
        "modechange",
        "multiply",
        "nexttrack",
        "nonconvert",
        "num0",
        "num1",
        "num2",
        "num3",
        "num4",
        "num5",
        "num6",
        "num7",
        "num8",
        "num9",
        "numlock",
        "pagedown",
        "pageup",
        "pause",
        "pgdn",
        "pgup",
        "playpause",
        "prevtrack",
        "print",
        "printscreen",
        "prntscrn",
        "prtsc",
        "prtscr",
        "return",
        "right",
        "scrolllock",
        "select",
        "separator",
        "shift",
        "shiftleft",
        "shiftright",
        "sleep",
        "space",
        "stop",
        "subtract",
        "tab",
        "up",
        "volumedown",
        "volumemute",
        "volumeup",
        "win",
        "winleft",
        "winright",
        "yen",
        "command",
        "option",
        "optionleft",
        "optionright",
    ]
)
"""键盘按键名称集合 (与 pyautogui.KEYBOARD_KEYS 一致, 内联以避免启动时导入 pyautogui)"""

MIRROR_ERROR_INFO = {
    1001: "获取版本信息的URL参数不正确",
    7001: "填入的 CDK 已过期",
    7002: "填入的 CDK 错误",
    7003: "填入的 CDK 今日下载次数已达上限",
    7004: "填入的 CDK 类型和待下载的资源不匹配",
    7005: "填入的 CDK 已被封禁",
    8001: "对应架构和系统下的资源不存在",
    8002: "错误的系统参数",
    8003: "错误的架构参数",
    8004: "错误的更新通道参数",
    1: "未知错误类型",
}
"""MirrorChyan错误代码映射表"""

DEFAULT_DATETIME = datetime.strptime("2000-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
"""默认日期时间"""


SKLAND_SM_CONFIG = {
    "organization": "UWXspnCCJN4sfYlNfqps",
    "appId": "default",
    "publicKey": "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCmxMNr7n8ZeT0tE1R9j/mPixoinPkeM+k4VGIn/s0k7N5rJAfnZ0eMER+QhwFvshzo0LNmeUkpR8uIlU/GEVr8mN28sKmwd2gpygqj0ePnBmOW4v0ZVwbSYK+izkhVFk2V/doLoMbWy6b+UnA8mkjvg0iYWRByfRsK2gdl7llqCwIDAQAB",
    "protocol": "https",
    "apiHost": "fp-it.portal101.cn",
    "apiPath": "/deviceprofile/v4",
}
"""数美科技配置"""

BROWSER_ENV = {
    "plugins": "MicrosoftEdgePDFPluginPortableDocumentFormatinternal-pdf-viewer1,MicrosoftEdgePDFViewermhjfbmdgcfjbbpaeojofohoefgiehjai1",
    "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "canvas": "259ffe69",  # 基于浏览器的canvas获得的值
    "timezone": -480,  # 时区
    "platform": "Win32",
    "url": "https://www.skland.com/",  # 固定值
    "referer": "",
    "res": "1920_1080_24_1.25",  # 屏幕宽度_高度_色深_window.devicePixelRatio
    "clientSize": "0_0_1080_1920_1920_1080_1920_1080",
    "status": "0011",  # 不知道在干啥
}
"""浏览器环境模拟"""

DES_RULE = {
    "appId": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "uy7mzc4h",
        "obfuscated_name": "xx",
    },
    "box": {
        "is_encrypt": 0,
        "obfuscated_name": "jf",
    },
    "canvas": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "snrn887t",
        "obfuscated_name": "yk",
    },
    "clientSize": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "cpmjjgsu",
        "obfuscated_name": "zx",
    },
    "organization": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "78moqjfc",
        "obfuscated_name": "dp",
    },
    "os": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "je6vk6t4",
        "obfuscated_name": "pj",
    },
    "platform": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "pakxhcd2",
        "obfuscated_name": "gm",
    },
    "plugins": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "v51m3pzl",
        "obfuscated_name": "kq",
    },
    "pmf": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "2mdeslu3",
        "obfuscated_name": "vw",
    },
    "protocol": {
        "is_encrypt": 0,
        "obfuscated_name": "protocol",
    },
    "referer": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "y7bmrjlc",
        "obfuscated_name": "ab",
    },
    "res": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "whxqm2a7",
        "obfuscated_name": "hf",
    },
    "rtype": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "x8o2h2bl",
        "obfuscated_name": "lo",
    },
    "sdkver": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "9q3dcxp2",
        "obfuscated_name": "sc",
    },
    "status": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "2jbrxxw4",
        "obfuscated_name": "an",
    },
    "subVersion": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "eo3i2puh",
        "obfuscated_name": "ns",
    },
    "svm": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "fzj3kaeh",
        "obfuscated_name": "qr",
    },
    "time": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "q2t3odsk",
        "obfuscated_name": "nb",
    },
    "timezone": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "1uv05lj5",
        "obfuscated_name": "as",
    },
    "tn": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "x9nzj1bp",
        "obfuscated_name": "py",
    },
    "trees": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "acfs0xo4",
        "obfuscated_name": "pi",
    },
    "ua": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "k92crp1t",
        "obfuscated_name": "bj",
    },
    "url": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "y95hjkoo",
        "obfuscated_name": "cf",
    },
    "version": {
        "is_encrypt": 0,
        "obfuscated_name": "version",
    },
    "vpw": {
        "cipher": "DES",
        "is_encrypt": 1,
        "key": "r9924ab5",
        "obfuscated_name": "ca",
    },
}
"""DES加密规则"""


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
"""匹配ANSI控制字符的正则表达式"""

TASK_MODE_ZH = {
    "AutoProxy": "自动代理",
    "ScriptConfig": "脚本配置",
}
"""任务模式中文映射表"""

APPDATA_PATH = Path(os.getenv("APPDATA") or "")
"""APPDATA路径"""

FORBIDDEN_PATH_PREFIXES: tuple[Path, ...] = tuple(
    Path(env_value).resolve()
    for key in ("SystemRoot",)
    for env_value in [os.environ.get(key, r"C:\Windows")]
    if env_value and Path(env_value).is_dir()
)
"""禁止作为配置路径的前缀目录（自身、子目录或父目录均非法，如系统目录；校验时另含当前工作目录）"""

FORBIDDEN_PATH_EXACT: tuple[Path, ...] = tuple(
    Path(env_value).resolve()
    for key in ("ProgramFiles", "ProgramFiles(x86)")
    for env_value in [os.environ.get(key, "")]
    if env_value and Path(env_value).is_dir()
)
"""禁止精确匹配的目录根（仅根目录非法，子目录如软件配置路径仍允许）"""

EMULATOR_SPLASH_ADS_PATH_BOOK = {
    "mumu": [
        APPDATA_PATH / "Netease/MuMuPlayer-12.0/data/startupImage",
        APPDATA_PATH / "Netease/MuMuPlayer/data/startupImage",
    ],
    "ldplayer": [APPDATA_PATH / "leidian9/cache"],
}
"""模拟器启动时广告路径"""

CYCLE_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
"""循环队列时间字段的持久化格式"""

CYCLE_EMPTY_TIME = "2000-01-01 00:00:00"
"""循环队列时间字段的空值哨兵，表示「尚未推算」而非某个真实时刻"""

BASE_SHARED = "shared"
"""base 来源：脚本级共享配置（旧字面量「脚本」/「简洁」）"""

BASE_INDEPENDENT = "independent"
"""base 来源：用户独立配置（旧字面量「用户」/「详细」/「自定义」）"""

BASE_NATIVE = "native"
"""base 来源：脚本原生配置（旧字面量「直控」）"""

LEGACY_BASE_SOURCES = {
    "脚本": BASE_SHARED,
    "用户": BASE_INDEPENDENT,
    "直控": BASE_NATIVE,
    "简洁": BASE_SHARED,
    "详细": BASE_INDEPENDENT,
    "自定义": BASE_INDEPENDENT,
}
"""旧配置来源字面量 → base 来源：只出现在存量数据与旧备份里，读取时归一"""


def normalize_base_source(value: object) -> str:
    """把配置来源值归一为 base 来源三态（shared / independent / native）。

    无法识别的值原样返回，由调用方决定是否回落；空值返回空串。
    """

    text = str(value or "").strip()
    return LEGACY_BASE_SOURCES.get(text, text)


BASE_SOURCE_LABELS = {
    BASE_SHARED: "共享",
    BASE_INDEPENDENT: "独立",
    BASE_NATIVE: "原生",
}
"""base 来源三态的展示词表（后端预览等无前端 i18n 处使用）"""
