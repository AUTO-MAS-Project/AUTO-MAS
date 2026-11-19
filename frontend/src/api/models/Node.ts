/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { NodeAttributes } from './NodeAttributes';
import type { NodeDisplayStatus } from './NodeDisplayStatus';
import type { NodeSource } from './NodeSource';
export type Node = {
    sequence: number;
    node_type: string;
    text: string;
    source: NodeSource;
    timestamp?: (number | null);
    node_id?: (string | null);
    revision?: number;
    withdrawn?: boolean;
    status?: NodeDisplayStatus;
    attributes?: NodeAttributes;
};

