/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRUserConfig_InfoInput = {
    /**
     * base 来源（shared/independent/native）：shared = 共用脚本级计划； independent = 本用户自己的计划；native = 原样运行 SRA / 三月七 当前的原生配置
     */
    Base?: ('shared' | 'independent' | 'native' | null);
    /**
     * 用户 ID（账号）
     */
    Id?: (string | null);
    /**
     * 是否启用快速配置（与配置来源独立，按用户保存）
     */
    IfQuickConfig?: (boolean | null);
    /**
     * 任务后执行脚本
     */
    IfScriptAfterTask?: (boolean | null);
    /**
     * 任务前执行脚本
     */
    IfScriptBeforeTask?: (boolean | null);
    /**
     * 用户名称
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
     * 游戏服务器
     */
    Server?: (string | null);
    /**
     * 是否启用
     */
    Status?: (boolean | null);
    /**
     * 用户标签信息（虚拟字段，供前端显示）
     */
    readonly Tag?: (string | null);
};

