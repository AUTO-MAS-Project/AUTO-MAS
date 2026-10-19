/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BAAHUserConfig_InfoInput = {
    /**
     * 活动排期按哪个服判断，供「活动关优先」使用（Kivo 时间轴的原文拼写：JP / Globle / CN）
     */
    ActivityLineType?: ('JP' | 'Globle' | 'CN' | null);
    /**
     * base 来源（shared=共享/independent=独立/native=原生）
     */
    Base?: ('shared' | 'independent' | 'native' | null);
    /**
     * 默认使用的 BAAH 配置文件名（BAAH_CONFIGS 目录下的文件名，不含 .json 后缀）
     */
    ConfigName?: (string | null);
    /**
     * 活动期间自动把「活动关卡」任务排到最前并打开
     */
    IfEventFirst?: (boolean | null);
    /**
     * 是否启用快速配置（与配置来源独立，按用户保存）
     */
    IfQuickConfig?: (boolean | null);
    /**
     * 用户名称
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
     * 关卡计划表；Fixed 表示按脚本配置
     */
    StageMode?: (string | null);
    /**
     * 是否启用
     */
    Status?: (boolean | null);
    /**
     * 用户标签信息
     */
    readonly Tag?: (string | null);
};

