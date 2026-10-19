/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WhimboxUserConfig_InfoInput = {
    /**
     * base 来源三态（shared=共享/independent=独立/native=原生）：共享/独立= 用 MAS 面板配置（当前运行行为一致，为后续特殊功能预留），原生=直接用奇想盒 自带配置（MAS 零写入）
     */
    Base?: ('shared' | 'independent' | 'native' | null);
    /**
     * 是否启用覆写层（快速配置，与来源独立，按账号保存，默认关）：开启时原生态 也会在任务前把面板覆盖集写入奇想盒（overlay，任务结束还原）；共享/独立态 面板本就是 base 来源，开关暂无额外消费点，为后续特殊功能预留。默认关保证 「原生=零写入」与 _write_config_or_hint 报错里「切原生绕开写入」的出路成立
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
     * 用户状态
     */
    Status?: (boolean | null);
    /**
     * 用户标签列表（JSON字符串，TagItem的dict列表）
     */
    readonly Tag?: (string | null);
};

