/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SrcUserConfig_Info = {
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
     * 账号 ID
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
     * base 来源（shared=共享/independent=独立/native=原生）
     */
    Base?: ('shared' | 'independent' | 'native' | null);
    /**
     * 是否启用覆写常规配置（与配置来源独立，按账号保存）
     */
    IfQuickConfig?: (boolean | null);
    /**
     * 游戏服务器（按崩穹的服务器代号取值，运行前映射为对应客户端包名）
     */
    Resource?: ('CN-Official' | 'CN-Bilibili' | 'VN-Official' | 'OVERSEA-America' | 'OVERSEA-Asia' | 'OVERSEA-Europe' | 'OVERSEA-TWHKMO' | null);
};

