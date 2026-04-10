/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndPlanConfig_Item = {
    /**
     * 协议空间选项卡
     */
    ProtocolSpaceTab?: ('OperatorProgression' | 'WeaponProgression' | 'CrisisDrills' | null);
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
};
