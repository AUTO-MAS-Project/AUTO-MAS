#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""任务级配置元数据与读写。

zzz-od 每个应用（任务）的配置存于 ``config/{idx:02d}/one_dragon/{app_id}.yml``
（一条龙 group_id=one_dragon），原生 GUI 以 FLYOUT 弹出设置卡片编辑
（选项静态已知的部分硬编码在其 GUI 组件中，动态选项来自游戏数据与配置目录）。
MAS 侧用数据驱动的元数据表复刻常用任务；加任务 = 在 :data:`TASK_APP_FIELDS`
加一个表项。

字段类型（``type``）与前端渲染方式一一对应：

- ``select`` — 下拉（静态 ``options`` 或 ``source`` 指向动态选项源）
- ``bool`` — 开关；``number`` — 数字输入
- ``team`` — 预备编队下拉（展示同 select，保存为 int 编队下标，-1=游戏内配队）
- ``plan_list`` — 计划列表（任务卡片 ⚙ 打开大设置弹窗编辑），``columns``
  声明行内字段（级联列 type=cascade 按声明顺序钻取训练副本树），
  ``new_item`` 为新增行的默认值（与上游 dataclass 默认一致）

动态选项源（``source``，见 :mod:`app.task.ZzzOd.tools.compendium`）：
``auto_battle`` 配队方案模板 / ``lost_void_challenge``、``hollow_zero_challenge``
挑战配置模板 / ``compendium_lost_void``、``hollow_zero_missions`` 副本图层 /
``world_patrol_route_list`` 锄大地路线名单 / ``agent_names`` 代理人名 /
``coffee_day_{1..7}`` 当日咖啡 / ``predefined_teams`` 预备编队（读目标槽
team.yml，随槽而异）。静态 ``options`` 会前置合并（如「随机」「全部」）。

``show_when`` 条件列支持单条件 dict 或条件列表（全部满足才显示），条件为
``{field, value, not?}``：``not=True`` 表示「不等于该值」时显示（如合成电池
分类下隐藏配队列）。

