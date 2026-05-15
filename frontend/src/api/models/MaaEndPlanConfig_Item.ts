/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndPlanConfig_Item = {
    /**
     * 理智任务类型
     */
    SanityTaskType?: ('OperatorProgression' | 'WeaponProgression' | 'CrisisDrills' | 'Essence' | null);
    /**
     * 干员养成任务
     */
    OperatorProgression?: ('OperatorEXP' | 'Promotions' | 'T-Creds' | 'SkillUp' | null);
    /**
     * 武器养成任务
     */
    WeaponProgression?: ('WeaponEXP' | 'WeaponTune' | null);
    /**
     * 危境预演任务
     */
    CrisisDrills?: ('AdvancedProgression1' | 'AdvancedProgression2' | 'AdvancedProgression3' | 'AdvancedProgression4' | 'AdvancedProgression5' | null);
    /**
     * 奖励套组选项
     */
    RewardsSetOption?: ('RewardsSetA' | 'RewardsSetB' | null);
    /**
     * 基质刷取指定地点
     */
    AutoEssenceSpecifiedLocation?: ('VFTheHub' | 'VFOriginiumSciencePark' | 'VFOriginLodespring' | 'VFPowerPlateau' | 'WLWulingCity' | 'WLQingboStockade' | null);
};

