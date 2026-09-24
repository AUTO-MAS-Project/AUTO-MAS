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
    /**
     * 账号信息，仅用于 AUTO-MAS 记录
     */
    Account?: (string | null);
    /**
     * 密码信息，仅用于 AUTO-MAS 记录
     */
    Password?: (string | null);
    /**
     * 用户覆盖的 MaaFW controller 名称
     */
    Controller?: (string | null);
    /**
     * 用户覆盖的 MaaFW resource 名称
     */
    Resource?: (string | null);
    /**
     * 悬赏试炼关卡来源（Fixed 或 MSS 计划表 UID）
     */
    PlanMode?: (string | null);
};

