/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OptionHint } from './OptionHint';
/**
 * 单字段 UI 组件提示（无文案/宽度）。
 */
export type ComponentHint = {
    field?: string;
    component?: string;
    secret?: boolean;
    editable?: boolean;
    format?: (string | null);
    path_kind?: (string | null);
    min?: (number | null);
    max?: (number | null);
    options?: (Array<OptionHint> | null);
    multiple?: boolean;
    ordered?: boolean;
    endpoint?: (string | null);
    deps?: (Array<string> | null);
    widget?: (string | null);
};

