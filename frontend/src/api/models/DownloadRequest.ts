/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 文件需求；自定义 key 替代 URL 定位资源，内容身份仍按 rid、哈希、null 确定。
 */
export type DownloadRequest = {
    url: string;
    key?: (string | null);
    rid?: (string | null);
    content_hash?: (string | null);
    downloader?: ('builtin' | 'fluxdown' | null);
};

