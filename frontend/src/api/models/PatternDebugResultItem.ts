/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 单行/单窗口调试结果
 */
export type PatternDebugResultItem = {
    /**
     * 行号或窗口序号
     */
    idx: number;
    /**
     * 是否命中
     */
    hit: boolean;
    /**
     * 提取后的文本
     */
    extracted?: string;
    /**
     * 原始日志行（多行模式为空）
     */
    line?: string;
    /**
     * 该行/窗口的错误信息
     */
    error?: (string | null);
};

