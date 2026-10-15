/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaUserConfig_Data = {
    /**
     * 剿灭达到周上限时的 ISO 周
     */
    AnnihilationCompletedWeek?: (string | null);
    /**
     * 上次完成绿票商店购买的月份
     */
    GreenTicketStoreMonth?: (string | null);
    /**
     * 上次成功代理时服务端的游戏资源版本
     */
    LastResVersion?: (string | null);
    /**
     * 养成接管提示（空 = 未接管）
     */
    CultivateNotice?: (string | null);
    /**
     * 理智流程配置迁移版本
     */
    StaminaPipelineVersion?: (number | null);
    /**
     * 理智流程升级前完整用户配置 JSON
     */
    StaminaPipelineBackup?: (string | null);
};

