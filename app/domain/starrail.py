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

"""星穹铁道配置使用的 SRC 关卡标识与展示词表。"""

STARRAIL_STAGE_BOOK = {
    "-": "禁用",
    "Calyx_Golden_Memories_Planarcadia": "材料：角色经验（回忆之蕾 二相乐园）",
    "Calyx_Golden_Aether_Planarcadia": "材料：武器经验（以太之蕾 二相乐园）",
    "Calyx_Golden_Treasures_Planarcadia": "材料：信用点（藏珍之蕾 二相乐园）",
    "Calyx_Golden_Memories_Amphoreus": "材料：角色经验（回忆之蕾 翁法罗斯）",
    "Calyx_Golden_Aether_Amphoreus": "材料：武器经验（以太之蕾 翁法罗斯）",
    "Calyx_Golden_Treasures_Amphoreus": "材料：信用点（藏珍之蕾 翁法罗斯）",
    "Calyx_Golden_Memories_Penacony": "材料：角色经验（回忆之蕾 匹诺康尼）",
    "Calyx_Golden_Aether_Penacony": "材料：武器经验（以太之蕾 匹诺康尼）",
    "Calyx_Golden_Treasures_Penacony": "材料：信用点（藏珍之蕾 匹诺康尼）",
    "Calyx_Golden_Memories_The_Xianzhou_Luofu": "材料：角色经验（回忆之蕾 仙舟罗浮）",
    "Calyx_Golden_Aether_The_Xianzhou_Luofu": "材料：武器经验（以太之蕾 仙舟罗浮）",
    "Calyx_Golden_Treasures_The_Xianzhou_Luofu": "材料：信用点（藏珍之蕾 仙舟罗浮）",
    "Calyx_Golden_Memories_Jarilo_VI": "材料：角色经验（回忆之蕾 雅利洛-Ⅵ）",
    "Calyx_Golden_Aether_Jarilo_VI": "材料：武器经验（以太之蕾 雅利洛-Ⅵ）",
    "Calyx_Golden_Treasures_Jarilo_VI": "材料：信用点（藏珍之蕾 雅利洛-Ⅵ）",
    "Calyx_Crimson_Destruction_Amphoreus_InkfordHermitage": "行迹材料：毁灭（渡画泉隐）",
    "Calyx_Crimson_Destruction_Herta_StorageZone": "行迹材料：毁灭（收容舱段）",
    "Calyx_Crimson_Destruction_Luofu_ScalegorgeWaterscape": "行迹材料：毁灭（鳞渊境）",
    "Calyx_Crimson_Preservation_Herta_SupplyZone": "行迹材料：存护（支援舱段）",
    "Calyx_Crimson_Preservation_Penacony_ClockStudiosThemePark": "行迹材料：存护（克劳克影视乐园）",
    "Calyx_Crimson_The_Hunt_Jarilo_OutlyingSnowPlains": "行迹材料：巡猎（城郊雪原）",
    "Calyx_Crimson_The_Hunt_Penacony_SoulGladScorchsandAuditionVenue": "行迹材料：巡猎（苏乐达热砂海选会场）",
    "Calyx_Crimson_The_Hunt_Amphoreus_MemortisShoreRuinsofTime": "行迹材料：巡猎（葬忆彼岸时光归墟）",
    "Calyx_Crimson_Abundance_Jarilo_BackwaterPass": "行迹材料：丰饶（边缘通路）",
    "Calyx_Crimson_Abundance_Luofu_FyxestrollGarden": "行迹材料：丰饶（绥园）",
    "Calyx_Crimson_Erudition_Jarilo_RivetTown": "行迹材料：智识（铆钉镇）",
    "Calyx_Crimson_Erudition_Penacony_PenaconyGrandTheater": "行迹材料：智识（匹诺康尼大剧院）",
    "Calyx_Crimson_Harmony_Jarilo_RobotSettlement": "行迹材料：同谐（机械聚落）",
    "Calyx_Crimson_Harmony_Penacony_TheReverieDreamscape": "行迹材料：同谐（白日梦酒店-梦境）",
    "Calyx_Crimson_Nihility_Jarilo_GreatMine": "行迹材料：虚无（大矿区）",
    "Calyx_Crimson_Nihility_Luofu_AlchemyCommission": "行迹材料：虚无（丹鼎司）",
    "Calyx_Crimson_Nihility_Amphoreus_SacredTracewoodGroveofDivineInsight": "行迹材料：虚无（「辉痕圣林」神悟树庭）",
    "Calyx_Crimson_Erudition_Amphoreus_SeafeldTVTower": "行迹材料：智识（海原电视塔）",
    "Calyx_Crimson_Remembrance_Amphoreus_StrifeRuinsCastrumKremnos": "行迹材料：记忆（纷争荒墟悬锋城）",
    "Calyx_Crimson_Elation_Planarcadia_WorldEndTavern": "行迹材料：欢愉（世界尽头酒馆）",
    "Stagnant_Shadow_Quanta": "晋阶材料：量子（银狼 / 希儿 / 青雀）",
    "Stagnant_Shadow_Gust": "晋阶材料：风（丹恒 / 布洛妮娅 / 桑博）",
    "Stagnant_Shadow_Fulmination": "晋阶材料：雷（阿兰 / 希露瓦 / 停云 / 白露）",
    "Stagnant_Shadow_Blaze": "晋阶材料：火（姬子 / 艾丝妲 / 虎克）",
    "Stagnant_Shadow_Spike": "晋阶材料：物理（娜塔莎 / 克拉拉 / 卢卡 / 素裳）",
    "Stagnant_Shadow_Rime": "晋阶材料：冰（三月七 / 黑塔 / 杰帕德 / 佩拉）",
    "Stagnant_Shadow_Mirage": "晋阶材料：虚数（瓦尔特 / 罗刹 / 驭空）",
    "Stagnant_Shadow_Icicle": "晋阶材料：冰（彦卿 / 镜流 / 阮•梅）",
    "Stagnant_Shadow_Doom": "晋阶材料：雷（卡芙卡 / 景元 / 黄泉）",
    "Stagnant_Shadow_Puppetry": "晋阶材料：虚数（丹恒•饮月 / 砂金 / 真理医生）",
    "Stagnant_Shadow_Abomination": "晋阶材料：量子（玲可 / 符玄 / 雪衣）",
    "Stagnant_Shadow_Scorch": "晋阶材料：火（托帕&账账 / 桂乃芬 / 忘归人）",
    "Stagnant_Shadow_Celestial": "晋阶材料：风（刃 / 藿藿 / 黑天鹅）",
    "Stagnant_Shadow_Perdition": "晋阶材料：物理（寒鸦 / 银枝）",
    "Stagnant_Shadow_Nectar": "晋阶材料：冰（米沙 / 大黑塔）",
    "Stagnant_Shadow_Roast": "晋阶材料：量子（花火 / 翡翠）",
    "Stagnant_Shadow_Ire": "晋阶材料：火（椒丘 / 灵砂 / 加拉赫 / 流萤）",
    "Stagnant_Shadow_Duty": "晋阶材料：物理（云璃 / 知更鸟 / 波提欧）",
    "Stagnant_Shadow_Timbre": "晋阶材料：虚数（星期日 / 乱破）",
    "Stagnant_Shadow_Mechwolf": "晋阶材料：雷（貊泽 / 阿格莱雅）",
    "Stagnant_Shadow_Gloam": "晋阶材料：风（飞霄 / 那刻夏 / 风堇 / Saber）",
    "Stagnant_Shadow_Sloggyre": "晋阶材料：虚数（万敌）",
    "Stagnant_Shadow_Gelidmoon": "晋阶材料：量子（缇宝 / 赛飞儿 / 遐蝶 / Archer）",
    "Stagnant_Shadow_Deepsheaf": "晋阶材料：物理（白厄 / 海瑟音 / 丹恒•腾荒 / 爻光）",
    "Stagnant_Shadow_Cinders": "晋阶材料：风（刻律德菈）",
    "Stagnant_Shadow_Sirens": "晋阶材料：冰（长夜月 / 昔涟）",
    "Stagnant_Shadow_Ashes": "晋阶材料：火（大丽花 / 火花）",
    "Stagnant_Shadow_Soundburst": "晋阶材料：雷（狂雷扫弦）",
    "Stagnant_Shadow_Devour": "晋阶材料：量子（嗤笑丑面）",
    "Cavern_of_Corrosion_Path_of_Insight": "遗器：领航员 & 名冶（观火之径）",
    "Cavern_of_Corrosion_Path_of_Possession": "遗器：魔法少女 & 卜者（魔占之径）",
    "Cavern_of_Corrosion_Path_of_Hidden_Salvation": "遗器：救世主 & 隐士（隐救之径）",
    "Cavern_of_Corrosion_Path_of_Thundersurge": "遗器：烈阳 & 船长（雳涌之径）",
    "Cavern_of_Corrosion_Path_of_Aria": "遗器：英豪 & 诗人（弦歌之径）",
    "Cavern_of_Corrosion_Path_of_Uncertainty": "遗器：司铎 & 学者（迷识之径）",
    "Cavern_of_Corrosion_Path_of_Cavalier": "遗器：铁骑 & 勇烈（勇骑之径）",
    "Cavern_of_Corrosion_Path_of_Dreamdive": "遗器：死水 & 钟表匠（梦潜之径）",
    "Cavern_of_Corrosion_Path_of_Darkness": "遗器：大公 & DoT套（幽冥之径）",
    "Cavern_of_Corrosion_Path_of_Elixir_Seekers": "遗器：莳者 & 信使（药使之径）",
    "Cavern_of_Corrosion_Path_of_Conflagration": "遗器：火套 & 虚数套（野焰之径）",
    "Cavern_of_Corrosion_Path_of_Holy_Hymn": "遗器：防御套 & 雷套（圣颂之径）",
    "Cavern_of_Corrosion_Path_of_Providence": "遗器：铁卫 & 量子套（睿治之径）",
    "Cavern_of_Corrosion_Path_of_Drifting": "遗器：治疗套 & 快枪手（漂泊之径）",
    "Cavern_of_Corrosion_Path_of_Jabbing_Punch": "遗器：物理套 & 怪盗（迅拳之径）",
    "Cavern_of_Corrosion_Path_of_Gelid_Wind": "遗器：冰套 & 风套（霜风之径）",
    "Echo_of_War_Rusted_Crypt_of_the_Iron_Carcass": "铁骸的锈冢（翁法罗斯）",
    "Echo_of_War_Glance_of_Twilight": "晨昏的回眸（翁法罗斯）",
    "Echo_of_War_Inner_Beast_Battlefield": "心兽的战场（仙舟「罗浮」）",
    "Echo_of_War_Salutations_of_Ashen_Dreams": "尘梦的赞礼（匹诺康尼）",
    "Echo_of_War_Borehole_Planet_Past_Nightmares": "蛀星的旧靥（空间站「黑塔」）",
    "Echo_of_War_Divine_Seed": "不死的神实（仙舟「罗浮」）",
    "Echo_of_War_End_of_the_Eternal_Freeze": "寒潮的落幕（雅利洛-Ⅵ）",
    "Echo_of_War_Destruction_Beginning": "毁灭的开端（空间站「黑塔」）",
    "Divergent_Universe_Gilded_Reminiscence": "饰品：朋克洛德 & 千星（鎏金追忆）",
    "Divergent_Universe_Within_the_West_Wind": "饰品：翁法罗斯 & 天国（西风丛中）",
    "Divergent_Universe_Moonlit_Blood": "饰品：妖精 & 沉醉（月下朱殷）",
    "Divergent_Universe_Unceasing_Strife": "饰品：拾骨地 & 巨树（纷争不休）",
    "Divergent_Universe_Famished_Worker": "饰品：海域 & 奇想（蠹役饥肠）",
    "Divergent_Universe_Eternal_Comedy": "饰品：奔狼 & 火宫（永恒笑剧）",
    "Divergent_Universe_To_Sweet_Dreams": "饰品：茨冈尼亚 & 出云（伴你入眠）",
    "Divergent_Universe_Pouring_Blades": "饰品：苍穹 & 匹诺康尼（天剑如雨）",
    "Divergent_Universe_Fruit_of_Evil": "饰品：繁星 & 龙骨（孽果盘生）",
    "Divergent_Universe_Permafrost": "饰品：贝洛伯格 & 萨尔索图（百年冻土）",
    "Divergent_Universe_Gentle_Words": "饰品：商业公司 & 差分机（温柔话语）",
    "Divergent_Universe_Smelted_Heart": "饰品：盗贼 & 翁瓦克（浴火钢心）",
    "Divergent_Universe_Untoppled_Walls": "饰品：太空 & 仙舟（坚城不倒）",
    "Simulated_Universe_World_3": "第三世界",
    "Simulated_Universe_World_4": "第四世界",
    "Simulated_Universe_World_5": "第五世界",
    "Simulated_Universe_World_6": "第六世界",
    "Simulated_Universe_World_8": "第八世界",
}
"""星穹铁道关卡文本索引表"""
