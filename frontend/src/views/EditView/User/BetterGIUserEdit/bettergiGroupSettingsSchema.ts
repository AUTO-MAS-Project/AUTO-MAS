// ---- 右栏「任务设置」：内置组 → BGI 一条龙可设置字段（按任务分组）----
// 字段 key 与 BGI 一条龙 JSON 顶层 camelCase 键一致（对应 res/templates 默认配置.json）；
// 少数字段来自 BGI 全局 config.json 段（source: 'globalDomain'，见「自动秘境-刷取设置/次数与树脂」）。
export type DragonSettingField = {
  key: string
  label: string
  type: 'text' | 'number' | 'bool' | 'select' | 'multi' | 'strategy' | 'boss'
  min?: number
  max?: number
  step?: number
  /** select / multi 用：候选 */
  options?: { label: string; value: string }[]
  /** select 是否开启搜索过滤（首领等大候选集用） */
  searchable?: boolean
  /** BGI 原生灰色说明（帮助文案），渲染为 label 右侧的 help 图标 */
  help?: string
  /** bool 反向显示/写回（true=界面勾选时存 false；用于「原粹树脂耗尽模式」等反义开关） */
  invert?: boolean
  /** 数据来源：默认一条龙 per-user JSON；globalDomain/globalStygian 走 BGI 全局 config.json 段 */
  source?: 'dragon' | 'globalDomain' | 'globalStygian'
  /** 供模板 v-for key 去重：同一数据 key 可派生出多个界面字段（如互斥双开关） */
  id?: string
  /** 受控字段：仅当 masterKey 对应值 === masterValue 时可编辑（masterInvert=true 则取反判断） */
  masterKey?: string
  masterValue?: unknown
  masterInvert?: boolean
  /** 受控不可编辑时是否隐藏（默认禁用+灰显，true 则隐藏） */
  hideWhenDisabled?: boolean
}

/** 每周秘境周表行：默认（兜底）或某天，队伍/秘境/奖励/执行 key 与 BGI 一条龙顶层键一致；
    strategyKey / runKey 为 MAS 扩展（BGI 原生一条龙无 per-任务策略键与 per-天执行开关）。
    runKey 仅周一~周日行持有（default 行无此列），留空=该行不渲染执行开关 */
export type WeeklyDomainTableRow = {
  uid: string
  label: string
  partyKey: string
  strategyKey: string
  domainKey: string
  rewardKey: string
  runKey?: string
}

/** 通用周表行：仅当行内所有列都可由普通字段描述时使用（如地脉花每周刷取） */
export type WeeklyFieldTableRow = {
  uid: string
  label: string
  /** 各列字段（key 与 BGI 一条龙顶层键一致；options 用于 select 渲染） */
  fields: DragonSettingField[]
}

export type DragonSettingSection = {
  title: string
  fields: DragonSettingField[]
  /** 每周秘境表格模式、地脉花「每周刷取」表格模式、或地脉花「每日地脉花」单日统一配置模式 */
  kind?: 'weekly-table' | 'weekly-field-table' | 'daily-leyline'
  enableField?: DragonSettingField
  weeklyRows?: WeeklyDomainTableRow[]
  /** 地脉花「每周刷取」表格模式（周一~周日，列=地区/任务类型/执行） */
  weeklyFieldRows?: WeeklyFieldTableRow[]
  /** 地脉花「每日地脉花」模式：单行统一配置（队伍/策略/地区/任务类型） */
  dailyFieldRow?: WeeklyFieldTableRow
}

// ---- 地区/国家候选（与 BGI 各任务各自的下拉一致，不再共用一份）----
// 合成树脂合成台地区：BGI OneDragonFlowViewModel.CraftingBenchCountry
export const CRAFTING_BENCH_REGION_OPTIONS = [
  { label: '枫丹', value: '枫丹' },
  { label: '稻妻', value: '稻妻' },
  { label: '璃月', value: '璃月' },
  { label: '蒙德', value: '蒙德' },
]

