/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndUserConfig_Info = {
    /**
     * 用户名
     */
    Name?: (string | null);
    /**
     * 用户状态
     */
    Status?: (boolean | null);
    /**
     * 用户ID
     */
    Id?: (string | null);
    /**
     * 密码
     */
    Password?: (string | null);
    /**
     * 配置文件来源
     */
    Mode?: ('简洁' | '详细' | null);
    /**
     * 是否启用快速配置
     */
    IfQuickConfig?: (boolean | null);
    /**
     * 理智任务配置模式
     */
    SanityMode?: (string | null);
    /**
     * 资源名称
     */
    Resource?: (string | null);
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
     * 是否启用森空岛签到
     */
    IfSkland?: (boolean | null);
    /**
     * SklandToken
     */
    SklandToken?: (string | null);
    /**
     * 用户标签信息
     */
    Tag?: (string | null);
};

