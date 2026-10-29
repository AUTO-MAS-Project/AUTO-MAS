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

"""MaaEnd 执行阶段、任务编排与客户端更新声明。"""

MAAEND_RUN_MOOD_BOOK = {
    "Delivery": "送货",
    "Routine": "日常",
    "AutoCollect": "自动采集",
}
"""MaaEnd 自动代理运行模式映射表"""

MAAEND_DELIVERY_TASK = "SeizeDeliveryJobs"
"""MaaEnd v2 送货阶段使用的任务名称"""

MAAEND_AUTO_COLLECT_TASK = "AutoCollect"
"""MaaEnd 自动采集阶段使用的任务名称"""

MAAEND_TASK_GROUPS = {
    "Sanity": {
        "label": "理智作战",
        "tasks": (
            ("Sanity", "理智任务"),
            ("AutoUseSpMedication", "应急理智加强剂"),
        ),
    },
    "Infrastructure": {
        "label": "基建任务",
        "tasks": (
            ("DijiangRewards", "基建任务"),
            ("DeliveryJobs", "转交委托"),
            ("SellProduct", "售卖产品"),
            ("AutoStockpile", "自动囤货"),
            ("AutoStockStaple", "购买稳定物资"),
        ),
    },
    "Credit": {
        "label": "信用收支",
        "tasks": (
            ("VisitFriends", "拜访好友"),
            ("CreditShoppingN2", "信用点购物"),
        ),
    },
    "Frontend": {
        "label": "前台任务",
        "tasks": (
            ("AutoEcoFarm", "生态农场"),
            ("AutoSell", "售卖弹性物资"),
            ("EnvironmentMonitoring", "环境监测"),
            ("TrialOfSwordmancy", "选剑演武"),
        ),
    },
    "Rewards": {
        "label": "奖励领取",
        "tasks": (
            ("DailyRewards", "日常奖励领取"),
            ("ResourceRecycleStation", "资源回收站"),
        ),
    },
    "Statistics": {
        "label": "数据统计",
        "tasks": (("PullCountCalculator", "抽数计算"),),
    },
}
"""MaaEnd任务分组"""

MAAEND_TASKS = tuple(
    task_name
    for group in MAAEND_TASK_GROUPS.values()
    for task_name, _ in group["tasks"]
)
"""MaaEnd快速控制任务列表（不含独立送货和自动采集阶段）"""

ENDFIELD_SERVER_PRESETS: dict[tuple[str, str, str], dict[str, str]] = {
    ("6LL0KJuqHBVz33WK", "1", "1"): {
        "label": "官服",
        "api_url": "https://launcher.hypergryph.com/api/proxy/batch_proxy",
        "appcode": "6LL0KJuqHBVz33WK",
        "launcher_appcode": "abYeZZ16BPluCFyT",
        "channel": "1",
        "sub_channel": "1",
        "seq": "5",
    },
    ("6LL0KJuqHBVz33WK", "2", "2"): {
        "label": "B服",
        "api_url": "https://launcher.hypergryph.com/api/proxy/batch_proxy",
        "appcode": "6LL0KJuqHBVz33WK",
        "launcher_appcode": "abYeZZ16BPluCFyT",
        "channel": "2",
        "sub_channel": "2",
        "seq": "5",
    },
    ("YDUTE5gscDZ229CW", "6", "6"): {
        "label": "国际服",
        "api_url": "https://launcher.gryphline.com/api/proxy/batch_proxy",
        "appcode": "YDUTE5gscDZ229CW",
        "launcher_appcode": "YDUTE5gscDZ229CW",
        "channel": "6",
        "sub_channel": "6",
        "seq": "3",
    },
    ("YDUTE5gscDZ229CW", "6", "802"): {
        "label": "国际服（Google Play）",
        "api_url": "https://launcher.gryphline.com/api/proxy/batch_proxy",
        "appcode": "YDUTE5gscDZ229CW",
        "launcher_appcode": "YDUTE5gscDZ229CW",
        "channel": "6",
        "sub_channel": "802",
        "seq": "3",
    },
}
"""终末地 PC 客户端的四套服务器参数，按渠道区分。

键是客户端 `config.ini` 里登记的 `(appcode, channel, sub_channel)`, 用来选出官服、B服、国际服与国际服

MAS 没有选服入口，只按登记值匹配这四套；匹配不到就不碰客户端，绝不拿官服参数去顶。

`channel` / `sub_channel` / `seq` / `version` 在请求里必须是 JSON 字符串：给成数字会被判400，版本串带首尾空格会被判 500。
"""
