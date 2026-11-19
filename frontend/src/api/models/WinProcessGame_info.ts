/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WinProcessGame_info = {
    /**
     * 实例命名
     */
    name?: (string | null);
    /**
     * 是否允许并发运行
     */
    concurrent_execution?: (boolean | null);
    /**
     * 游戏可执行文件
     */
    path?: (string | null);
    /**
     * 启动器路径，留空直接启动游戏
     */
    launch_path?: (string | null);
    /**
     * 已设置启动器时通过启动器启动
     */
    launch_with_launcher?: (boolean | null);
    /**
     * 启动参数
     */
    arguments?: (Array<string> | null);
    /**
     * 工作目录，留空使用启动程序所在目录
     */
    working_directory?: (string | null);
    /**
     * 操作最大等待时间（秒）
     */
    wait_time?: (number | null);
    /**
     * 关闭时强制结束目标进程
     */
    force_kill?: (boolean | null);
};

