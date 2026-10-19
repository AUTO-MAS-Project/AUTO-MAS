/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SrcUserConfig_Info = {
    /**
     * base 来源（shared=共享/independent=独立/native=原生）
     */
    Base?: ('shared' | 'independent' | 'native' | null);
    /**
     * 用户 ID
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
    Server?: ('CN-Official' | 'CN-Bilibili' | 'VN-Official' | 'OVERSEA-America' | 'OVERSEA-Asia' | 'OVERSEA-Europe' | 'OVERSEA-TWHKMO' | null);
    /**
     * 是否启用
     */
    Status?: (boolean | null);
    /**
     * 用户标签信息
     */
    readonly Tag?: (string | null);
};

