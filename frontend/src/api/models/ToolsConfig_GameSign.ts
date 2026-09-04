/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ToolsConfig_GameSign = {
    /**
     * 是否启用游戏社区
     */
    Enabled?: (boolean | null);
    /**
     * 签到后是否发送通知
     */
    NotifyEnabled?: (boolean | null);
    /**
     * 是否启用日常便笺
     */
    ActivityEnabled?: (boolean | null);
    /**
     * 签到窗口起点 HH:mm
     */
    WindowStart?: (string | null);
    /**
     * 签到窗口终点 HH:mm
     */
    WindowEnd?: (string | null);
    /**
     * 启动时运行
     */
    RunOnStartup?: (boolean | null);
    /**
     * 定时运行
     */
    ScheduledRun?: (boolean | null);
    /**
     * 是否立即开始
     */
    AutoStart?: (boolean | null);
    /**
     * 上次签到日期
     */
    LastSignDate?: (string | null);
    /**
     * 今日计划签到时间
     */
    ScheduledTime?: (string | null);
    /**
     * 签到状态标签
     */
    Status?: (string | null);
    /**
     * 签到结果 JSON
     */
    Result?: (string | null);
};