任务卡片与 MAS 字段一样是**持久写绑定槽**（直控写指定原生实例）：注入
（game_account + _group）不碰 per-app yml，恢复备份时随槽内容一起回到该时点。
``plan_list`` 保存时按 plan_id 保留既有 ``run_times``（已运行进度），MAS 只改
计划内容，不重置一条龙的运行计数。
"""

import uuid
from pathlib import Path
from typing import Any

from app.utils.io import read_file, write_file

# 应用配置存储子目录（一条龙默认组，与 _group.yml 同目录）
_APP_GROUP_ID = "one_dragon"

# ── 静态枚举选项（与上游 Enum 的 ConfigItem 取值逐字一致，上游改动需同步）──

# NotoriousHuntLevelEnum（体力刷本与恶名狩猎的等级取值一致）
_LEVEL_OPTIONS = [
    {"label": "默认等级", "value": "默认等级"},
    {"label": "等级Lv.65", "value": "等级Lv.65"},
    {"label": "等级Lv.60", "value": "等级Lv.60"},
    {"label": "等级Lv.50", "value": "等级Lv.50"},
    {"label": "等级Lv.40", "value": "等级Lv.40"},
    {"label": "等级Lv.30", "value": "等级Lv.30"},
]

# NotoriousHuntBuffEnum
_BUFF_OPTIONS = [
    {"label": "第一个BUFF", "value": "1"},
    {"label": "第二个BUFF", "value": "2"},
    {"label": "第三个BUFF", "value": "3"},
]

# CardNumEnum（实战模拟室卡片数量，value 为字符串数字）
_CARD_NUM_OPTIONS = [
    {"label": "默认数量", "value": "默认数量"},
    {"label": "1张卡片", "value": "1"},
    {"label": "2张卡片", "value": "2"},
    {"label": "3张卡片", "value": "3"},
    {"label": "4张卡片", "value": "4"},
    {"label": "5张卡片", "value": "5"},
]

# RestoreChargeEnum
_RESTORE_CHARGE_OPTIONS = [
    {"label": "不使用", "value": "不使用"},
    {"label": "使用储蓄电量", "value": "使用储蓄电量"},
    {"label": "使用以太电池", "value": "使用以太电池"},
    {"label": "同时使用储蓄电量和以太电池", "value": "同时使用储蓄电量和以太电池"},
]

# LostVoidTaskEnum
_LOST_VOID_TASK_OPTIONS = [
    {"label": "完成悬赏委托", "value": "完成悬赏委托"},
    {"label": "刷满业绩点", "value": "刷满业绩点"},
    {"label": "刷满周期奖励", "value": "刷满周期奖励"},
    {"label": "完成周计划次数", "value": "完成周计划次数"},
]

# NotoriousHuntWeekdayEnum（value 为 int，对齐上游 `notorious_hunt_run_record.py:47`
# 的 `>=` 比较，避免 select 分支 str 落盘后上游抛 TypeError；其他 select 字段保持字符串）
# 周几短标签（按 1~7，咖啡每日选择等字段标题用）
_WEEKDAY_LABELS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

_WEEKDAY_OPTIONS = [
    {"label": label, "value": day} for day, label in enumerate(_WEEKDAY_LABELS, 1)
]

# CoffeeTransportPoint（ConfigItem 单参构造 value=label）
_COFFEE_TRANSPORT_OPTIONS = [
    {"label": "六分街 - 咖啡店", "value": "六分街 - 咖啡店"},
    {"label": "澄辉坪 - 汀曼咖啡", "value": "澄辉坪 - 汀曼咖啡"},
    {"label": "布亚斯特城区 - 片刻闲", "value": "布亚斯特城区 - 片刻闲"},
]

# CoffeeChooseWay
_COFFEE_CHOOSE_WAY_OPTIONS = [
    {"label": "优先体力计划", "value": "优先体力计划"},
    {"label": "汀曼特调", "value": "汀曼特调"},
    {"label": "浓缩咖啡", "value": "浓缩咖啡"},
]

# CoffeeChallengeWay
_COFFEE_CHALLENGE_WAY_OPTIONS = [
    {"label": "全都挑战", "value": "全都挑战"},
    {"label": "只挑战体力计划", "value": "只挑战体力计划"},
    {"label": "不挑战", "value": "不挑战"},
]

# CoffeeCardNumEnum（与 charge_plan CardNumEnum 数量语义一致，仅两项）
_COFFEE_CARD_NUM_OPTIONS = [
    {"label": "默认数量", "value": "默认数量"},
    {"label": "1", "value": "1"},
]

# RandomPlayTransportPoint
_RANDOM_PLAY_TRANSPORT_OPTIONS = [
    {"label": "录像店 - 柜台", "value": "录像店 - 柜台"},
    {"label": "澄辉坪 - 录像店营业点", "value": "澄辉坪 - 录像店营业点"},
    {"label": "布亚斯特城区 - 录像店营业点", "value": "布亚斯特城区 - 录像店营业点"},
]

# HollowZeroExtraTask（枯萎之都）
_HOLLOW_EXTRA_TASK_OPTIONS = [
    {"label": "不进行", "value": "不进行"},
    {"label": "刷满业绩点", "value": "刷满业绩点"},
    {"label": "刷满周期奖励", "value": "刷满周期奖励"},
]

# HollowZeroExtraExitEnum
_HOLLOW_EXTRA_EXIT_OPTIONS = [
    {"label": "通关", "value": "通关"},
    {"label": "2层业绩后退出", "value": "2层业绩后退出"},
    {"label": "3层业绩后退出", "value": "3层业绩后退出"},
]

# DismantleLevelEnum
_DISMANTLE_LEVEL_OPTIONS = [
    {"label": "B", "value": "B"},
    {"label": "A及以下", "value": "A及以下"},
    {"label": "S及以下", "value": "S及以下"},
]

# SuibianTempleAdventureDispatchDuration（配置存 enum name）
_ADVENTURE_DURATION_OPTIONS = [
    {"label": "3分钟", "value": "MIN_3"},
    {"label": "15分钟", "value": "MIN_15"},
    {"label": "1小时", "value": "HOUR_1"},
    {"label": "2小时", "value": "HOUR_2"},
    {"label": "6小时", "value": "HOUR_6"},
    {"label": "12小时", "value": "HOUR_12"},
    {"label": "20小时", "value": "HOUR_20"},
]

# SuibianTempleAdventureMission（配置存 enum name，值即展示名）
_ADVENTURE_MISSION_OPTIONS = [
    {"label": name, "value": name}
    for name in (
        [f"制造区{r}-{n}" for r in (1, 2, 3) for n in (1, 2, 3, 4)]
        + [f"社区旧址{r}-{n}" for r in (1, 2, 3) for n in (1, 2, 3, 4)]
        + [f"科研院旧址{r}-{n}" for r in (1, 2, 3) for n in (1, 2, 3, 4)]
    )
]

# BangbooPrice（配置存 enum name）
_BANGBOO_PRICE_OPTIONS = [
    {"label": "40000", "value": "S1"},
    {"label": "35000", "value": "S2"},
    {"label": "30000", "value": "S3"},
    {"label": "25000", "value": "S4"},
    {"label": "不购买", "value": "NONE"},
]

# 随便观游历任务默认（与上游 config 默认一致）
_ADVENTURE_MISSION_DEFAULTS = (
    "RESEARCH_3_4",
    "RESEARCH_2_4",
    "RESEARCH_1_4",
    "COMMUNITY_3_4",
)

# WorldPatrol 界面消失处理（value 为代码常量，label 与上游 GUI 一致）
_WORLD_PATROL_UI_DISAPPEAR_OPTIONS = [
    {"label": "静默失败", "value": "silent_fail"},
    {"label": "重开游戏并跳过路线", "value": "restart_and_skip"},
    {"label": "重开游戏并重试路线", "value": "restart_and_retry"},
]

# WorldPatrol 路线重试处理
_WORLD_PATROL_ROUTE_RETRY_OPTIONS = [
    {"label": "若再次卡住则跳过脱困", "value": "skip_on_stuck_again"},
    {"label": "若再次卡住仍尝试脱困", "value": "retry_on_stuck_again"},
]

# ── 计划列表列定义 ──
# 级联列（type=cascade）按声明顺序钻取训练副本树：分类 → 类型 → 关卡；
# show_when 控制条件列（数据驱动，前端通用渲染）。

# ChargePlanItem 的计划内容列（体力刷本与恶名狩猎共用子集）
# 游戏内配队（predefined_team_idx）与配队方案（auto_battle_config）按上游
# GUI 互斥：配队方案仅在「游戏内配队」(predefined_team_idx=-1) 时显示；
# 两者在合成电池分类下都无意义，隐藏
_PLAN_COLUMNS = [
    {"field": "category_name", "title": "副本", "type": "cascade"},
    {"field": "mission_type_name", "title": "类型", "type": "cascade"},
    {"field": "mission_name", "title": "关卡", "type": "cascade"},
    {"field": "level", "title": "等级", "type": "select", "options": _LEVEL_OPTIONS},
    {
        "field": "auto_battle_config",
        "title": "配队方案",
        "type": "select",
        "source": "auto_battle",
        "show_when": [
            {"field": "category_name", "value": "合成电池", "not": True},
            {"field": "predefined_team_idx", "value": -1},
        ],
    },
    {
        "field": "predefined_team_idx",
        "title": "游戏内配队",
        "type": "team",
        "source": "predefined_teams",
        "show_when": {"field": "category_name", "value": "合成电池", "not": True},
    },
    {"field": "plan_times", "title": "计划次数", "type": "number"},
]

# 恶名狩猎 BUFF 列（仅恶名狩猎分类显示）
_BUFF_COLUMN = {
    "field": "notorious_hunt_buff_num",
    "title": "BUFF",
    "type": "select",
    "options": _BUFF_OPTIONS,
    "show_when": {"field": "category_name", "value": "恶名狩猎"},
}

# ChargePlanItem 的隐藏持久字段（不进编辑列，但保存时白名单保留）
_PLAN_HIDDEN_FIELDS = ("tab_name", "run_times", "plan_id")

# 任务配置元数据表：app_id → 字段定义（数据驱动，加任务即加表项）
TASK_APP_FIELDS: dict[str, list[dict[str, Any]]] = {
    "daily_signin": [
        {
            "field": "selected_sign",
            "title": "选择签到商店",
            "type": "select",
            "options": [
                {"label": "吼吼饼铺", "value": "hou_hou_bakery"},
                {"label": "卦象集录", "value": "trigrams_collection"},
                {"label": "刮刮卡", "value": "scratch_card"},
            ],
        },
    ],
    "charge_plan": [
        {
            "field": "plan_list",
            "title": "体力计划",
            "type": "plan_list",
            "columns": [
                *_PLAN_COLUMNS,
                {
                    "field": "card_num",
                    "title": "卡片数量",
                    "type": "select",
                    "options": _CARD_NUM_OPTIONS,
                    "show_when": {"field": "category_name", "value": "实战模拟室"},
                },
                _BUFF_COLUMN,
            ],
            "new_item": {
                "tab_name": "训练",
                "category_name": "实战模拟室",
                "mission_type_name": "基础材料",
                "mission_name": "调查专项",
                "level": "默认等级",
                "auto_battle_config": "全配队通用",
                "run_times": 0,
                "plan_times": 1,
                "card_num": "默认数量",
                "predefined_team_idx": -1,
                "notorious_hunt_buff_num": 1,
            },
        },
        {"field": "loop", "title": "循环执行", "type": "bool", "default": True},
        {
            "field": "daily_reset_plan_times",
            "title": "每日清零已运行次数",
            "type": "bool",
            "default": False,
        },
        {
            "field": "restore_charge",
            "title": "体力恢复",
            "type": "select",
            "options": _RESTORE_CHARGE_OPTIONS,
        },
    ],
    "notorious_hunt": [
        {
            "field": "plan_list",
            "title": "恶名狩猎计划",
            "type": "plan_list",
            "columns": [
                *_PLAN_COLUMNS,
                _BUFF_COLUMN,
            ],
            "new_item": {
                "tab_name": "训练",
                "category_name": "恶名狩猎",
                "mission_type_name": "",
                "mission_name": None,
                "level": "默认等级",
                "auto_battle_config": "全配队通用",
                "run_times": 0,
                "plan_times": 1,
                "predefined_team_idx": -1,
                "notorious_hunt_buff_num": 1,
            },
        },
        {
            "field": "weekly_challenge_start_weekday",
            "title": "周挑战起始日",
            "type": "select",
            "options": _WEEKDAY_OPTIONS,
        },
        {"field": "loop", "title": "循环执行", "type": "bool", "default": True},
    ],
    "lost_void": [
        {
            "field": "daily_plan_times",
            "title": "每日计划次数",
            "type": "number",
            "default": 5,
        },
        {
            "field": "weekly_plan_times",
            "title": "每周计划次数",
            "type": "number",
            "default": 2,
        },
        {
            "field": "extra_task",
            "title": "额外任务",
            "type": "select",
            "options": _LOST_VOID_TASK_OPTIONS,
        },
        {
            "field": "mission_name",
            "title": "选图",
            "type": "select",
            "source": "compendium_lost_void",
            "default": "战线肃清",
        },
        {
            "field": "challenge_config",
            "title": "挑战配置",
            "type": "select",
            "source": "lost_void_challenge",
            "default": "默认-成就模式",
        },
    ],
    "withered_domain": [
        {
            "field": "daily_plan_times",
            "title": "每日计划次数",
            "type": "number",
            "default": 99,
        },
        {
            "field": "weekly_plan_times",
            "title": "每周计划次数",
            "type": "number",
            "default": 2,
        },
        {
            "field": "extra_task",
            "title": "额外任务",
            "type": "select",
            "options": _HOLLOW_EXTRA_TASK_OPTIONS,
            "default": "刷满周期奖励",
        },
        {
            "field": "extra_exit",
            "title": "额外任务退出时机",
            "type": "select",
            "options": _HOLLOW_EXTRA_EXIT_OPTIONS,
            "default": "通关",
        },
        {
            "field": "mission_name",
            "title": "选图",
            "type": "select",
            "source": "hollow_zero_missions",
            "default": "旧都列车-内部",
        },
        {
            "field": "challenge_config",
            "title": "挑战配置",
            "type": "select",
            "source": "hollow_zero_challenge",
            "default": "默认-专属空洞-艾莲",
        },
    ],
    "coffee": [
        {
            "field": "transport_point",
            "title": "传送地点",
            "type": "select",
            "options": _COFFEE_TRANSPORT_OPTIONS,
        },
        {
            "field": "choose_way",
            "title": "咖啡选择",
            "type": "select",
            "options": _COFFEE_CHOOSE_WAY_OPTIONS,
        },
        {
            "field": "challenge_way",
            "title": "喝后挑战",
            "type": "select",
            "options": _COFFEE_CHALLENGE_WAY_OPTIONS,
        },
        {
            "field": "card_num",
            "title": "体力计划外的数量",
            "type": "select",
            "options": _COFFEE_CARD_NUM_OPTIONS,
            "default": "1",
        },
        {
            "field": "auto_battle",
            "title": "配队方案",
            "type": "select",
            "source": "auto_battle",
            "default": "全配队通用",
        },
        {
            "field": "predefined_team_idx",
            "title": "预备编队",
            "type": "team",
            "source": "predefined_teams",
        },
        {
            "field": "run_charge_plan_afterwards",
            "title": "结束后运行体力计划",
            "type": "bool",
            "default": False,
        },
        *[
            {
                "field": f"day_coffee_{day}",
                "title": f"{name}咖啡",
                "type": "select",
                "source": f"coffee_day_{day}",
                "default": "汀曼特调",
            }
            for day, name in zip((1, 2, 3, 4, 5, 6, 7), _WEEKDAY_LABELS)
        ],
    ],
    "intel_board": [
        {
            "field": "predefined_team_idx",
            "title": "预备编队",
            "type": "team",
            "source": "predefined_teams",
        },
        {
            "field": "auto_battle_config",
            "title": "配队方案",
            "type": "select",
            "source": "auto_battle",
            "default": "全配队通用",
        },
        {
            "field": "exp_grind_mode",
            "title": "刷满经验模式",
            "type": "bool",
            "default": False,
        },
    ],
    "suibian_temple": [
        {
            "field": "auto_manage_enabled",
            "title": "自动托管",
            "type": "bool",
            "default": True,
        },
        {"field": "yum_cha_sin", "title": "饮茶仙", "type": "bool", "default": True},
        {
            "field": "yum_cha_sin_period_refresh",
            "title": "饮茶仙-定期采办刷新",
            "type": "bool",
            "default": True,
        },
        {
            "field": "adventure_duration",
            "title": "游历-时间",
            "type": "select",
            "options": _ADVENTURE_DURATION_OPTIONS,
            "default": "HOUR_20",
        },
        *[
            {
                "field": f"adventure_mission_{i}",
                "title": f"游历-任务{i}",
                "type": "select",
                "options": _ADVENTURE_MISSION_OPTIONS,
                "default": _ADVENTURE_MISSION_DEFAULTS[i - 1],
            }
            for i in (1, 2, 3, 4)
        ],
        {
            "field": "craft_drag_times",
            "title": "制造-最大下拉次数",
            "type": "number",
            "default": 10,
        },
        {
            "field": "good_goods_purchase_enabled",
            "title": "好物铺购买",
            "type": "bool",
            "default": False,
        },
        {
            "field": "boo_box_purchase_enabled",
            "title": "邦巢-购买",
            "type": "bool",
            "default": False,
        },
        {
            "field": "boo_box_adventure_price",
            "title": "邦巢-游历最低价",
            "type": "select",
            "options": _BANGBOO_PRICE_OPTIONS,
            "default": "S4",
        },
        {
            "field": "boo_box_craft_price",
            "title": "邦巢-制造最低价",
            "type": "select",
            "options": _BANGBOO_PRICE_OPTIONS,
            "default": "S4",
        },
        {
            "field": "boo_box_sell_price",
            "title": "邦巢-售卖最低价",
            "type": "select",
            "options": _BANGBOO_PRICE_OPTIONS,
            "default": "S4",
        },
        {
            "field": "pawnshop_omnicoin_enabled",
            "title": "德丰大押-百宝通",
            "type": "bool",
            "default": True,
        },
        {
            "field": "pawnshop_crest_enabled",
            "title": "德丰大押-云纹徽",
            "type": "bool",
            "default": True,
        },
        {
            "field": "pawnshop_crest_unlimited_denny_enabled",
            "title": "云纹徽-不限购丁尼",
            "type": "bool",
            "default": False,
        },
    ],
    "world_patrol": [
        {
            "field": "auto_battle",
            "title": "配队方案",
            "type": "select",
            "source": "auto_battle",
            "default": "全配队通用",
        },
        {
            "field": "route_list",
            "title": "路线名单",
            "type": "select",
            "options": [{"label": "全部", "value": ""}],
            "source": "world_patrol_route_list",
        },
        {
            "field": "daily_loop_count",
            "title": "每日轮数",
            "type": "number",
            "default": 1,
        },
        {
            "field": "loop_interval_seconds",
            "title": "每轮最少占用时长(秒)",
            "type": "number",
            "default": 1800,
        },
        {
            "field": "ui_disappear_action",
            "title": "界面消失处理",
            "type": "select",
            "options": _WORLD_PATROL_UI_DISAPPEAR_OPTIONS,
        },
        {
            "field": "ui_disappear_seconds",
            "title": "界面消失判定秒数",
            "type": "number",
            "default": 10,
        },
        {
            "field": "route_retry_times",
            "title": "路线重试次数",
            "type": "number",
            "default": 1,
        },
        {
            "field": "route_retry_action",
            "title": "重试后仍卡住处理",
            "type": "select",
            "options": _WORLD_PATROL_ROUTE_RETRY_OPTIONS,
        },
    ],
    "life_on_line": [
        {
            "field": "daily_plan_times",
            "title": "每日计划次数",
            "type": "number",
            "default": 20,
        },
        {
            "field": "predefined_team_idx",
            "title": "预备编队",
            "type": "team",
            "source": "predefined_teams",
        },
    ],
    "drive_disc_dismantle": [
        {
            "field": "dismantle_level",
            "title": "拆解等级",
            "type": "select",
            "options": _DISMANTLE_LEVEL_OPTIONS,
        },
        {
            "field": "dismantle_abandon",
            "title": "全选已弃置",
            "type": "bool",
            "default": False,
        },
    ],
    "random_play": [
        {
            "field": "transport_point",
            "title": "传送地点",
            "type": "select",
            "options": _RANDOM_PLAY_TRANSPORT_OPTIONS,
        },
        {
            "field": "agent_name_1",
            "title": "代理人-1",
            "type": "select",
            "options": [{"label": "随机", "value": "随机"}],
            "source": "agent_names",
            "default": "随机",
        },
        {
            "field": "agent_name_2",
            "title": "代理人-2",
            "type": "select",
            "options": [{"label": "随机", "value": "随机"}],
            "source": "agent_names",
            "default": "随机",
        },
    ],
}

# 支持跳转一条龙主界面配置的任务（任务卡片展示跳转按钮）：高度复杂配置
# （式舆防卫战配队、迷失之地/枯萎之都挑战方案）引导用户进原生 GUI 编辑
TASK_APP_JUMPS: frozenset[str] = frozenset(
    {"shiyu_defense", "lost_void", "withered_domain"}
)

# 数字列字段（plan_list 行内保存时转 int）
_PLAN_NUMBER_FIELDS = frozenset(
    {"plan_times", "predefined_team_idx", "notorious_hunt_buff_num"}
)


def get_task_app_fields(app_id: str) -> list[dict[str, Any]] | None:
    """返回任务的可配置字段定义；无元数据（复杂任务）返回 None。"""

    return TASK_APP_FIELDS.get(app_id)


def get_task_app_jump(app_id: str) -> bool:
    """任务是否支持跳转一条龙主界面配置。"""

    return app_id in TASK_APP_JUMPS


def resolve_field_options(
    root: Path, meta: dict[str, Any], config_dir: Path | None = None
) -> list[dict]:
    """解析字段的选项列表：静态 ``options`` 在前，``source`` 动态选项在后。

    静态选项与动态源可组合（如代理人列表前置「随机」、路线名单前置「全部」）。
    ``predefined_teams`` 源随槽而异（读目标槽 team.yml），须经 ``config_dir``
    传入目标实例目录，缺省时无动态选项。
    """

    source = meta.get("source")
    if not source:
        return [dict(o) for o in meta.get("options") or []]

    if source == "predefined_teams":
        from .zzz_od_config import predefined_team_options

        return (
            [dict(o) for o in predefined_team_options(config_dir)]
            if config_dir is not None
            else []
        )

    from .compendium import (
        agent_names,
        auto_battle_options,
        coffee_options,
        hollow_zero_challenge_options,
        hollow_zero_missions,
        lost_void_challenge_options,
        lost_void_missions,
        world_patrol_route_lists,
    )

    if source == "auto_battle":
        dynamic = auto_battle_options(root)
    elif source == "lost_void_challenge":
        dynamic = lost_void_challenge_options(root)
    elif source == "hollow_zero_challenge":
        dynamic = hollow_zero_challenge_options(root)
    elif source == "compendium_lost_void":
        dynamic = [{"label": m, "value": m} for m in lost_void_missions(root)]
    elif source == "hollow_zero_missions":
        dynamic = [{"label": m, "value": m} for m in hollow_zero_missions(root)]
    elif source == "world_patrol_route_list":
        dynamic = world_patrol_route_lists(root)
    elif source == "agent_names":
        dynamic = agent_names(root)
    elif source.startswith("coffee_day_"):
        try:
            day = int(source.rsplit("_", 1)[1])
        except ValueError:
            day = 0
        dynamic = coffee_options(root, day)
    else:
        dynamic = []

    static = [dict(o) for o in meta.get("options") or []]
    return static + dynamic


def merge_plan_list(
    columns: list[dict[str, Any]],
    new_item: dict[str, Any],
    existing: list,
    incoming: list,
) -> list[dict]:
    """合并编辑后的计划列表（保存前白名单过滤 + 进度保留）。

    - 行内字段白名单 = columns 字段 + new_item 里的隐藏持久字段
      （tab_name/run_times/plan_id），多余键丢弃
    - ``run_times``（已运行进度）按 plan_id 保留既有值，新计划从 0 开始
      ——MAS 只改计划内容，不重置一条龙的运行计数
    - 缺失 plan_id 的新行生成 uuid，与上游 ChargePlanItem.__post_init__ 一致
    """

    allowed = [str(c["field"]) for c in columns]
    allowed += list(_PLAN_HIDDEN_FIELDS)
    allowed_set = dict.fromkeys(allowed).keys()

    current_run_times = {
        str(item.get("plan_id")): int(item.get("run_times") or 0)
        for item in (existing or [])
        if isinstance(item, dict) and item.get("plan_id")
    }

    merged: list[dict] = []
    for item in incoming or []:
        if not isinstance(item, dict):
            continue
        clean: dict[str, Any] = {}
        for field in allowed_set:
            value = item.get(field, new_item.get(field))
            if field in _PLAN_NUMBER_FIELDS:
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    value = int(new_item.get(field) or 0)
            clean[field] = value
        plan_id = str(clean.get("plan_id") or "").strip() or str(uuid.uuid4())
        clean["plan_id"] = plan_id
        clean["run_times"] = current_run_times.get(plan_id, 0)
        merged.append(clean)
    return merged


def app_config_path(root: Path, slot_idx: int, app_id: str) -> Path:
    """应用配置文件路径：``config/{idx:02d}/one_dragon/{app_id}.yml``。"""

    return root / "config" / f"{int(slot_idx):02d}" / _APP_GROUP_ID / f"{app_id}.yml"


def read_app_config(root: Path, slot_idx: int, app_id: str) -> dict:
    """读取应用配置（文件不存在返回空 dict，由调用方回退默认值）。"""

    return dict(read_file(app_config_path(root, slot_idx, app_id)) or {})


def write_app_config(
    root: Path, slot_idx: int, app_id: str, values: dict[str, Any]
) -> dict:
    """按 patch 更新应用配置（读-改-写，保留未知字段），返回完整配置。"""

    path = app_config_path(root, slot_idx, app_id)
    data = read_file(path) or {}
    data.update(values)
    write_file(path, data)
    return data
