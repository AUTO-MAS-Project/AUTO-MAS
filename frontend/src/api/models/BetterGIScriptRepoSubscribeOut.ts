/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 订阅 BetterGI 脚本仓库中某个脚本的结果。
 */
export type BetterGIScriptRepoSubscribeOut = {
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
    /**
     * 写入订阅清单的相对路径
     */
    subscribed?: (string | null);
    /**
     * 原生目标目录绝对路径（仅立即落地时有值）
     */
    nativePath?: (string | null);
    /**
     * 原生目录订阅前是否已存在
     */
    alreadyExisted?: (boolean | null);
    /**
     * 本次是否执行了从仓库压缩包的拷贝
     */
    copied?: (boolean | null);
    /**
     * 本次是否执行了下载落地（False 表示仅写入订阅清单）
     */
    immediate?: (boolean | null);
};

