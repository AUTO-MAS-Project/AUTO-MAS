/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BetterGIUserConfig_OneDragonInput = {
    /**
     * 战斗策略（对应 BetterGI 一条龙的 AutoBossStrategyName，留空不覆盖） 默认「根据队伍自动选择」为 BetterGI 内置策略名
     */
    AutoBossStrategyName?: (string | null);
    /**
     * 自定义配置组列表：JSON 数组字符串，元素为 {"name": str, "enabled": bool}
     */
    CustomGroups?: (string | null);
    /**
     * 领取奖励队伍（对应 BetterGI 一条龙的 DailyRewardPartyName，留空不覆盖）
     */
    DailyRewardPartyName?: (string | null);
    /**
     * 一条龙要执行的内置配置组（按组名，默认全部 8 组开启）
     */
    Groups?: (Array<string> | null);
    /**
     * 是否管理自定义配置组（总开关；OFF 时沿 BetterGI 原生设置，自定义组原样保留）
     */
    IfUseCustomGroups?: (boolean | null);
    /**
     * 「队伍配置」总开关（胶囊开关）：ON 时表格内队伍参与运行时「战斗场景」选队； OFF 时数据保留但不参与匹配（通用队伍 PartyName/AutoBossStrategyName 照旧生效）。
     */
    IfUseTeams?: (boolean | null);
    /**
     * 战斗队伍（对应 BetterGI 一条龙的通用 PartyName，留空不覆盖）
     */
    PartyName?: (string | null);
    /**
     * 一条龙执行计划（Plan）JSON 字符串：{version, steps:[{uid,kind,name,enabled,settings}]}。 战斗 4 项（自动秘境/自动地脉花/自动幽境危战/自动首领讨伐）直连执行层时由本字段 承载其 per-任务参数；右栏对应设置仅写入本字段（不落原生一条龙配置）。
     */
    Plan?: (string | null);
    /**
     * 一条龙队列（可视化编排）：JSON 数组字符串，按执行顺序存储，元素为 {"kind": str, "name": str}（kind ∈ builtin/js/pathing/scriptgroup/custom， 内置组名命中时后端强制 builtin）。仅表达顺序与成员（含同名重复实例）， 行启停仍由 Groups / CustomGroups 承载；为空或非法时回退旧行为 （按副本 TaskOrder 相对顺序，不重排）。
     */
    Queue?: (string | null);
    /**
     * 队伍配置表：JSON 数组字符串，数组顺序即界面展示顺序（可拖拽重排），元素为 {"name": str,            # 队伍名称（游戏内队伍名） "strategy": str,        # 战斗策略名（留空 = 跟随通用策略 AutoBossStrategyName） "scenes": {             # 战斗场景（可跨标签页任意叠加，空则本行不参与匹配） "domain": [{"region": str, "domain": str, "reward": str}],   # 秘境：地区/秘境名/奖励档 "leyline": [{"country": str, "type": str}],                  # 地脉花：地区/地脉类型 "boss": [{"region": str, "boss": str}]},                     # 首领讨伐：地区/首领名 "note": str,            # 备注 "enabled": bool}        # 启用状态 序号 0 的「通用队伍」不落本字段（直绑 PartyName / AutoBossStrategyName）。 运行期由 team_resolver 按 L1 精确匹配 + 随机选取，写入 Plan 步骤的 masTeamOverride / masStrategyOverride（最高优先级，压过每周行与步骤级字段）。
     */
    Teams?: (string | null);
    /**
     * 是否启用「直连执行层」：战斗 4 项由 MAS 自编排 Plan 驱动（按需求恒开，预留开关）。
     */
    UseExecutionLayer?: (boolean | null);
};

