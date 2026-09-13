/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI 一条龙配置
 */
export type BetterGIUserConfig_OneDragon = {
    /**
     * 一条龙要执行的内置配置组名列表
     */
    Groups?: (Array<string> | null);
    /**
     * 领取奖励队伍（对应一条龙 DailyRewardPartyName，留空不覆盖）
     */
    DailyRewardPartyName?: (string | null);
    /**
     * 战斗队伍（对应一条龙通用 PartyName，留空不覆盖）
     */
    PartyName?: (string | null);
    /**
     * 战斗策略（对应一条龙 AutoBossStrategyName，留空不覆盖）
     */
    AutoBossStrategyName?: (string | null);
    /**
     * 是否管理自定义配置组（总开关）
     */
    IfUseCustomGroups?: (boolean | null);
    /**
     * 自定义配置组 JSON 列表字符串，元素含 name/enabled
     */
    CustomGroups?: (string | null);
    /**
     * 一条龙可视化队列 JSON 数组字符串（按执行顺序），元素为 {kind, name}；kind ∈ builtin/js/pathing/scriptgroup/custom，允许同名重复实例
     */
    Queue?: (string | null);
    /**
     * 一条龙执行计划（Plan）JSON 字符串：{version, steps:[{uid,kind,name,enabled,settings}]}；与 Queue 并列，灰度开关 UseExecutionLayer 打开后由执行层直接消费，否则按 Queue 运行
     */
    Plan?: (string | null);
    /**
     * 是否启用「直连执行层」开关（路径 B）：打开后一条龙由 MAS 自编排 Plan 驱动、战斗 4 项直连 BetterGI 原生任务；默认开，但只有用户配置过该组且队列中启用时才接管，其余战斗组仍走原生一条龙
     */
    UseExecutionLayer?: (boolean | null);
    /**
     * 是否启用「队伍配置」（总开关）；关闭时表格数据保留，但除通用队伍外不参与匹配
     */
    IfUseTeams?: (boolean | null);
    /**
     * 队伍配置 JSON 数组字符串，按展示顺序存储，元素含 name/strategy/scenes{domain,leyline,boss}/note/enabled；序号 0 的通用队伍不落本字段（直绑 PartyName / AutoBossStrategyName）
     */
    Teams?: (string | null);
};

