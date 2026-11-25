/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ScriptIndexItem = {
    /**
     * 唯一标识符
     */
    uid: string;
    /**
     * 配置类型
     */
    type: ScriptIndexItem.type;
    /**
     * 对应的游戏活动标识，无游戏归属时为空
     */
    activityGame?: (string | null);
    /**
     * 所属插件当前是否可用；插件托管的插件不在已启用状态时为 false
     */
    pluginAvailable?: boolean;
    /**
     * 查询单个托管时返回当前配置是否支持桌面分身
     */
    desktopSessionSupported?: (boolean | null);
};
export namespace ScriptIndexItem {
    /**
     * 配置类型
     */
    export enum type {
        GENERAL_CONFIG = 'GeneralConfig',
        OKWW_CONFIG = 'OkwwConfig',
        OK_NTE_CONFIG = 'OkNteConfig',
        MAA_END_CONFIG = 'MaaEndConfig',
        M9ACONFIG = 'M9AConfig',
        MAA_FWCONFIG = 'MaaFWConfig',
        HSRCONFIG = 'HSRConfig',
        BETTER_GICONFIG = 'BetterGIConfig',
        ZZZ_OD_CONFIG = 'ZzzOdConfig',
        BAAHCONFIG = 'BAAHConfig',
        MSSCONFIG = 'MSSConfig',
        MAA_CONFIG = 'MaaConfig',
        WHIMBOX_CONFIG = 'WhimboxConfig',
        SRC_CONFIG = 'SrcConfig',
    }
}

