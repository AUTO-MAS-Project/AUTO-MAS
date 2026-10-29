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

"""MaaEnd 配置共用的选项、展示词表与固定兼容默认值。"""

MAAEND_DELIVERY_COMMISSION_SOURCES = ("Unlimited", "WulingCity", "TestArea")
"""MaaEnd 抢委托送货的委托接收点选项"""

MAAEND_AUTO_COLLECT_MODES = ("Distributed", "Concentrated")
"""MaaEnd 自动采集的三日周期模式"""

MAAEND_SANITY_TASK_LABELS = {
    "OperatorProgression": "干员养成",
    "WeaponProgression": "武器养成",
    "CrisisDrills": "危境预演",
    "Essence": "基质刷取",
}
"""MaaEnd理智任务类型展示文案"""

MAAEND_SANITY_TASK_DETAIL_LABELS = {
    "OperatorEXP": "干员经验",
    "Promotions": "干员进阶",
    "T-Creds": "钱币收集",
    "SkillUp": "技能提升",
    "WeaponEXP": "武器经验",
    "WeaponTune": "武器进阶",
    "AdvancedProgression1": "高阶培养 I - D96钢样品四",
    "AdvancedProgression2": "高阶培养 II - 超距辉映管",
    "AdvancedProgression3": "高阶培养 III - 快子遴捡晶格",
    "AdvancedProgression4": "高阶培养 IV - 象限拟合液",
    "AdvancedProgression5": "高阶培养 V - 三相纳米片",
}
"""MaaEnd理智任务详细选项展示文案"""

MAAEND_SANITY_TASK_TYPES = (
    "OperatorProgression",
    "WeaponProgression",
    "CrisisDrills",
    "Essence",
)
"""MaaEnd理智任务类型列表"""

MAAEND_AUTO_ESSENCE_MENUS = ("Random", "Location", "Target")
"""MaaEnd 基质刷取模式（随机、地点、目标）"""

MAAEND_PROTOCOL_SPACE_TASK_OPTIONS = {
    "OperatorProgression": ("OperatorEXP", "Promotions", "T-Creds", "SkillUp"),
    "WeaponProgression": ("WeaponEXP", "WeaponTune"),
    "CrisisDrills": (
        "AdvancedProgression1",
        "AdvancedProgression2",
        "AdvancedProgression3",
        "AdvancedProgression4",
        "AdvancedProgression5",
    ),
}
"""MaaEnd协议空间任务选项列表"""

MAAEND_STAGE_WITH_AB = set(["OperatorEXP", "Promotions", "SkillUp", "WeaponTune"])
"""MAAEnd任务包含AB关的关卡列表"""

MAAEND_SANITY_TASK_DEFAULTS = {
    "SanityTaskType": "OperatorProgression",
    "OperatorProgression": "OperatorEXP",
    "WeaponProgression": "WeaponEXP",
    "CrisisDrills": "AdvancedProgression1",
    "RewardsSetOption": "RewardsSetA",
    "AutoEssenceSpecifiedLocation": "",
    # Location 保持原有“指定地点”语义；Target 由用户显式切换。
    "AutoEssenceMenu": "Location",
    "AutoEssenceTargetWeapons": [],
}
"""MaaEnd理智任务字段默认值"""

# 固定采用 MaaEnd 2.36.0-beta.1 的 SupplyPlanLimits 默认值。
MAAEND_INVENTORY_TARGET_DEFAULTS = {
    "SupplyPlanLimit_T_CREDS": "3580000",
    "SupplyPlanLimit_PROTOHEDRON": "1100",
    "SupplyPlanLimit_PROTOPRISM": "920",
    "SupplyPlanLimit_COGNITIVE_CARRIER_EXP": "2100000",
    "SupplyPlanLimit_COMBAT_RECORD_EXP": "1500000",
    "SupplyPlanLimit_PROTOSET": "120",
    "SupplyPlanLimit_PROTODISK": "65",
    "SupplyPlanLimit_WEAPON_EXP": "5000000",
    "SupplyPlanLimit_HEAVY_CAST_DIE": "100",
    "SupplyPlanLimit_CAST_DIE": "45",
    "SupplyPlanLimit_WARP_PLASMA_COATED_SLIDE": "260",
    "SupplyPlanLimit_TRIPHASIC_NANOFLAKE": "260",
    "SupplyPlanLimit_QUADRANT_FITTING_FLUID": "260",
    "SupplyPlanLimit_TACHYON_SCREENING_LATTICE": "260",
    "SupplyPlanLimit_D96_STEEL_SAMPLE_4": "260",
    "SupplyPlanLimit_METADIASTIMA_PHOTOEMISSION_TUBE": "260",
}

MAAEND_SANITY_TASK_FIELDS = (
    "SanityTaskType",
    "OperatorProgression",
    "WeaponProgression",
    "CrisisDrills",
    "RewardsSetOption",
    "AutoEssenceSpecifiedLocation",
    "AutoEssenceMenu",
    "AutoEssenceTargetWeapons",
)
"""MaaEnd理智任务字段列表"""
