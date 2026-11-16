/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndProtocolSpacePlanKey = {
    /**
     * 协议空间任务类型
     */
    SanityTaskType?: MaaEndProtocolSpacePlanKey.SanityTaskType;
    /**
     * 干员养成任务
     */
    OperatorProgression?: MaaEndProtocolSpacePlanKey.OperatorProgression;
    /**
     * 武器养成任务
     */
    WeaponProgression?: MaaEndProtocolSpacePlanKey.WeaponProgression;
    /**
     * 危境预演任务，由 MaaEnd 声明
     */
    CrisisDrills?: string;
    /**
     * 奖励组选项
     */
    RewardsSetOption?: MaaEndProtocolSpacePlanKey.RewardsSetOption;
};
export namespace MaaEndProtocolSpacePlanKey {
    /**
     * 协议空间任务类型
     */
    export enum SanityTaskType {
        OPERATOR_PROGRESSION = 'OperatorProgression',
        WEAPON_PROGRESSION = 'WeaponProgression',
        CRISIS_DRILLS = 'CrisisDrills',
    }
    /**
     * 干员养成任务
     */
    export enum OperatorProgression {
        OPERATOR_EXP = 'OperatorEXP',
        PROMOTIONS = 'Promotions',
        T_CREDS = 'T-Creds',
        SKILL_UP = 'SkillUp',
    }
    /**
     * 武器养成任务
     */
    export enum WeaponProgression {
        WEAPON_EXP = 'WeaponEXP',
        WEAPON_TUNE = 'WeaponTune',
    }
    /**
     * 奖励组选项
     */
    export enum RewardsSetOption {
        REWARDS_SET_A = 'RewardsSetA',
        REWARDS_SET_B = 'RewardsSetB',
    }
}

