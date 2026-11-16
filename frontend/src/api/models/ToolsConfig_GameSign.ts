/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ToolsConfig_GameSign = {
    /**
     * GameSign - 启用日常便笺
     */
    ActivityEnabled?: (boolean | null);
    /**
     * GameSign - 是否立即开始
     */
    AutoStart?: (boolean | null);
    /**
     * GameSign - 启用签到
     */
    Enabled?: (boolean | null);
    /**
     * GameSign - 上次签到日期 (防止重复触发)
     */
    LastSignDate?: (string | null);
    /**
     * GameSign - 签到后发送通知
     */
    NotifyEnabled?: (boolean | null);
    /**
     * GameSign - 签到结果详情 (虚拟字段)
     */
    readonly Result?: (string | null);
    /**
     * GameSign - 启动时运行
     */
    RunOnStartup?: (boolean | null);
    /**
     * GameSign - 签到状态标签 (虚拟字段)
     */
    readonly Status?: (string | null);
};

