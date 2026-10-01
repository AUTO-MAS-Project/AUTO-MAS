/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 订阅 BetterGI 脚本仓库中某个脚本的请求体。
 */
export type BetterGIScriptRepoSubscribeIn = {
    /**
     * BetterGI 脚本 ID
     */
    scriptId: string;
    /**
     * 仓库相对路径（如 js/xxx 或 pathing/xx/xx.json）
     */
    path: string;
    /**
     * 是否立即下载并落地到 BGI 原生目录。默认 False：仅写入 BGI 原生订阅清单，交由 BetterGI 下次启动时自动拉取（更轻量、无需等待下载）；True：额外下载仓库压缩包并解压拷贝到原生目录，使脚本立刻可用。
     */
    immediate?: boolean;
};

