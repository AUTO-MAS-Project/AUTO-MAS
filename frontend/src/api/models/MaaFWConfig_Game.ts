/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWConfig_Game = {
    /**
     * 桌面控制器使用的实际游戏可执行文件路径
     */
    Path?: (string | null);
    /**
     * 游戏启动参数
     */
    Arguments?: (string | null);
    /**
     * 游戏启动后等待窗口就绪的时间（秒）
     */
    WaitTime?: (number | null);
    /**
     * 任务结束后是否关闭由 MAS 启动的游戏
     */
    CloseOnFinish?: (boolean | null);
};

