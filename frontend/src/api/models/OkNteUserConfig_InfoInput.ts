/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OkNteUserConfig_InfoInput = {
    /**
     * 固定配置或 OkNte 计划表
     */
    PlanMode?: (string | null);
    /**
     * base 来源（shared=共享、independent=独立、native=脚本原生配置）
     */
    Base?: ('shared' | 'independent' | 'native' | null);
    /**
     * 账号
     */
    Id?: (string | null);
    /**
     * 是否启用覆写常规配置（与配置来源独立）
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
     * 账号名称
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
     * 账号状态
     */
    Status?: (boolean | null);
    /**
     * 账号标签列表（JSON字符串，TagItem的dict列表）
     */
    readonly Tag?: (string | null);
};

