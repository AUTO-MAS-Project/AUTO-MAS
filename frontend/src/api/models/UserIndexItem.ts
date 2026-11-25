/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type UserIndexItem = {
    /**
     * 唯一标识符
     */
    uid: string;
    /**
     * 配置类型
     */
    type: UserIndexItem.type;
};
export namespace UserIndexItem {
    /**
     * 配置类型
     */
    export enum type {
        GENERAL_USER_CONFIG = 'GeneralUserConfig',
        OKWW_USER_CONFIG = 'OkwwUserConfig',
        OK_NTE_USER_CONFIG = 'OkNteUserConfig',
        MAA_END_USER_CONFIG = 'MaaEndUserConfig',
        HSRUSER_CONFIG = 'HSRUserConfig',
        BETTER_GIUSER_CONFIG = 'BetterGIUserConfig',
        ZZZ_OD_USER_CONFIG = 'ZzzOdUserConfig',
        BAAHUSER_CONFIG = 'BAAHUserConfig',
        M9AUSER_CONFIG = 'M9AUserConfig',
        MAA_USER_CONFIG = 'MaaUserConfig',
        MAA_FWUSER_CONFIG = 'MaaFWUserConfig',
        MSSUSER_CONFIG = 'MSSUserConfig',
        SRC_USER_CONFIG = 'SrcUserConfig',
        WHIMBOX_USER_CONFIG = 'WhimboxUserConfig',
    }
}

