/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ZzzOdUserConfig_Info = {
    /**
     * base 来源（shared=共享/independent=独立/native=原生）
     */
    Base?: ('shared' | 'independent' | 'native' | null);
    /**
     * 是否启用快速配置（已封锁，仅保留字段兼容存量数据：原生来源在 load/update 归一为关，共享/独立来源不消费本开关）
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
     * 一条龙启动器选择（原生/独立两态通用）： 自动 = 优先用「上次成功」的启动器，启动失败自动换另一个重试并记住下一次 成功的那个；原始/集成 = 固定用对应启动器（对应 exe 未安装时回退可用项）
     */
    LauncherMode?: ('自动' | '原始' | '集成' | null);
    /**
     * 用户名
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
     * 任务后脚本路径
     */
    ScriptAfterTask?: (string | null);
    /**
     * 任务前脚本路径
     */
    ScriptBeforeTask?: (string | null);
    /**
     * 绑定的 zzz-od 实例槽下标（运行/配置会话内临时合成视图写回原生配置，非持久注册）：-1=未分配，首次运行或 「在一条龙内配置」时自动分配空闲 idx 并锁定该槽至会话结束， 此后配置会话与运行时注入都固定使用该槽。新槽从 MAS_SLOT_BASE（1001）起， 退到一条龙「升序找最小空号」够不到的高位段（上限 9999 与之一致放宽）
     */
    SlotIdx?: (number | null);
    /**
     * 用户状态
     */
    Status?: (boolean | null);
    /**
     * 用户标签列表（JSON字符串，TagItem的dict列表）
     */
    readonly Tag?: (string | null);
};

