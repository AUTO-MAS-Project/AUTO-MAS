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
     * 配置来源（脚本/用户/直控）
     */
    Mode?: ('脚本' | '用户' | '直控' | null);
    /**
     * 是否启用快速配置（与配置来源独立）
     */
    IfQuickConfig?: (boolean | null);
    /**
     * 默认使用的 BAAH 配置文件名
     */
    ConfigName?: (string | null);
    /**
     * 关卡计划表；Fixed 表示按脚本配置
     */
    StageMode?: (string | null);
    /**
     * 活动排期按哪个服判断: JP 日服, Globle 国际服, CN 国服
     */
    ActivityLineType?: ('JP' | 'Globle' | 'CN' | null);
    /**
     * 活动期间把活动关卡排到最前
     */
    IfEventFirst?: (boolean | null);
    /**
     * 备注
     */
    Notes?: (string | null);
    /**
     * 用户标签列表（JSON字符串，TagItem的dict列表）
     */
    Tag?: (string | null);
};

