/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HistoryAttachment = {
    id: string;
    record_id: string;
    kind: HistoryAttachment.kind;
    role: string;
    display_name: string;
    relative_path?: (string | null);
    byte_size?: number;
    saved_via?: ('move' | 'copy' | null);
    available?: boolean;
    unavailable_reason?: (string | null);
};
export namespace HistoryAttachment {
    export enum kind {
        LOG = 'log',
        IMAGE = 'image',
        VIDEO = 'video',
        DIAGNOSTIC = 'diagnostic',
    }
}

