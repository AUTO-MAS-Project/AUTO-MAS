/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 文件需求；内容身份按 rid、内容哈希、null 的顺序确定。
 */
export type DownloadRequest = {
    url: string;
    rid?: (string | null);
    content_hash?: (string | null);
    downloader?: ('builtin' | 'fluxdown' | null);
};

