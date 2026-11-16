/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BetterGIUserConfig_InfoInput = {
    /**
     * base 来源（shared=共享/independent=独立/native=原生）
     */
    Base?: ('shared' | 'independent' | 'native' | null);
    /**
     * 账号
     */
    Id?: (string | null);
    /**
     * 是否启用覆写常规配置（与配置来源独立，按账号保存）
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
     * 兼容旧版账号一条龙独立配置开关
     */
    IfUseMasConfig?: (boolean | null);
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

