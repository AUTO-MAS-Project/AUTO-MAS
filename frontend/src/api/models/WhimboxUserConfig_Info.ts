/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 奇想盒用户信息
 *
 * base 来源三态（#879 语义）：「脚本/用户」=共享/独立 base（MAS 面板值，当前
 * 运行行为一致、为后续特殊功能预留），「直控」=原生 base（奇想盒自带配置）；
 * 覆写层（IfQuickConfig）为账号级独立开关，开启时原生态任务前也会物化面板覆盖集。
 */
export type WhimboxUserConfig_Info = {
    /**
     * 用户名
     */
    Name?: (string | null);
    /**
     * 用户状态
     */
    Status?: (boolean | null);
    /**
     * 剩余天数
     */
    RemainedDay?: (number | null);
    /**
     * base 来源（脚本=共享/用户=独立/直控=原生）
     */
    Mode?: ('脚本' | '用户' | '直控' | null);
    /**
     * 是否启用覆写层（快速配置，与来源独立；原生态开启时任务前写入面板覆盖集、结束还原）
     */
    IfQuickConfig?: (boolean | null);
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
     * 用户标签列表（JSON字符串，TagItem的dict列表）
     */
    Tag?: (string | null);
};

