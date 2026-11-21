/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRUserConfig_Info = {
    /**
     * 是否在任务后执行脚本
     */
    IfScriptAfterTask?: (boolean | null);
    /**
     * 是否在任务前执行脚本
     */
    IfScriptBeforeTask?: (boolean | null);
    /**
     * 任务后脚本路径
     */
    ScriptAfterTask?: (string | null);
    /**
     * 任务前脚本路径
     */
    ScriptBeforeTask?: (string | null);
    /**
     * 账号
     */
    Id?: (string | null);
    /**
     * 密码
     */
    Password?: (string | null);
    /**
     * 账号名称
     */
    Name?: (string | null);
    /**
     * 备注
     */
    Notes?: (string | null);
    /**
     * 剩余天数
     */
    RemainedDay?: (number | null);
    /**
     * 是否启用
     */
    Status?: (boolean | null);
    /**
     * 账号标签信息
     */
    readonly Tag?: (string | null);
    /**
     * base 来源（shared/independent/native）：shared = 共用托管级计划； independent = 本账号自己的计划；native = 原样运行 SRA / 三月七 当前的原生配置
     */
    Base?: ('shared' | 'independent' | 'native' | null);
    /**
     * 兼容字段；HSR 运行不消费此开关，不提供覆写常规配置
     */
    IfQuickConfig?: (boolean | null);
    /**
     * 游戏服务器
     */
    Resource?: (string | null);
};

