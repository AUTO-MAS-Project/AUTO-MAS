/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaCopilotSourceIn = {
    source?: MaaCopilotSourceIn.source;
    /**
     * 作者、作业集或单份作业的编号/分享链接
     */
    query?: string;
    action?: MaaCopilotSourceIn.action;
};
export namespace MaaCopilotSourceIn {
    export enum source {
        ALL = 'all',
        AUTHOR = 'author',
        SET = 'set',
        COPILOT = 'copilot',
    }
    export enum action {
        LOAD = 'load',
        REFRESH = 'refresh',
        STATUS = 'status',
    }
}

