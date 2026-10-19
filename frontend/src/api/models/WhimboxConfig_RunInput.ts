/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WhimboxConfig_RunInput = {
    /**
     * 单账号运行总时限（分钟），包含等待和全部重试
     */
    HardTimeLimit?: (number | null);
    /**
     * 每日代理次数上限（0=不限）
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 运行超时（分钟）：日志静默超过该时长判定卡死
     */
    RunTimeLimit?: (number | null);
    /**
     * 失败重试次数：只用于「没有上游结论」的异常（进程提前退出/卡死）； 上游自己判负时，仅当失败原因与上一轮不同才继续重试（同一结论连着出现即收口）
     */
    RunTimesLimit?: (number | null);
    /**
     * 以管理员权限启动奇想盒后端（上游强制管理员，缺权限会在起跑即退出； MAS 自身已提权时不重复触发 UAC，子进程自动继承管理员令牌）
     */
    UseAdmin?: (boolean | null);
};

