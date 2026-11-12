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
     * 每日任务体力用途（仅日常任务且开启覆写常规配置时生效）
     */
    WhichToFarm?: ('Tacet Suppression' | 'Forgery Challenge' | 'Simulation Challenge' | null);
};