// 领取每日奖励的冒险者协会地区：BGI AdventurersGuildCountry
export const ADVENTURERS_GUILD_REGION_OPTIONS = [
  { label: '挪德卡莱', value: '挪德卡莱' },
  { label: '枫丹', value: '枫丹' },
  { label: '稻妻', value: '稻妻' },
  { label: '璃月', value: '璃月' },
  { label: '蒙德', value: '蒙德' },
]

// 地脉花国家：BGI TaskSettingsPageViewModel.LeyLineOutcropCountryList
export const LEY_LINE_COUNTRY_OPTIONS = [
  { label: '蒙德', value: '蒙德' },
  { label: '璃月', value: '璃月' },
  { label: '稻妻', value: '稻妻' },
  { label: '须弥', value: '须弥' },
  { label: '枫丹', value: '枫丹' },
  { label: '纳塔', value: '纳塔' },
  { label: '挪德卡莱', value: '挪德卡莱' },
  { label: '至冬', value: '至冬' },
]

// 地脉花类型：BGI LeyLineOutcropTypeList（启示之花=经验书，藏金之花=摩拉）
export const LEY_LINE_TYPE_OPTIONS = [
  { label: '启示之花（经验书）', value: '启示之花' },
  { label: '藏金之花（摩拉）', value: '藏金之花' },
]

// 分解圣遗物星级：BGI TaskSettingsPageViewModel.ArtifactSalvageStarList = ["4","3","2","1"]
export const ARTIFACT_STAR_OPTIONS = [
  { label: '4', value: '4' },
  { label: '3', value: '3' },
  { label: '2', value: '2' },
  { label: '1', value: '1' },
]

// 幽境危战刷取战场：BGI AutoStygianOnslaughtConfig.BossNum = 1/2/3（三个 Boss 位）
export const STYGIAN_BOSS_NUM_OPTIONS = [
  { label: '1', value: '1' },
  { label: '2', value: '2' },
  { label: '3', value: '3' },
]

