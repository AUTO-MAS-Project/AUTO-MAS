#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""OK-EF 配置文件 Schema 定义。

OK-EF 属于 ok-script 线，配置编辑器直接读写 `working/configs` 下的 JSON。
本模块只负责把现有 JSON 转成 MAS 前端可渲染的字段描述，不启动 OK-EF 原生 UI。
"""

from __future__ import annotations

import gettext
import json
import re
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

from .common.config_schema import (
    CONFIDENCE_DECLARED,
    CONTROL_TEXTAREA,
    SOURCE_PROVIDER,
    FieldChoice,
    FieldDeclaration,
    FieldSchema,
    materialize_field_schemas,
    render_legacy_fields,
)


_PO_ENTRY_RE = re.compile(
    r'^msgid\s+"((?:[^"\\]|\\.)*)"\s*\nmsgstr\s+"((?:[^"\\]|\\.)*)"',
    re.MULTILINE,
)

_SKIP_CONFIG_FILES = {
    "devices.json",
    "main_window.json",
    "template_tab.json",
}

_ACCOUNT_FIELD_NAMES = {"多账户模式", "多账户独立配置", "账号列表"}
_HIDDEN_FIELD_NAMES = {"配置选择", "自动打开汇总文件"}
_MULTILINE_FIELD_NAMES = {"账号列表"}

_TASK_INDEX_MAP: dict[str, int] = {
    "DailyTask.json": 1,
    "TakeDeliveryTask.json": 2,
    "WarehouseTransferTask.json": 3,
    "DeliveryTask.json": 4,
    "BattleTask.json": 5,
    "DemoDrawTask.json": 6,
    "Test.json": 7,
    "YingTuoTask.json": 8,
    "TestStartGame.json": 9,
    "RealtimeDetectTask.json": 10,
    "DiagnosisTask.json": 11,
}

_DISPLAY_NAMES: dict[str, str] = {
    "DailyTask.json": "日常任务",
    "TakeDeliveryTask.json": "运送委托接取",
    "WarehouseTransferTask.json": "仓库物品转移",
    "DeliveryTask.json": "自动送货",
    "BattleTask.json": "刷体力",
    "DemoDrawTask.json": "演算抽牌",
    "Test.json": "蓝点归中测试",
    "YingTuoTask.json": "影拓丰碑",
    "TestStartGame.json": "启动一次游戏",
    "RealtimeDetectTask.json": "YOLO实测扫描",
    "DiagnosisTask.json": "诊断",
    "AutoCombatTask.json": "自动战斗",
    "AutoInteractionTask.json": "自动交互",
    "AutoLoginTask.json": "自动登录",
    "AutoPickTask.json": "自动拾取",
    "ItemNavigatorTask.json": "物品导航",
    "Basic Options.json": "基础选项",
    "Battle Config.json": "战斗配置",
    "Game Hotkey Config.json": "游戏热键",
    "Ensure Main Once Action Sleep.json": "主界面等待",
}

_FALLBACK_LABELS: dict[str, str] = {
    "Yes": "是",
    "No": "否",
    "Auto": "自动",
    "None": "无",
}

_STAGE_OPTIONS = [
    "干员经验",
    "干员进阶",
    "钱币收集",
    "技能提升",
    "武器经验",
    "武器进阶",
    "罗丹",
    "三位一体",
    "白垩界卫",
    "阮一",
    "聂菲斯",
    "D96钢",
    "超距辉映管",
    "快子遴捡晶格",
    "象限拟合液",
    "三相纳米片",
    "枢纽区",
    "源石研究园",
    "试验园区",
    "矿脉源区",
    "供能高地",
    "武陵城",
    "清波寨",
    "首墩",
    "藏剑谷",
]
_REWARD_TIER_OPTIONS = ["保持当前", "低阶", "高阶"]
_TIER_STAGE_OPTIONS = {"干员经验", "干员进阶", "技能提升", "武器进阶"}
_STAGE_SEQUENCE_OPTIONS = [
    item
    for stage in _STAGE_OPTIONS
    for item in (
        [stage, f"{stage}低阶", f"{stage}高阶"]
        if stage in _TIER_STAGE_OPTIONS
        else [stage]
    )
]
_TEAM_OPTIONS = ["不换队伍", "1", "2", "3", "4", "5"]
_CONFIG_PROFILE_OPTIONS = ["隐藏", "⭐⭐⭐ 默认"]
_BOAT_OPTIONS = ["收集线索", "制造舱", "培养舱"]
_ACTIVITY_REWARD_OPTIONS = ["周常奖励", "理智补给"]
_TRADE_GOODS_OPTIONS = [
    "精选荞愈胶囊",
    "高容谷地电池",
    "精选柑实罐头",
    "中容谷地电池",
    "优质荞愈胶囊",
    "优质柑实罐头",
    "荞愈胶囊",
    "柑实罐头",
    "晶体外壳",
    "息壤玉葫芦",
    "息壤葫芦",
    "中容武陵电池",
    "优质芽针针剂",
    "优质锦草软饮",
    "低容武陵电池",
    "芽针针剂",
    "锦草软饮",
    "重息壤",
    "赫铜零件",
]
_DELIVERY_TARGET_TICKET_OPTIONS = ["119000", "79800", "73100"]
_DELIVERY_AREA_OPTIONS = ["武陵"]
_DELIVERY_TEST_TARGET_OPTIONS = [
    "无",
    "通向送货点",
    "通向送货点试验园区",
    "常沄",
    "资源",
    "彦宁",
    "齐纶",
    "于施",
    "苏白易",
    "普里莫",
    "赵昭",
    "裴令容",
    "阿禾",
    "完整循环测试",
]
_DELIVERY_FULL_CYCLE_LOCATION_OPTIONS = ["武陵城", "试验园区"]
_WAREHOUSE_OPTIONS = ["valley4", "wuling"]
_WAREHOUSE_ITEM_OPTIONS = ["蓝铁矿", "高容谷地电池", "源矿", "致密源石粉末"]
_EXTERNAL_COMMAND_TIMING_OPTIONS = ["任务最开始", "任务最后"]
_GIFT_TARGET_OPTIONS = [
    "庄方宜",
    "洛茜",
    "汤汤",
    "管理员",
    "黎风",
    "余烬",
    "洁尔佩塔",
    "艾尔黛拉",
    "骏卫",
    "莱万汀",
    "伊冯",
    "别礼",
    "陈千语",
    "昼雪",
    "赛希",
    "狼卫",
    "佩丽卡",
    "弧光",
    "阿列什",
    "艾维文娜",
    "大潘",
    "埃特拉",
    "卡契尔",
    "安塔尔",
    "萤石",
    "秋栗",
]

_SELECT_OPTIONS: dict[str, dict[str, list[str]]] = {
    "Basic Options.json": {
        "Use DirectML": ["Auto", "Yes", "No"],
        "Start/Stop": ["None", "F9", "F10", "F11", "F12"],
    },
    "DeliveryTask.json": {
        "目标券数": _DELIVERY_TARGET_TICKET_OPTIONS,
        "地区切换": _DELIVERY_AREA_OPTIONS,
        "选择测试对象": _DELIVERY_TEST_TARGET_OPTIONS,
        "完整循环测试区域": _DELIVERY_FULL_CYCLE_LOCATION_OPTIONS,
    },
    "WarehouseTransferTask.json": {
        "发货仓库": _WAREHOUSE_OPTIONS,
        "收货仓库": _WAREHOUSE_OPTIONS,
        "物品": _WAREHOUSE_ITEM_OPTIONS,
    },
    "RealtimeDetectTask.json": {
        "YOLO模型": ["battle_end_default"],
        "检测目标": ["battle_end"],
    },
}

_GLOBAL_SELECT_OPTIONS: dict[str, list[str]] = {
    "体力本": _STAGE_OPTIONS,
    "体力本奖励档位": _REWARD_TIER_OPTIONS,
    "刷本序列": _STAGE_SEQUENCE_OPTIONS,
    "指定的队伍编号": _TEAM_OPTIONS,
    "配置选择": _CONFIG_PROFILE_OPTIONS,
    "交易货品优先序列": _TRADE_GOODS_OPTIONS,
    "帝江号收菜操作": _BOAT_OPTIONS,
    "活动奖励": _ACTIVITY_REWARD_OPTIONS,
    "外部命令执行时机": _EXTERNAL_COMMAND_TIMING_OPTIONS,
    "优先送礼对象": _GIFT_TARGET_OPTIONS,
    "技能释放": ["1", "2", "3"],
    "Use DirectML": ["Auto", "Yes", "No"],
    "Start/Stop": ["None", "F9", "F10", "F11", "F12"],
}

_FIELD_LABELS: dict[str, str] = {
    "Exit After Task": "完成后退出",
    "Auto Start Game When App Starts": "应用启动时自动启动游戏",
    "Minimize Window to System Tray when Closing": "关闭时最小化到系统托盘",
    "Mute Game while in Background": "后台运行时静音游戏",
    "Auto Resize Game Window": "自动调整游戏窗口大小",
    "Exit App when Game Exits": "游戏退出时退出应用",
    "Use DirectML": "使用 DirectML",
    "Trigger Interval": "触发间隔",
    "Start/Stop": "开始/停止快捷键",
    "Kill Launcher After Start": "启动后关闭启动器",
    "Launch with DX11": "使用 DX11 启动",
}

_FIELD_DESCRIPTIONS: dict[str, str] = {
    "多账户模式": "启用后按账号列表执行当前任务，适合脚本自身支持多账号的任务。",
    "多账户独立配置": "启用后每个账号使用独立配置；关闭时多个账号共享当前配置。",
    "账号列表": "每行一个账号，按 OK-EF 原生多账户逻辑依次执行。",
    "⭐买物资": "是否在「地区建设/物资调度/稳定物资需求」中通过调度券购买物资。",
    "购物白名单": "默认留空，表示购买首行首个物资；填写后按白名单顺序购买。",
    "是否买礼物": "是否购买「人文物产」，同样应用购物白名单序列。",
    "⭐刷体力": "是否消耗所有「理智」刷取培养材料。",
    "消耗限时体力药": "优先消耗小时级限时体力药；天级体力药按脚本规则折算消耗。",
    "体力本": "刷取哪个副本。所选副本必须领完所有等级的首通奖励。",
    "体力本奖励档位": "用于干员经验、干员进阶、技能提升、武器进阶的奖励档位选择。",
    "刷体力开始日期": "用于计算今天是第几天，配合刷本序列自动轮换。",
    "刷本序列": "会根据开始日期自动轮换；留空表示不启用自动轮换。",
    "仅站桩": "开始挑战后角色原地不动，仅对重度能量淤积点生效。",
    "体力刷完后继续刷取次数": "结算时点击「放弃」而非「领取」，不消耗体力；0 表示不启用。",
    "是否启用滚动放大视角": "对齐滑索时自动滚动放大视角，可能提高也可能降低对齐成功率。",
    "指定的队伍编号": "选择要更换的队伍编号。",
    "⭐买卖货": "是否启用「地区建设/物资调度/弹性需求物资」交易。",
    "只买不卖": "启用后只进行购买操作，不进行出售操作。",
    "⭐买信用商店": "是否在「采购中心/信用交易所」采购，自动刷新并购买优先商品。",
    "信用商店保留信用": "若剩余信用小于这个数值，则终止采购。",
    "⭐收邮件": "是否前往「邮箱」领取邮件。",
    "⭐据点兑换": "是否在「地区建设/据点管理」中通过交易获得调度券。",
    "交易货品优先序列": "默认留空时交易货品顺序随机；填写后按优先序列兑换。",
    "⭐转交运送委托": "是否在「地区建设/仓储结点」中转交全部运送委托。",
    "⭐转交委托奖励领取": "是否领取「地区建设/仓储结点/我转交的委托」奖励。",
    "⭐造装备": "是否前往装备制造并制作一件列表首位的装备。",
    "⭐简易制作": "是否执行简易制作相关操作。",
    "⭐收信用": "是否前往好友帝江号助力并收取信用。",
    "尝试仅收培育室": "优先尝试仅助力好友帝江号上的培养舱。",
    "⭐帝江号收菜": "是否前往好友帝江号执行线索、制造舱和培养舱操作。",
    "帝江号收菜操作": "勾选要在帝江号收菜时执行的操作。",
    "⭐活动奖励": "是否领取活动中心中的每周事务和理智补给奖励。",
    "活动奖励": "勾选要在活动中心里领取的奖励。",
    "⭐日常奖励": "是否领取行动手册日常和通行证奖励。",
    "⭐送礼": "是否通过帝江号干员联络台赠送礼物提升好感度。",
    "一次送礼个数": "每次送礼时使用的礼物数量。",
    "⭐帝江号一键存放": "是否在帝江号打开背包并点击一键存放。",
    "送礼任务最多尝试次数": "送礼链路失败后的最多重试次数。",
    "优先送礼对象": "选择优先赠送礼物的干员。",
    "⭐演算": "是否执行演武集算任务。",
    "⭐执行外部命令": "是否执行一次外部命令行程序。",
    "外部命令": "需要执行的命令行内容。",
    "外部命令起始于": "可选填写命令工作目录。",
    "外部命令等待退出": "等待外部命令退出，适合需要串行执行的多账户场景。",
    "外部命令已运行时跳过": "外部命令已在运行时跳过本次执行。",
    "外部命令执行时机": "选择外部命令在任务最开始或最后执行。",
    "⭐传送到帝江号右侧传送点": "是否在日常任务中传送到帝江号右侧传送点。",
    "自动打开汇总文件": "任务结束后是否打开 OK-EF 汇总文本。",
    "发生异常时终止游戏": "发生异常时终止游戏和脚本。",
    "仅退出游戏": "完成后只退出游戏，不退出 OK-EF 应用。",
}

_SECTION_ORDER: dict[str, int] = {
    "⭐⭐⭐ 默认": 0,
    "多账户模式": 10,
    "⭐买物资": 20,
    "体力本配置": 30,
    "淤积点相关选项": 40,
    "战斗相关选项": 50,
    "⭐买卖货": 60,
    "⭐买信用商店": 70,
    "⭐据点兑换": 80,
    "⭐收信用": 90,
    "⭐帝江号收菜": 100,
    "⭐活动奖励": 110,
    "⭐送礼": 120,
    "⭐执行外部命令": 130,
    "其他配置": 900,
}

_FILE_GROUPS: dict[str, str] = {
    "DailyTask.json": "日常任务",
    "TakeDeliveryTask.json": "运送委托",
    "DeliveryTask.json": "运送委托",
    "WarehouseTransferTask.json": "仓库与物资",
    "BattleTask.json": "战斗",
    "DemoDrawTask.json": "战斗",
    "YingTuoTask.json": "战斗",
    "Test.json": "工具与调试",
    "TestStartGame.json": "工具与调试",
    "RealtimeDetectTask.json": "工具与调试",
    "DiagnosisTask.json": "工具与调试",
    "AutoCombatTask.json": "实时触发",
    "AutoInteractionTask.json": "实时触发",
    "AutoLoginTask.json": "实时触发",
    "AutoPickTask.json": "实时触发",
    "ItemNavigatorTask.json": "实时触发",
}

_FIELD_SECTIONS: dict[str, str] = {
    "多账户模式": "多账户模式",
    "多账户独立配置": "多账户模式",
    "账号列表": "多账户模式",
    "⭐买物资": "⭐⭐⭐ 默认",
    "购物白名单": "⭐买物资",
    "是否买礼物": "⭐买物资",
    "⭐刷体力": "⭐⭐⭐ 默认",
    "消耗限时体力药": "体力本配置",
    "体力本": "体力本配置",
    "体力本奖励档位": "体力本配置",
    "刷体力开始日期": "体力本配置",
    "刷本序列": "体力本配置",
    "仅站桩": "淤积点相关选项",
    "体力刷完后继续刷取次数": "淤积点相关选项",
    "是否启用滚动放大视角": "淤积点相关选项",
    "枢纽区": "淤积点相关选项",
    "源石研究园": "淤积点相关选项",
    "试验园区": "淤积点相关选项",
    "矿脉源区": "淤积点相关选项",
    "供能高地": "淤积点相关选项",
    "武陵城": "淤积点相关选项",
    "清波寨": "淤积点相关选项",
    "首墩": "淤积点相关选项",
    "藏剑谷": "淤积点相关选项",
    "指定的队伍编号": "战斗相关选项",
    "技能释放": "战斗相关选项",
    "启动技能点数": "战斗相关选项",
    "后台结束战斗通知": "战斗相关选项",
    "无数字操作间隔": "战斗相关选项",
    "进入战斗后的初始等待时间": "战斗相关选项",
    "启用排轴": "战斗相关选项",
    "排轴序列": "战斗相关选项",
    "⭐买卖货": "⭐⭐⭐ 默认",
    "只买不卖": "⭐买卖货",
    "武陵买入价": "⭐买卖货",
    "武陵卖出价": "⭐买卖货",
    "武陵": "⭐买卖货",
    "四号谷地买入价": "⭐买卖货",
    "四号谷地卖出价": "⭐买卖货",
    "四号谷地": "⭐买卖货",
    "⭐买信用商店": "⭐⭐⭐ 默认",
    "信用商店保留信用": "⭐买信用商店",
    "⭐收邮件": "⭐⭐⭐ 默认",
    "⭐据点兑换": "⭐⭐⭐ 默认",
    "交易货品优先序列": "⭐据点兑换",
    "⭐转交运送委托": "⭐⭐⭐ 默认",
    "⭐转交委托奖励领取": "⭐⭐⭐ 默认",
    "⭐造装备": "⭐⭐⭐ 默认",
    "⭐简易制作": "⭐⭐⭐ 默认",
    "⭐收信用": "⭐⭐⭐ 默认",
    "尝试仅收培育室": "⭐收信用",
    "⭐帝江号收菜": "⭐⭐⭐ 默认",
    "帝江号收菜操作": "⭐帝江号收菜",
    "⭐活动奖励": "⭐⭐⭐ 默认",
    "活动奖励": "⭐活动奖励",
    "⭐日常奖励": "⭐⭐⭐ 默认",
    "⭐送礼": "⭐⭐⭐ 默认",
    "一次送礼个数": "⭐送礼",
    "⭐帝江号一键存放": "⭐送礼",
    "送礼任务最多尝试次数": "⭐送礼",
    "优先送礼对象": "⭐送礼",
    "⭐演算": "⭐⭐⭐ 默认",
    "⭐执行外部命令": "⭐⭐⭐ 默认",
    "外部命令": "⭐执行外部命令",
    "外部命令起始于": "⭐执行外部命令",
    "外部命令等待退出": "⭐执行外部命令",
    "外部命令已运行时跳过": "⭐执行外部命令",
    "外部命令执行时机": "⭐执行外部命令",
    "⭐传送到帝江号右侧传送点": "⭐⭐⭐ 默认",
}

_FIELD_PRIORITY: dict[str, int] = {
    name: index
    for index, name in enumerate(
        [
            "多账户模式",
            "多账户独立配置",
            "账号列表",
            "⭐买物资",
            "购物白名单",
            "是否买礼物",
            "⭐刷体力",
            "消耗限时体力药",
            "体力本",
            "体力本奖励档位",
            "刷体力开始日期",
            "刷本序列",
            "仅站桩",
            "体力刷完后继续刷取次数",
            "是否启用滚动放大视角",
            "枢纽区",
            "源石研究园",
            "试验园区",
            "矿脉源区",
            "供能高地",
            "武陵城",
            "清波寨",
            "首墩",
            "藏剑谷",
            "指定的队伍编号",
            "技能释放",
            "启动技能点数",
            "后台结束战斗通知",
            "无数字操作间隔",
            "进入战斗后的初始等待时间",
            "启用排轴",
            "排轴序列",
            "⭐买卖货",
            "只买不卖",
            "武陵买入价",
            "武陵卖出价",
            "武陵",
            "四号谷地买入价",
            "四号谷地卖出价",
            "四号谷地",
            "⭐买信用商店",
            "信用商店保留信用",
            "⭐收邮件",
            "⭐据点兑换",
            "交易货品优先序列",
            "⭐转交运送委托",
            "⭐转交委托奖励领取",
            "⭐造装备",
            "⭐简易制作",
            "⭐收信用",
            "尝试仅收培育室",
            "⭐帝江号收菜",
            "帝江号收菜操作",
            "⭐活动奖励",
            "活动奖励",
            "⭐日常奖励",
            "⭐送礼",
            "一次送礼个数",
            "⭐帝江号一键存放",
            "送礼任务最多尝试次数",
            "优先送礼对象",
            "⭐演算",
            "⭐执行外部命令",
            "外部命令",
            "外部命令起始于",
            "外部命令等待退出",
            "外部命令已运行时跳过",
            "外部命令执行时机",
            "⭐传送到帝江号右侧传送点",
            "发生异常时终止游戏",
            "仅退出游戏",
            "自动打开汇总文件",
            "Exit After Task",
        ]
    )
}


def _parse_po_file(po_path: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    try:
        text = po_path.read_text(encoding="utf-8")
        for match in _PO_ENTRY_RE.finditer(text):
            msgid = match.group(1)
            msgstr = match.group(2)
            if msgid and msgstr:
                labels[msgid] = msgstr
    except Exception:
        pass
    return labels


def _parse_mo_file(mo_path: Path) -> dict[str, str]:
    try:
        with mo_path.open("rb") as fp:
            catalog = gettext.GNUTranslations(fp)._catalog
        return {
            msgid: msgstr
            for msgid, msgstr in catalog.items()
            if isinstance(msgid, str)
            and msgid
            and isinstance(msgstr, str)
            and msgstr
        }
    except Exception:
        return {}


def _parse_ts_file(ts_path: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    try:
        root = ElementTree.parse(str(ts_path)).getroot()
        for message in root.iter("message"):
            source = message.find("source")
            translation = message.find("translation")
            if (
                source is not None
                and translation is not None
                and source.text
                and translation.text
                and translation.attrib.get("type") != "unfinished"
            ):
                labels[source.text] = translation.text
    except Exception:
        pass
    return labels


def load_okef_option_labels(root_path: Path | str) -> dict[str, str]:
    """从 OK-EF 安装目录加载英中标签映射。"""

    root = Path(root_path)
    labels: dict[str, str] = {}

    i18n_candidates = [
        root / "i18n",
        root / "_internal" / "i18n",
        root / "data" / "apps" / "ok-ef" / "repo" / "i18n",
        root / "data" / "apps" / "ok-ef" / "working" / "i18n",
    ]
    for i18n_dir in i18n_candidates:
        mo_file = i18n_dir / "zh_CN" / "LC_MESSAGES" / "ok.mo"
        if mo_file.is_file():
            loaded = _parse_mo_file(mo_file)
            if loaded:
                labels.update(loaded)
                break

        po_file = i18n_dir / "zh_CN" / "LC_MESSAGES" / "ok.po"
        if po_file.is_file():
            loaded = _parse_po_file(po_file)
            if loaded:
                labels.update(loaded)
                break

    ts_candidates = [
        root / "ok" / "gui" / "i18n" / "zh_CN.ts",
        root / "_internal" / "ok" / "gui" / "i18n" / "zh_CN.ts",
        root / "data" / "apps" / "ok-ef" / "repo" / "ok" / "gui" / "i18n" / "zh_CN.ts",
        root / "data" / "apps" / "ok-ef" / "working" / "ok" / "gui" / "i18n" / "zh_CN.ts",
    ]
    for ts_file in ts_candidates:
        if ts_file.is_file():
            loaded = _parse_ts_file(ts_file)
            if loaded:
                labels.update(loaded)
                break

    return labels


def _translate(key: str, labels: dict[str, str]) -> str:
    if key in _FIELD_LABELS:
        return _FIELD_LABELS[key]
    if key in labels:
        return labels[key]
    if key in _FALLBACK_LABELS:
        return _FALLBACK_LABELS[key]
    return key


def _is_internal_field(name: str) -> bool:
    return name.startswith("_")


def _is_account_field(name: str) -> bool:
    return name in _ACCOUNT_FIELD_NAMES


def _is_hidden_field(name: str) -> bool:
    return name in _HIDDEN_FIELD_NAMES


def _is_visible_config(filename: str) -> bool:
    return not filename.startswith("_") and filename not in _SKIP_CONFIG_FILES


def _group_for_config(filename: str) -> str:
    if filename in _FILE_GROUPS:
        return _FILE_GROUPS[filename]
    if filename in _TASK_INDEX_MAP:
        return "一次性任务配置"
    if filename.endswith("Task.json"):
        return "后台任务配置"
    if "Config" in filename or "Options" in filename or "Hotkey" in filename:
        return "全局配置"
    return "其他配置"


def _sort_key(filename: str) -> tuple[int, int, str]:
    if filename in _TASK_INDEX_MAP:
        return (0, _TASK_INDEX_MAP[filename], filename)
    if filename.endswith("Task.json"):
        return (1, 0, filename)
    return (2, 0, filename)


def _get_select_options(filename: str, field_name: str) -> list[str] | None:
    configured = _SELECT_OPTIONS.get(filename, {}).get(field_name)
    if configured is None:
        configured = _GLOBAL_SELECT_OPTIONS.get(field_name)
    return configured


def _section_for_field(filename: str, field_name: str) -> str:
    if _is_account_field(field_name):
        return "多账户模式"
    if field_name in _FIELD_SECTIONS:
        return _FIELD_SECTIONS[field_name]
    if filename == "Battle Config.json":
        return "战斗相关选项"
    if filename == "Basic Options.json":
        return "基础选项"
    return "其他配置"


def _provider_declarations_for_config(
    filename: str,
    json_data: dict[str, Any],
    option_labels: dict[str, str],
) -> tuple[FieldDeclaration, ...]:
    names = list(json_data)
    names.extend(
        name
        for name in _SELECT_OPTIONS.get(filename, {})
        if name not in json_data
    )
    names.extend(
        name
        for name in _GLOBAL_SELECT_OPTIONS
        if name not in json_data and name not in names
    )

    declarations: list[FieldDeclaration] = []
    for name in names:
        if _is_internal_field(name) or _is_hidden_field(name):
            continue
        options = _get_select_options(filename, name)
        section = _section_for_field(filename, name)
        declarations.append(
            FieldDeclaration(
                path=name,
                label=_translate(name, option_labels),
                description=_FIELD_DESCRIPTIONS.get(name, ""),
                control=(
                    CONTROL_TEXTAREA
                    if name in _MULTILINE_FIELD_NAMES
                    else ""
                ),
                choices=tuple(
                    FieldChoice(
                        value=value,
                        label=_translate(value, option_labels),
                    )
                    for value in options or ()
                ),
                source=SOURCE_PROVIDER,
                confidence=CONFIDENCE_DECLARED,
                section=section,
                section_priority=_SECTION_ORDER.get(section, 800),
                priority=_FIELD_PRIORITY.get(name, 999),
                advanced=name not in _FIELD_PRIORITY,
            )
        )
    return tuple(declarations)


def build_field_schemas_for_config(
    filename: str,
    json_data: dict[str, Any],
    option_labels: dict[str, str],
    *,
    upstream: Iterable[FieldDeclaration] = (),
) -> tuple[FieldSchema, ...]:
    """用公共 FieldSchema 物化 OK-EF 配置字段。"""

    visible_data = {
        name: value
        for name, value in json_data.items()
        if not _is_internal_field(name) and not _is_hidden_field(name)
    }
    visible_upstream = tuple(
        declaration
        for declaration in upstream
        if not _is_internal_field(declaration.path)
        and not _is_hidden_field(declaration.path)
    )
    return materialize_field_schemas(
        visible_data,
        upstream=visible_upstream,
        provider=_provider_declarations_for_config(
            filename,
            visible_data,
            option_labels,
        ),
    )


def build_fields_for_config(
    filename: str,
    json_data: dict[str, Any],
    option_labels: dict[str, str],
    *,
    upstream: Iterable[FieldDeclaration] = (),
) -> list[dict[str, Any]]:
    """投影为当前宿主编辑器消费的兼容字段。"""

    schemas = build_field_schemas_for_config(
        filename,
        json_data,
        option_labels,
        upstream=upstream,
    )
    return render_legacy_fields(schemas, json_data)


def _visible_field_count(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 1
    if not isinstance(data, dict):
        return 1
    return sum(
        not _is_internal_field(name) and not _is_hidden_field(name)
        for name in data
    )


def get_config_info_from_dir(config_dir: Path | str) -> list[dict[str, Any]]:
    """按实际配置目录返回可编辑配置文件元信息。"""

    root = Path(config_dir)
    if not root.is_dir():
        return []

    result = []
    for path in sorted(root.glob("*.json"), key=lambda item: _sort_key(item.name)):
        if not _is_visible_config(path.name):
            continue
        field_count = _visible_field_count(path)
        if field_count == 0:
            continue
        result.append(
            {
                "filename": path.name,
                "displayName": _DISPLAY_NAMES.get(path.name, path.stem),
                "group": _group_for_config(path.name),
                "taskIndex": _TASK_INDEX_MAP.get(path.name),
                "fieldCount": field_count,
            }
        )
    return result
