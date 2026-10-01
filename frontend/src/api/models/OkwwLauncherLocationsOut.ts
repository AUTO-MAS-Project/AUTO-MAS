/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * OK-WW 启动器解码结果（直启模式的客户端路径展示与启动均由此派生）
 */
export type OkwwLauncherLocationsOut = {
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
     * 解码得到的鸣潮客户端 exe 完整路径
     */
    client_path: string;
    /**
     * 解码得到的游戏安装目录
     */
    install_dir: string;
};

