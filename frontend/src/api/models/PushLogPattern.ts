/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 推送日志采集模式配置（split/regex/multiline 三种模式按 type 区分，各模式使用对应字段）
 */
export type PushLogPattern = {
    /**
     * 匹配类型
     */
    type: PushLogPattern.type;
    /**
     * 规则标题（供分享站展示/说明）
     */
    name?: (string | null);
    /**
     * 单条规则启用/停用开关：停用时保留配置但不参与采集
     */
    enabled?: (boolean | null);
    /**
     * 日志类型：普通/失败
     */
    logType?: (string | null);
    /**
     * split 模式的匹配关键字
     */
    match?: (string | null);
    /**
     * split 模式的首部关键字
     */
    head?: (string | null);
    /**
     * split 模式是否包含首部关键字
     */
    headInclude?: (boolean | null);
    /**
     * split 模式的尾部关键字
     */
    tail?: (string | null);
    /**
     * split 模式是否包含尾部关键字
     */
    tailInclude?: (boolean | null);
    /**
     * regex 模式的提取正则（split/regex 通用）
     */
    extract?: (string | null);
    /**
     * multiline 模式的起始行正则
     */
    start?: (string | null);
    /**
     * multiline 模式的结束行正则
     */
    end?: (string | null);
    /**
     * multiline 模式的最大跨行数
     */
    maxLines?: (number | null);
};
export namespace PushLogPattern {
    /**
     * 匹配类型
     */
    export enum type {
        SPLIT = 'split',
        REGEX = 'regex',
        MULTILINE = 'multiline',
    }
}

