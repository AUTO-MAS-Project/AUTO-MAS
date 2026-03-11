/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SrcUserConfig_Info = {
    /**
     * 用户名称
     */
    Name?: (string | null);
    /**
     * 是否启用
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
     * 脚本模式
     */
    Mode?: ('简洁' | '详细' | null);
    /**
     * 游戏服务器
     */
    Server?: ('CN-Official' | 'CN-Bilibili' | 'VN-Official' | 'OVERSEA-America' | 'OVERSEA-Asia' | 'OVERSEA-Europe' | 'OVERSEA-TWHKMO' | null);
    /**
     * 剩余天数
     */
    RemainedDay?: (number | null);
    /**
     * 备注
     */
    Notes?: (string | null);
    /**
     * 用户标签信息
     */
    Tag?: (string | null);
};

