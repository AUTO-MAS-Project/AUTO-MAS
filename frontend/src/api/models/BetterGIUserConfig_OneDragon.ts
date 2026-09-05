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
};

