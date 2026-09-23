/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MSSUserConfig_Info = {
    /**
     * 用户名称
     */
    Name?: (string | null);
    /**
     * 是否启用
     */
    Status?: (boolean | null);
    /**
     * 剩余天数
     */
    RemainedDay?: (number | null);
    /**
     * 配置来源（用户独立、直控使用脚本原生配置）
     */
    Mode?: ('脚本' | '用户' | '直控' | null);
    /**
     * 是否启用快速配置（与配置来源独立）
     */
    IfQuickConfig?: (boolean | null);
    /**
     * 悬赏试炼关卡来源（Fixed 或计划表 UID）
     */
    PlanMode?: (string | null);
    /**
     * 活动期间是否先打活动
     */
    IfActivityFirst?: (boolean | null);
    /**
     * 周常模式
     */
    ClimbMode?: ('Close' | 'Auto' | null);
    /**
     * 周常允许开始的星期
     */
    ClimbStartWeekday?: ('Monday' | 'Tuesday' | 'Wednesday' | 'Thursday' | 'Friday' | 'Saturday' | 'Sunday' | null);
    /**
     * 周常爬塔次数
     */
    ClimbTimes?: (number | null);
    /**
     * 是否在任务前执行脚本
     */
    IfScriptBeforeTask?: (boolean | null);
    /**
     * 任务前脚本路径
     */
    ScriptBeforeTask?: (string | null);
    /**
     * 是否在任务后执行脚本
     */
    IfScriptAfterTask?: (boolean | null);
    /**
     * 任务后脚本路径
     */
    ScriptAfterTask?: (string | null);
    /**
     * 备注
     */
    Notes?: (string | null);
    /**
     * 用户标签信息
     */
    Tag?: (string | null);
};

