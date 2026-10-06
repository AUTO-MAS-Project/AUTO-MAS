"""明日方舟 / MAA 插件侧常量。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

UTC4 = timezone(timedelta(hours=4))

UTC8 = timezone(timedelta(hours=8))
"""东8区时区对象"""

MAA_RUN_MOOD_BOOK = {
    "GreenTicketStore": "绿票商店",
    "Annihilation": "剿灭",
    "Routine": "日常",
}
"""MAA运行模式映射表"""

MAA_MODE_TIME_LIMIT_BOOK = {
    "GreenTicketStore": "RoutineTimeLimit",
    "Annihilation": "AnnihilationTimeLimit",
    "Routine": "RoutineTimeLimit",
}
"""MAA运行模式对应的超时配置项：绿票商店只买一次商店，复用日常时限"""

MAA_TASKS = [
    "StartUp",
    "DepotMaintain",
    "Fight",
    "Infrast",
    "Recruit",
    "Mall",
    "Award",
    "Roguelike",
    "SwitchTheme",
]
"""MAA任务列表"""

MAA_TASKS_ZH = [
    "开始唤醒",
    "库存保持",
    "理智作战",
    "基建换班",
    "自动公招",
    "信用收支",
    "领取奖励",
    "自动肉鸽",
    "更换主题",
]
"""MAA任务列表"""

MAA_DEPOT_EXCLUDED_ITEM_IDS = {
    "3213",
    "3223",
    "3233",
    "3243",
    "3253",
    "3263",
    "3273",
    "3283",
    "7001",
    "7002",
    "7003",
    "7004",
    "4004",
    "4005",
    "3105",
    "3131",
    "3132",
    "3133",
    "6001",
    "3141",
    "4002",
    "32001",
    "30115",
    "30125",
    "30135",
    "30145",
    "30155",
    "30165",
    # 无对应可刷关卡：家具零件（基建产出）、合成玉（源石兑换）、声望（战斗经验）
    "3401",
    "4003",
    "5001",
}
"""MAA 库存保持不可刷取物品 ID"""

MAA_STAGE_KEY = [
    "MedicineNumb",
    "SeriesNumb",
    "Stage",
    "Stage_1",
    "Stage_2",
    "Stage_3",
    "Stage_Remain",
]
"""MAA关卡键表"""

ARKNIGHTS_PACKAGE_NAME = {
    "Official": "com.hypergryph.arknights",
    "Bilibili": "com.hypergryph.arknights.bilibili",
    "YoStarEN": "com.YoStarEN.Arknights",
    "YoStarJP": "com.YoStarJP.Arknights",
    "YoStarKR": "com.YoStarKR.Arknights",
    "txwy": "tw.txwy.and.arknights",
}
"""明日方舟包名映射表"""

ARKNIGHTS_VERSION_API_SERVER = {
    "Official": "official",
    "Bilibili": "b",
}
"""明日方舟版本接口服务器标识映射表

仅收录已实测可用的服务器；外服与台服未找到稳定的公开版本接口，
不在此表中的服务器会跳过客户端版本检查。
"""

ARKNIGHTS_OFFICIAL_APK_URL = "https://ak.hypergryph.com/downloads/android_lastest"
"""明日方舟官服安卓包下载入口（302 跳转至启动器再跳至 CDN 实际包地址）"""

MAA_TASK_TRANSITION_METHOD_BOOK = {
    "NoAction": "8",
    "ExitGame": "9",
    "ExitEmulator": "9",
}
"""MAA任务切换方式映射表"""

MAA_ANNIHILATION_FIGHT_BASE = {
    "$type": "FightTask",
    "UseMedicine": False,
    "MedicineCount": 0,
    "UseStone": False,
    "StoneCount": 0,
    "EnableTargetDrop": False,
    "DropId": "",
    "DropCount": 0,
    "IsInventoryTarget": False,
    "EnableTimesLimit": False,
    "TimesLimit": 999,
    "Series": 0,
    "StagePlan": ["Annihilation"],
    "IsDrGrandet": False,
    "UseExpiringMedicine": True,
    "UseExpireMedicineForActivity": False,
    "UseCustomAnnihilation": True,
    "AnnihilationStage": "Annihilation",
    "HideUnavailableStage": True,
    "IsStageManually": False,
    "UseOptionalStage": False,
    "UseStoneAllowSave": False,
    "HideSeries": False,
    "UseWeeklySchedule": False,
    "WeeklySchedule": {
        "Sunday": True,
        "Monday": True,
        "Tuesday": True,
        "Wednesday": True,
        "Thursday": True,
        "Friday": True,
        "Saturday": True,
    },
    "Name": "剿灭作战",
    "IsEnable": True,
    "TaskType": "Fight",
}
"""MAA剿灭作战基础配置"""

MAA_GREEN_TICKET_STORE_TASK = {
    "$type": "CustomTask",
    "Name": "绿票商店",
    "IsEnable": True,
    "TaskType": "Custom",
    "CustomTaskName": "GreenTicket@Store@Begin",
}
"""MAA绿票商店任务配置：牛杂「绿票商店」的任务链，需 MAA v6.3.0 及以上"""

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

ARKNIGHTS_GAME_DAY_TZ = {
    "Official": UTC4,
    "Bilibili": UTC4,
    "txwy": UTC4,
    "YoStarEN": timezone(timedelta(hours=-11)),
    "YoStarJP": timezone(timedelta(hours=5)),
    "YoStarKR": timezone(timedelta(hours=5)),
}


def get_game_day_tz(server: str | None) -> timezone:
    """按明日方舟区服取游戏日时区，未知或空区服回落到东4区。"""

    return ARKNIGHTS_GAME_DAY_TZ.get(server or "", UTC4)


def game_now(server: str | None) -> datetime:
    """按明日方舟区服的游戏日时区取当前时间，其日期即当前游戏日。"""

    return datetime.now(tz=get_game_day_tz(server))
