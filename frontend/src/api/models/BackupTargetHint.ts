/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BackupTargetHint = {
    editorEvents?: Array<'enter' | 'save' | 'leave'>;
    key: string;
    kind: BackupTargetHint.kind;
};
export namespace BackupTargetHint {
    export enum kind {
        USER = 'user',
        SCRIPT = 'script',
    }
}

