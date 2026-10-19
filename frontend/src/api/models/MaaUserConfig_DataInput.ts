/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaUserConfig_DataInput = {
    /**
     * 剿灭达到周上限时的 ISO 周（形如 "2026-W34"）
     */
    AnnihilationCompletedWeek?: (string | null);
    /**
     * 养成接管提示（注入时写入，供前端展示接管态；空 = 未接管）
     */
    CultivateNotice?: (string | null);
    /**
     * 上次完成绿票商店购买的完整时间，按 UTC+4 判断月份；空值表示尚未完成
     */
    GreenTicketStoreMonth?: (string | null);
    /**
     * 上次成功代理时服务端的游戏资源版本，用于识别待下载的资源热更新
     */
    LastResVersion?: (string | null);
    /**
     * 理智流程升级前完整用户配置 JSON
     */
    StaminaPipelineBackup?: (string | null);
    /**
     * 理智流程配置迁移版本与升级前完整用户配置（关闭的旧计划仍可找回）
     */
    StaminaPipelineVersion?: (number | null);
};

