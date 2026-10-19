/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MSSUserConfig_Info = {
    /**
     * 账号信息，仅用于 AUTO-MAS 记录，不自动传入 MaaFW 任务
     */
    Account?: (string | null);
    /**
     * base 来源（shared=共享/independent=独立/native=原生）
     */
    Base?: ('shared' | 'independent' | 'native' | null);
    /**
     * MaaFW controller 名称，留空时按 interface 和设备配置自动选择
     */
    Controller?: (string | null);
    /**
     * 是否启用快速配置（与配置来源独立，按用户保存）
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
     * 用户名称
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
     * 用户标签信息
     */
    readonly Tag?: (string | null);
    /**
     * 活动优先：队列里没加「活动快速战斗」时，确认在活动期也自动加入，排在悬赏试炼之前
     */
    IfActivityFirst?: (boolean | null);
    /**
     * 悬赏试炼关卡来源：Fixed 用任务队列里配的，选了计划表就按当天槽位改
     */
    PlanMode?: (string | null);
};

