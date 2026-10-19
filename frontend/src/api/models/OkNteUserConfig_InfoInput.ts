/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OkNteUserConfig_InfoInput = {
    /**
     * base 来源（shared=共享、independent=独立、native=脚本原生配置）
     */
    Base?: ('shared' | 'independent' | 'native' | null);
    /**
     * 账号
     */
    Id?: (string | null);
    /**
     * 是否启用快速配置（与配置来源独立）
     */
    IfQuickConfig?: (boolean | null);
    /**
     * 是否在任务后执行脚本
     */
    IfScriptAfterTask?: (boolean | null);
    /**
     * 是否在任务前执行脚本
     */
    IfScriptBeforeTask?: (boolean | null);
    /**
     * 用户名
     */
    Name?: (string | null);
    /**
     * 备注
     */
    Notes?: (string | null);
    /**
     * 密码
     */
    Password?: (string | null);
    /**
     * 剩余天数
     */
    RemainedDay?: (number | null);
    /**
     * 游戏资源
     */
    Resource?: (string | null);
    /**
     * 任务后脚本路径
     */
    ScriptAfterTask?: (string | null);
    /**
     * 任务前脚本路径
     */
    ScriptBeforeTask?: (string | null);
    /**
     * 用户状态
     */
    Status?: (boolean | null);
    /**
     * 用户标签列表（JSON字符串，TagItem的dict列表）
     */
    readonly Tag?: (string | null);
};

