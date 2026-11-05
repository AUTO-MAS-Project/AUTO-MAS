/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type M9AUserConfig_InfoInput = {
    /**
     * 账号信息，仅用于 AUTO-MAS 记录，不自动传入 MaaFW 任务
     */
    Account?: (string | null);
    /**
     * 兼容字段；MFW 运行不按 base 三态切换配置，任务来源为账号任务队列
     */
    Base?: ('shared' | 'independent' | 'native' | null);
    /**
     * MaaFW controller 名称，留空时按 interface 和设备配置自动选择
     */
    Controller?: (string | null);
    /**
     * 兼容字段；MFW 运行不消费此开关，始终使用账号任务队列
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
     * 密码信息，仅用于 AUTO-MAS 记录，不自动传入 MaaFW 任务
     */
    Password?: (string | null);
    /**
     * 剩余天数
     */
    RemainedDay?: (number | null);
    /**
     * MaaFW resource 名称，留空时选择匹配 controller 的第一个 resource
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
     * 是否启用
     */
    Status?: (boolean | null);
    /**
     * 账号标签信息
     */
    readonly Tag?: (string | null);
};

