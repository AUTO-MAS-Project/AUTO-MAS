/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BAAHUserConfig_Info = {
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
     * BAAH 配置文件名
     */
    ConfigName?: (string | null);
    /**
     * 活动期间使用的 BAAH 配置文件名
     */
    ActivityConfigName?: (string | null);
    /**
     * 是否按碧蓝档案有没有活动切换使用的配置文件
     */
    IfActivityAdapt?: (boolean | null);
    /**
     * 活动排期按哪个服判断: JP 日服, Globle 国际服, CN 国服
     */
    ActivityLineType?: ('JP' | 'Globle' | 'CN' | null);
    /**
     * 备注
     */
    Notes?: (string | null);
    /**
     * 用户标签列表（JSON字符串，TagItem的dict列表）
     */
    Tag?: (string | null);
};

