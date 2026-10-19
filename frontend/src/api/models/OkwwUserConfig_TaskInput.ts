/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OkwwUserConfig_TaskInput = {
    /**
     * 每日任务后运行的附加任务
     */
    AdditionalTasks?: (Array<'Check Weekly Garden' | 'Auto Farm all Nightmare Nest' | 'Merge Echo If discarded > 1000' | 'Teleport and Farm 4C Echo'> | null);
    /**
     * 使用梦魇巢穴完成日常声骸
     */
    FarmNightmareNestForDailyEcho?: (boolean | null);
    /**
     * 模拟领域材料
     */
    MaterialSelection?: ('Resonator EXP' | 'Weapon EXP' | 'Shell Credit' | null);
    /**
     * 凝素领域序号
     */
    WhichForgeryChallengeToFarm?: (number | null);
    /**
     * 无音区序号
     */
    WhichTacetSuppressionToFarm?: (number | null);
    /**
     * MAS 仅接管 DailyTask 及 DailyTask 高频设置；账号切换由 MAS 侧 account_switch 实现，不再暴露上游 MultiAccountDailyTask。 每日任务体力用途
     */
    WhichToFarm?: ('Tacet Suppression' | 'Forgery Challenge' | 'Simulation Challenge' | null);
};

