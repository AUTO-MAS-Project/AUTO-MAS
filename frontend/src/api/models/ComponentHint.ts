/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OptionHint } from './OptionHint';
import type { PathKind } from './PathKind';
import type { TriggerUiState } from './TriggerUiState';
/**
 * 单字段 UI 组件提示，可附带字段说明。
 */
export type ComponentHint = {
    field?: string;
    description?: (string | null);
    component?: string;
    secret?: boolean;
    editable?: boolean;
    state?: TriggerUiState;
    masked?: boolean;
    format?: (string | null);
    path_kind?: (PathKind | null);
    path_extensions?: Array<string>;
    path_must_exist?: boolean;
    min?: (number | null);
    max?: (number | null);
    precision?: number;
    step?: number;
    options?: (Array<OptionHint> | null);
    multiple?: boolean;
    ordered?: boolean;
    endpoint?: (string | null);
    option_source?: string;
    depends_on?: Record<string, string>;
    action_ref?: string;
    plan_type?: string;
    deps?: (Array<string> | null);
    widget?: (string | null);
};

