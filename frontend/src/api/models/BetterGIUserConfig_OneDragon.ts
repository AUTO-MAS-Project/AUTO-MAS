/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BetterGIUserConfig_OneDragon = {
    /**
     * 一条龙要执行的内置配置组名列表
     */
    Groups?: (Array<string> | null);
    /**
     * 领取奖励队伍
     */
    DailyRewardPartyName?: (string | null);
    /**
     * 战斗队伍
     */
    PartyName?: (string | null);
    /**
     * 战斗策略
     */
    AutoBossStrategyName?: (string | null);
    /**
     * 是否管理自定义配置组（总开关）
     */
    IfUseCustomGroups?: (boolean | null);
    /**
     * 自定义配置组 JSON 列表字符串，元素含 name/enabled
     */
    CustomGroups?: (string | Array<any> | null);
};
