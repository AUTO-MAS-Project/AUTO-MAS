/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWUserConfig_Info = {
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
};

