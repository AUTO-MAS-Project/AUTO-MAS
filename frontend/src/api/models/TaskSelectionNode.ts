/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskParams } from './TaskParams';
/**
 * 有序要求节点；队列下 uid 指队列项，直接运行时指托管。
 */
export type TaskSelectionNode = {
    uid: string;
    params?: TaskParams;
    children?: Record<string, TaskSelectionNode>;
};

