/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 奇想盒用户信息
 *
 * 配置来源只有两态：脚本=用 MAS 面板配置，直控=用奇想盒原生配置；不含「用户」
 * 态与快速配置开关（上游仅一份 config.json，「脚本」与「用户」行为一致）。
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
     * 配置来源（脚本/直控）
     */
    Mode?: ('脚本' | '直控' | null);
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

