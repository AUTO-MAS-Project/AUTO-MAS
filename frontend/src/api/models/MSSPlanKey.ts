/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MSSPlanKey = {
    /**
     * 悬赏试炼关卡（取值见 constants.MSS_TRIBULATION_STAGES）
     */
    TribulationStage?: string;
    /**
     * 悬赏试炼是否跳过难度选择
     */
    SkipDifficulty?: boolean;
    /**
     * 悬赏试炼难度
     */
    Difficulty?: number;
    /**
     * 悬赏试炼是否消耗所有干劲
     */
    ConsumeAllEnergy?: boolean;
    /**
     * 自定义快速作战次数
     */
    FightTimes?: number;
};

