/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndUserConfig_Info = {
    /**
     * 用户名
     */
    Name?: (string | null);
    /**
     * 用户状态
     */
    Status?: (boolean | null);
    /**
     * 用户ID
     */
    Id?: (string | null);
    /**
     * 密码
     */
    Password?: (string | null);
    /**
     * 配置模式
     */
    Mode?: ('简洁' | '详细' | null);
    /**
     * 资源名称
     */
    Resource?: (string | null);
    /**
     * 剩余天数
     */
    RemainedDay?: (number | null);
    /**
     * 备注
     */
    Notes?: (string | null);
    /**
     * 是否启用森空岛签到
     */
    IfSkland?: (boolean | null);
    /**
     * SklandToken
     */
    SklandToken?: (string | null);
    /**
     * 用户标签信息
     */
    Tag?: (string | null);
};

