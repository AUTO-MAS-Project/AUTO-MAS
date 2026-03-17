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
     * 账号
     */
    Account?: (string | null);
    /**
     * 密码
     */
    Password?: (string | null);
    /**
     * 脚本模式
     */
    Mode?: (MaaEndUserConfig_Info.Mode | null);
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
export namespace MaaEndUserConfig_Info {
    /**
     * 脚本模式
     */
    export enum Mode {
        简洁 = '简洁',
        详细 = '详细',
    }
}