// 讨伐首领候选（按地区分组事实源）：BGI AutoBossData.CountryToBosses
// （蒙德/璃月/稻妻/须弥/枫丹/纳塔/挪德卡莱/至冬 共 44 个；至冬组为 2026-10 上游新增）。
// 上游目录是 C# 硬编码字典（无磁盘名录可扫描），新增首领需手动同步此处。
// 二级弹窗（地区 → 首领）由此目录驱动；value 存首领名（BGI AutoBossName 语义，
// 留空=不指定，由 BGI 按配置决定默认），显示「首领名称-地区」便于区分同名首领。
export const AUTO_BOSS_CATALOG: { region: string; name: string; label: string }[] = [
  // 蒙德
  { region: '蒙德', name: '急冻树', label: '急冻树-蒙德' },
  { region: '蒙德', name: '无相之雷', label: '无相之雷-蒙德' },
  { region: '蒙德', name: '守望者·堕天', label: '守望者·堕天-蒙德' },
  // 璃月
  { region: '璃月', name: '爆炎树', label: '爆炎树-璃月' },
  { region: '璃月', name: '纯水精灵', label: '纯水精灵-璃月' },
  { region: '璃月', name: '古岩龙蜥', label: '古岩龙蜥-璃月' },
  { region: '璃月', name: '无相之岩', label: '无相之岩-璃月' },
  { region: '璃月', name: '遗迹巨蛇', label: '遗迹巨蛇-璃月' },
  { region: '璃月', name: '隐山猊兽', label: '隐山猊兽-璃月' },
  // 稻妻
  { region: '稻妻', name: '无相之火', label: '无相之火-稻妻' },
  { region: '稻妻', name: '恒常机关阵列', label: '恒常机关阵列-稻妻' },
  { region: '稻妻', name: '雷音权现', label: '雷音权现-稻妻' },
  { region: '稻妻', name: '魔偶剑鬼', label: '魔偶剑鬼-稻妻' },
  { region: '稻妻', name: '无相之水', label: '无相之水-稻妻' },
  // 须弥
  { region: '须弥', name: '掣电树', label: '掣电树-须弥' },
  { region: '须弥', name: '半永恒统辖矩阵', label: '半永恒统辖矩阵-须弥' },
  { region: '须弥', name: '翠翎恐蕈', label: '翠翎恐蕈-须弥' },
  { region: '须弥', name: '风蚀沙虫', label: '风蚀沙虫-须弥' },
  { region: '须弥', name: '无相之草', label: '无相之草-须弥' },
  { region: '须弥', name: '深罪浸礼者', label: '深罪浸礼者-须弥' },
  { region: '须弥', name: '兆载永劫龙兽', label: '兆载永劫龙兽-须弥' },
  // 枫丹
  { region: '枫丹', name: '歌裴莉娅的葬送', label: '歌裴莉娅的葬送-枫丹' },
  { region: '枫丹', name: '科培琉司的劫罚', label: '科培琉司的劫罚-枫丹' },
  { region: '枫丹', name: '实验性场力发生装置', label: '实验性场力发生装置-枫丹' },
  { region: '枫丹', name: '魔像督军', label: '魔像督军-枫丹' },
  { region: '枫丹', name: '千年珍珠骏麟', label: '千年珍珠骏麟-枫丹' },
  { region: '枫丹', name: '水形幻人', label: '水形幻人-枫丹' },
  { region: '枫丹', name: '铁甲熔火帝皇', label: '铁甲熔火帝皇-枫丹' },
  // 纳塔
  { region: '纳塔', name: '金焰绒翼龙暴君', label: '金焰绒翼龙暴君-纳塔' },
  { region: '纳塔', name: '灵觉隐修的迷者', label: '灵觉隐修的迷者-纳塔' },
  { region: '纳塔', name: '秘源机兵·构型械', label: '秘源机兵·构型械-纳塔' },
  { region: '纳塔', name: '秘源机兵·统御械', label: '秘源机兵·统御械-纳塔' },
  { region: '纳塔', name: '熔岩辉龙像', label: '熔岩辉龙像-纳塔' },
  { region: '纳塔', name: '深邃摹结株', label: '深邃摹结株-纳塔' },
  { region: '纳塔', name: '贪食匿叶龙山王', label: '贪食匿叶龙山王-纳塔' },
  // 挪德卡莱
  { region: '挪德卡莱', name: '蕴光月守宫', label: '蕴光月守宫-挪德卡莱' },
  { region: '挪德卡莱', name: '深黯魇语之主', label: '深黯魇语之主-挪德卡莱' },
  { region: '挪德卡莱', name: '超重型陆巡舰·机动战垒', label: '超重型陆巡舰·机动战垒-挪德卡莱' },
  { region: '挪德卡莱', name: '霜夜巡天灵主', label: '霜夜巡天灵主-挪德卡莱' },
  { region: '挪德卡莱', name: '蕴光月幻蝶', label: '蕴光月幻蝶-挪德卡莱' },
  { region: '挪德卡莱', name: '重拳出击鸭', label: '重拳出击鸭-挪德卡莱' },
  // 至冬
  { region: '至冬', name: '不灭衍生造物', label: '不灭衍生造物-至冬' },
  { region: '至冬', name: '嵌合翼骏狮', label: '嵌合翼骏狮-至冬' },
  { region: '至冬', name: '游雪的护刃', label: '游雪的护刃-至冬' },
]

// 周日/限时奖励序号候选：与 BGI 原生下拉（SundaySelectedValueList = ["", "1", "2", "3"]）一致。
// 0 与空串在 BGI 中都表示“默认/不指定”。
// 注：每日/每周秘境均以「weekly-table」渲染（奖励联动所选秘境的物品档位），此常量保留语义注释。

// 尘歌壶进壶方式：BGI OneDragonFlowViewModel.SereniteaPotTpTypes = ["地图传送", "尘歌壶道具"]
export const SERENITEA_TP_OPTIONS = [
  { label: '地图传送', value: '地图传送' },
  { label: '尘歌壶道具', value: '尘歌壶道具' },
]

// 尘歌壶奖励对象：BGI SecretTreasureObjectList（含购买日期首项「每天重复」）
export const SECRET_TREASURE_OPTIONS = [
  { label: '每天重复', value: '每天重复' },
  { label: '布匹', value: '布匹' },
  { label: '须臾树脂', value: '须臾树脂' },
  { label: '大英雄的经验', value: '大英雄的经验' },
  { label: '流浪者的经验', value: '流浪者的经验' },
  { label: '精锻用魔矿', value: '精锻用魔矿' },
  { label: '摩拉', value: '摩拉' },
  { label: '祝圣精华', value: '祝圣精华' },
  { label: '祝圣油膏', value: '祝圣油膏' },
]

