/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndUserConfig_Task = {
    /**
     * 任务选项覆盖
     */
    OptionOverride?: (string | null);
    /**
     * 资源配置
     */
    ResourceProfile?: ('官服' | 'B服' | null);
    /**
     * 拜访好友卡死保护模式
     */
    VisitFriendsStallProtection?: ('Disabled' | 'Enabled' | null);
    /**
     * 拜访好友超时阈值（秒）
     */
    VisitFriendsTimeoutSec?: (number | null);
};
