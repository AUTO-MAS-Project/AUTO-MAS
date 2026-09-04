/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaUserConfig_Task = {
    /**
     * 开始唤醒
     */
    IfStartUp?: (boolean | null);
    /**
     * 自动公招
     */
    IfRecruit?: (boolean | null);
    /**
     * 基建换班
     */
    IfInfrast?: (boolean | null);
    /**
     * 理智作战
     */
    IfFight?: (boolean | null);
    /**
     * 信用收支
     */
    IfMall?: (boolean | null);
    /**
     * 领取奖励
     */
    IfAward?: (boolean | null);
    /**
     * 自动肉鸽
     */
    IfRoguelike?: (boolean | null);
    /**
     * 生息演算
     */
    IfReclamation?: (boolean | null);
    /**
     * 库存保持
     */
    IfDepotMaintain?: (boolean | null);
    /**
     * 绿票商店
     */
    IfGreenTicketStore?: (boolean | null);
    /**
     * 活动期间优先刷活动关
     */
    IfActivityFirst?: (boolean | null);
    /**
     * 优先刷取的活动关卡序号
     */
    ActivityStageIndex?: (number | null);
    /**
     * 活动关优先任务吃理智药数量
     */
    ActivityMedicineNumb?: (number | null);
    /**
     * 库存保持计划 JSON
     */
    DepotMaintainPlans?: (string | null);
};

