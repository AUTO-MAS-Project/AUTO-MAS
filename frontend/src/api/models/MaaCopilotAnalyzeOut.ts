/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaCopilotAssignment } from './MaaCopilotAssignment';
import type { MaaCopilotOperator } from './MaaCopilotOperator';
export type MaaCopilotAnalyzeOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    bindingKey?: string;
    total?: number;
    analyzable?: number;
    ready?: number;
    trainable?: number;
    projectedReady?: number;
    missing?: number;
    unknown?: number;
    stageCount?: number;
    capturedAt?: number;
    updatedAt?: number;
    operators?: Array<MaaCopilotOperator>;
    assignments?: Array<MaaCopilotAssignment>;
};