// 周一到周日（BGI JSON 里的星期键前缀与展示名）
export const WEEKDAY_KEYS = [
  { key: 'Monday', label: '周一' },
  { key: 'Tuesday', label: '周二' },
  { key: 'Wednesday', label: '周三' },
  { key: 'Thursday', label: '周四' },
  { key: 'Friday', label: '周五' },
  { key: 'Saturday', label: '周六' },
  { key: 'Sunday', label: '周日' },
]

// ---- 内置组 schema ----
// 字段 key：
//   - 默认与 BGI 一条龙 JSON 顶层键一致（PartyName/DomainName/AutoBoss*/LeyLine* 等）
//   - source:'globalDomain' 的字段对应 BetterGI 全局 config.json 段
//     （autoDomainConfig.specifyResinUse…/autoArtifactSalvageConfig.maxArtifactStar），
//     由后端按 scriptId 读写，不随用户/配置组切换。
// help 文本摘录自 BGI 界面灰字副说明，悬浮展示在字段 label 右侧。
export const BUILTIN_GROUP_SETTING_SECTIONS: Record<string, DragonSettingSection[]> = {
  合成树脂: [
    {
      title: '合成树脂',
      fields: [
        {
          key: 'CraftingBenchCountry',
          label: '合成台地区',
          type: 'select',
          options: CRAFTING_BENCH_REGION_OPTIONS,
          help: '前往指定地区合成台合成浓缩树脂',
        },
        {
          key: 'MinResinToKeep',
          label: '合成后保留原粹树脂',
          type: 'number',
          min: 0,
          max: 200,
          help: '合成浓缩树脂后保留的原粹树脂数量',
        },
      ],
    },
  ],
  自动幽境危战: [
    {
      // 刷取战场(bossNum)/战斗队伍(fightTeamName)/战斗策略(strategyName)/分解圣遗物(autoArtifactSalvage)：
      // 均存于 BGI 全局 config.json 的 autoStygianOnslaughtConfig 段（source: 'globalStygian'）。
      // 分解星级不在此配置：BGI 幽境 Param（AutoStygianOnslaughtParam）无 maxArtifactStar 参数，
      // 分解档位由全局 autoArtifactSalvageConfig 统一生效（在「自动秘境」面板配置）。
      // 队伍/策略与顶部「通用战斗队伍/策略」同段——面板非空运行时覆盖通用值，留空由通用兜底。
      title: '刷取设置',
      fields: [
        {
          key: 'bossNum',
          label: '刷取战场',
          type: 'select',
          source: 'globalStygian',
          options: STYGIAN_BOSS_NUM_OPTIONS,
          help: '选择要挑战的 Boss（1/2/3），不同编号对应幽境危战的不同战场。',
        },
        {
          key: 'fightTeamName',
          label: '战斗队伍',
          type: 'text',
          source: 'globalStygian',
          help: '填游戏内队伍名；留空不指定（由顶部「通用战斗队伍」兜底）。',
        },
        {
          key: 'strategyName',
          label: '战斗策略',
          type: 'strategy',
          source: 'globalStygian',
          help: '选择战斗策略；留空由顶部「通用战斗策略」兜底。',
        },
        {
          key: 'autoArtifactSalvage',
          label: '分解圣遗物',
          type: 'bool',
          source: 'globalStygian',
          help: '任务结束后自动分解圣遗物。',
        },
      ],
    },
    {
      // 次数与树脂：specifyResinUse=false=刷取至树脂耗尽 / true=按下方指定次数（两个互斥开关 UI）
      title: '次数与树脂',
      fields: [
        {
          id: 'stygian-exhaust',
          key: 'specifyResinUse',
          label: '刷取至树脂耗尽',
          type: 'bool',
          source: 'globalStygian',
          invert: true,
          help: '开启=刷至可用树脂耗尽后停止（与「指定树脂刷取次数」互斥）。',
        },
        {
          id: 'stygian-specify',
          key: 'specifyResinUse',
          label: '指定树脂刷取次数',
          type: 'bool',
          source: 'globalStygian',
          help: '开启=按下方指定次数刷取（与「刷取至树脂耗尽」互斥）。',
        },
        {
          key: 'originalResinUseCount',
          label: '原粹树脂刷取次数',
          type: 'number',
          source: 'globalStygian',
          min: 0,
          masterKey: 'specifyResinUse',
          masterValue: true,
          help: '指定树脂刷取次数模式下使用原粹树脂的刷取次数。',
        },
        {
          key: 'condensedResinUseCount',
          label: '浓缩树脂刷取次数',
          type: 'number',
          source: 'globalStygian',
          min: 0,
          masterKey: 'specifyResinUse',
          masterValue: true,
          help: '指定树脂刷取次数模式下使用浓缩树脂的刷取次数。',
        },
        {
          key: 'transientResinUseCount',
          label: '须臾树脂刷取次数',
          type: 'number',
          source: 'globalStygian',
          min: 0,
          masterKey: 'specifyResinUse',
          masterValue: true,
          help: '指定树脂刷取次数模式下使用须臾树脂的刷取次数。',
        },
        {
          key: 'fragileResinUseCount',
          label: '脆弱树脂刷取次数',
          type: 'number',
          source: 'globalStygian',
          min: 0,
          masterKey: 'specifyResinUse',
          masterValue: true,
          help: '指定树脂刷取次数模式下使用脆弱树脂的刷取次数。',
        },
      ],
    },
  ],
  自动地脉花: [
    {
      title: '刷取设置',
      fields: [
        {
          key: 'useAdventurerHandbook',
          label: '不使用冒险之证寻路',
          type: 'bool',
          help: '勾选后改用内置路线，不通过冒险之证定位地脉花。',
        },
        {
          key: 'LeyLineTimeout',
          label: '战斗超时(秒)',
          type: 'number',
          min: 0,
          help: '单次执行最长等待时间（秒）；0 表示不限制（使用 BetterGI 默认）。',
        },
      ],
    },
    {
      title: '次数与树脂',
      fields: [
        {
          key: 'LeyLineResinExhaustionMode',
          label: '树脂耗尽模式',
          type: 'bool',
          help: '按当前树脂与库存自动计算可刷次数，结束后自动停止。',
        },
        {
          key: 'LeyLineOpenModeCountMin',
          label: '刷取次数最小值',
          type: 'bool',
          help: '与手动次数取最小值，避免超过树脂可用次数。',
        },
        {
          key: 'LeyLineRunCount',
          label: '刷取次数',
          type: 'number',
          min: 0,
          help: '填 0 则使用独立任务配置。',
        },
        {
          key: 'useFragileResin',
          label: '使用脆弱树脂',
          type: 'bool',
          help: '原粹与浓缩耗尽后，允许使用脆弱树脂继续刷取。',
        },
        {
          key: 'useTransientResin',
          label: '使用须臾树脂',
          type: 'bool',
          help: '原粹与浓缩耗尽后，允许使用须臾树脂继续刷取。',
        },
      ],
    },
    {
      // 每日地脉花：与「每周刷取」互斥（共用 leyLineDailyEnabled 开关，invert 区分）。
      // 开启后使用每日统一的一套配置（队伍/策略/地区/任务类型/执行）。
      title: '每日地脉花',
      kind: 'daily-leyline',
      enableField: {
        key: 'leyLineDailyEnabled',
        label: '开启每日地脉花',
        type: 'bool',
        help: '开启后使用每日统一配置（队伍/策略/地区/任务类型/执行），与「每周刷取」互斥。',
      },
      fields: [
        {
          key: 'friendshipTeam',
          label: '领取前切换队伍（好感队）',
          type: 'text',
          masterKey: 'team',
          masterValue: '',
          masterInvert: true,
          help: '进入战斗前切换到该队伍，留空则不切换。必须填写战斗队伍后才能填写。',
        },
      ],
      dailyFieldRow: {
        uid: 'daily',
        label: '每日',
        fields: [
          { key: 'team', label: '队伍', type: 'text' },
          { key: 'combatStrategyPath', label: '策略', type: 'strategy' },
          { key: 'country', label: '地区', type: 'select', options: LEY_LINE_COUNTRY_OPTIONS },
          {
            key: 'leyLineOutcropType',
            label: '任务类型',
            type: 'select',
            options: LEY_LINE_TYPE_OPTIONS,
          },
        ],
      },
    },
    {
      // 每周地脉花：与「每日地脉花」互斥（共用 leyLineDailyEnabled 开关，invert 区分）。
      // 表格最前为「默认」行（无执行开关），当天某字段为空时按默认行兜底；
      // 列=队伍/策略/地区/任务类型/执行。执行开关默认关闭，全部关闭=当天不执行。
      title: '每周地脉花',
      kind: 'weekly-field-table',
      enableField: {
        key: 'leyLineDailyEnabled',
        label: '开启每周地脉花',
        type: 'bool',
        invert: true,
        help: '开启后按周一~周日分别配置，与「每日地脉花」互斥。',
      },
      fields: [
        {
          key: 'friendshipTeam',
          label: '领取前切换队伍（好感队）',
          type: 'text',
          masterKey: 'LeyLineDefaultTeam',
          masterValue: '',
          masterInvert: true,
          help: '进入战斗前切换到该队伍，留空则不切换。必须填写默认战斗队伍后才能填写。',
        },
      ],
      weeklyFieldRows: [
        {
          uid: 'default',
          label: '默认',
          fields: [
            { key: 'LeyLineDefaultTeam', label: '队伍', type: 'text' },
            { key: 'LeyLineDefaultStrategy', label: '策略', type: 'strategy' },
            {
              key: 'LeyLineDefaultCountry',
              label: '地区',
              type: 'select' as const,
              options: LEY_LINE_COUNTRY_OPTIONS,
              help: '留空时使用独立任务默认设置。',
            },
            {
              key: 'LeyLineDefaultType',
              label: '任务类型',
              type: 'select' as const,
              options: LEY_LINE_TYPE_OPTIONS,
              help: '留空时使用独立任务默认设置。',
            },
          ],
        },
        ...WEEKDAY_KEYS.map(({ key, label }) => ({
          uid: key,
          label,
          fields: [
            { key: `LeyLine${key}Team`, label: '队伍', type: 'text' as const },
            { key: `LeyLine${key}Strategy`, label: '策略', type: 'strategy' as const },
            {
              key: `LeyLine${key}Country`,
              label: '地区',
              type: 'select' as const,
              options: LEY_LINE_COUNTRY_OPTIONS,
              help: '留空时使用独立任务默认设置。',
            },
            {
              key: `LeyLine${key}Type`,
              label: '任务类型',
              type: 'select' as const,
              options: LEY_LINE_TYPE_OPTIONS,
              help: '留空时使用独立任务默认设置。',
            },
            {
              key: `LeyLineRun${key}`,
              label: '执行',
              type: 'bool' as const,
              help: '仅勾选的星期执行；未勾选则不执行。',
            },
          ],
        })),
      ],
    },
  ],
  自动秘境: [
    {
      // 分解圣遗物 / 启用奖励识别：存于 BGI 全局 config.json 段（autoDomainConfig/autoArtifactSalvageConfig）
      title: '刷取设置',
      fields: [
        {
          key: 'autoArtifactSalvage',
          label: '分解圣遗物',
          type: 'bool',
          source: 'globalDomain',
          help: '领取奖励后自动分解圣遗物。',
        },
        {
          key: 'maxArtifactStar',
          label: '分解圣遗物星级',
          type: 'select',
          source: 'globalDomain',
          options: ARTIFACT_STAR_OPTIONS,
          help: '分解的最高星级。',
        },
        {
          key: 'rewardRecognitionEnabled',
          label: '启用奖励识别',
          type: 'bool',
          source: 'globalDomain',
          help: '每轮领取后识别奖励名称与数量，任务结束打印汇总。',
        },
      ],
    },
    {
      // 次数与树脂：specifyResinUse=false=刷取至树脂耗尽 / true=按下方指定次数（两个互斥开关 UI）
      title: '次数与树脂',
      fields: [
        {
          id: 'domain-exhaust',
          key: 'specifyResinUse',
          label: '刷取至树脂耗尽',
          type: 'bool',
          source: 'globalDomain',
          invert: true,
          help: '开启=刷至可用树脂耗尽后停止（与「指定树脂刷取次数」互斥）。',
        },
        {
          id: 'domain-specify',
          key: 'specifyResinUse',
          label: '指定树脂刷取次数',
          type: 'bool',
          source: 'globalDomain',
          help: '开启=按下方指定次数刷取（与「刷取至树脂耗尽」互斥）。',
        },
        {
          key: 'originalResinUseCount',
          label: '原粹树脂刷取次数',
          type: 'number',
          source: 'globalDomain',
          min: 0,
          masterKey: 'specifyResinUse',
          masterValue: true,
          help: '指定树脂刷取次数模式下使用原粹树脂的刷取次数。',
        },
        {
          key: 'condensedResinUseCount',
          label: '浓缩树脂刷取次数',
          type: 'number',
          source: 'globalDomain',
          min: 0,
          masterKey: 'specifyResinUse',
          masterValue: true,
          help: '指定树脂刷取次数模式下使用浓缩树脂的刷取次数。',
        },
        {
          key: 'transientResinUseCount',
          label: '须臾树脂刷取次数',
          type: 'number',
          source: 'globalDomain',
          min: 0,
          masterKey: 'specifyResinUse',
          masterValue: true,
          help: '指定树脂刷取次数模式下使用须臾树脂的刷取次数。',
        },
        {
          key: 'fragileResinUseCount',
          label: '脆弱树脂刷取次数',
          type: 'number',
          source: 'globalDomain',
          min: 0,
          masterKey: 'specifyResinUse',
          masterValue: true,
          help: '指定树脂刷取次数模式下使用脆弱树脂的刷取次数。',
        },
      ],
    },
    {
      // 每日秘境：队伍/秘境/周日或限时（勾选开启每日=WeeklyDomainEnabled 存 false；
      // 关闭则使用每周秘境周表）。与每周秘境同样以下拉选秘境 + 奖励联动。
      title: '每日秘境',
      kind: 'weekly-table',
      enableField: {
        key: 'WeeklyDomainEnabled',
        label: '开启每日秘境',
        type: 'bool',
        invert: true,
        help: '开启后按下方每日设置刷取；关闭则使用每周秘境周表（下方每日项冻结）。',
      },
      fields: [],
      weeklyRows: [
        {
          uid: 'daily',
          label: '每日',
          partyKey: 'PartyName',
          strategyKey: 'StrategyName',
          domainKey: 'DomainName',
          rewardKey: 'SundayEverySelectedValue',
        },
      ],
    },
    {
      // 每周秘境：默认行 + 周一~周日（开关关闭=走每日，此时每周项冻结）
      // 以周表（周几 × 队伍/秘境/奖励）呈现；奖励列按所选秘境显示三档产出物引导，
      // 实际仍把 0~3 序号写入 SelectedValue（BGI 语义不变）。
      title: '每周秘境',
      kind: 'weekly-table',
      enableField: {
        key: 'WeeklyDomainEnabled',
        label: '启用每周秘境刷取',
        type: 'bool',
        help: '启用后，每日刷取配置将会失效（下方每周项解冻）。',
      },
      fields: [],
      weeklyRows: [
        {
          uid: 'default',
          label: '默认',
          partyKey: 'PartyName',
          strategyKey: 'StrategyName',
          domainKey: 'DomainName',
          rewardKey: 'SundayWeeklySelectedValue',
        },
        ...WEEKDAY_KEYS.map(({ key, label }) => ({
          uid: key,
          label,
          partyKey: `${key}PartyName`,
          strategyKey: `${key}StrategyName`,
          domainKey: `${key}DomainName`,
          rewardKey: `${key}SelectedValue`,
          runKey: `DomainRun${key}`,
        })),
      ],
    },
  ],
  自动首领讨伐: [
    {
      title: '刷取设置',
      fields: [
        {
          key: 'AutoBossName',
          label: '选择首领',
          type: 'boss',
          help: '部分首领因机制问题未添加。',
        },
        {
          key: 'AutoBossTeamName',
          label: '切换队伍',
          type: 'text',
          help: '留空则不更换队伍；例如：首领队。',
        },
        {
          key: 'AutoBossStrategyName',
          label: '选择战斗策略',
          type: 'strategy',
          help: '仅用于首领讨伐，不覆盖其他策略设置。',
        },
        {
          key: 'AutoBossReviveRetryCount',
          label: '角色死亡后重试次数',
          type: 'number',
          min: 0,
          help: '战斗中存在角色死亡时，复活后重新讨伐当前首领。',
        },
        {
          key: 'AutoBossReturnToStatueAfterEachRound',
          label: '每轮讨伐后返回七天神像',
          type: 'bool',
          help: '开启后每次领奖后先回血，再重新前往首领。',
        },
        {
          key: 'AutoBossRewardRecognitionEnabled',
          label: '启用奖励识别',
          type: 'bool',
          help: '每轮领取后识别奖励名称与数量，任务结束打印汇总。',
        },
        {
          key: 'AutoBossTimeout',
          label: '战斗超时（秒）',
          type: 'number',
          min: 1,
          help: '单轮战斗超时秒数，超时后按失败处理（默认 240）。',
        },
      ],
    },
    {
      title: '次数与树脂',
      fields: [
        // AutoBossSpecifyRunCount 同一布尔的两个互斥界面（参考幽境危战）：
        // 刷取至原粹树脂耗尽=界面勾选时存 false（invert）；指定讨伐次数=界面勾选时存 true。
        {
          id: 'boss-exhaust',
          key: 'AutoBossSpecifyRunCount',
          label: '刷取至原粹树脂耗尽',
          type: 'bool',
          invert: true,
          help: '开启=刷至原粹树脂耗尽后停止，下方次数与树脂冻结（与「指定讨伐次数」互斥）。',
        },
        {
          id: 'boss-specify',
          key: 'AutoBossSpecifyRunCount',
          label: '指定讨伐次数',
          type: 'bool',
          help: '开启=按下方「讨伐次数」执行（与「刷取至原粹树脂耗尽」互斥）。',
        },
        {
          key: 'AutoBossRunCount',
          label: '讨伐次数',
          type: 'number',
          min: 1,
          masterKey: 'AutoBossSpecifyRunCount',
          masterValue: true,
          help: '指定成功后按成功领取奖励次数停止。',
        },
        {
          key: 'AutoBossUseTransientResin',
          label: '原粹不足时使用须臾树脂',
          type: 'bool',
          masterKey: 'AutoBossSpecifyRunCount',
          masterValue: true,
          help: '原粹不足时使用须臾树脂补充。',
        },
        {
          key: 'AutoBossUseFragileResin',
          label: '原粹不足时使用脆弱树脂',
          type: 'bool',
          masterKey: 'AutoBossSpecifyRunCount',
          masterValue: true,
          help: '原粹不足时使用脆弱树脂补充。',
        },
      ],
    },
  ],
  领取每日奖励: [
    {
      title: '每日奖励',
      fields: [
        {
          key: 'AdventurersGuildCountry',
          label: '领取奖励的冒险者协会',
          type: 'select',
          options: ADVENTURERS_GUILD_REGION_OPTIONS,
          help: '前往指定地区冒险者协会领取。',
        },
        {
          key: 'DailyRewardPartyName',
          label: '领取前切换队伍（好感队）',
          type: 'text',
          help: '用于给指定队伍加好感度；填写好感队名称。',
        },
      ],
    },
  ],
  领取尘歌壶奖励: [
    {
      title: '尘歌壶',
      fields: [
        {
          key: 'SereniteaPotTpType',
          label: '进壶方式选择',
          type: 'select',
          options: SERENITEA_TP_OPTIONS,
          help: '地图传送=大地图直达；尘歌壶道具=使用壶道具进入。',
        },
        {
          key: 'SecretTreasureObjects',
          label: '尘歌壶奖励对象',
          type: 'multi',
          options: SECRET_TREASURE_OPTIONS,
          help: '购买日期与商品（日期不影响领取好感和钱币）。',
        },
      ],
    },
  ],
}
