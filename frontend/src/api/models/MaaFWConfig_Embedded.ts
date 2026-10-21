/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWConfig_Embedded = {
    /**
     * 导入时来源的 interface 版本
     */
    SourceVersion?: (string | null);
    /**
     * 导入时间
     */
    ImportedAt?: (string | null);
    /**
     * 投影报告 JSON 文本：省下多少、外壳家族、排除条数与原因
     */
    Report?: (string | null);
    /**
     * 跟随来源目录（开发者模式）：运行前来源目录有变化就重新导入，不做项目更新，不与同项目其它脚本共用版本
     */
    FollowSource?: (boolean | null);
};

