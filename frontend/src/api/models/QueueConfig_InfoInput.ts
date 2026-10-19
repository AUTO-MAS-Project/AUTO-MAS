/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type QueueConfig_InfoInput = {
    /**
     * 完成后操作
     */
    AfterAccomplish?: ('NoAction' | 'Shutdown' | 'ShutdownForce' | 'Reboot' | 'Hibernate' | 'Sleep' | 'KillSelf' | 'RestartSelf' | 'Logoff' | null);
    /**
     * 完成后操作的延时时长, 单位分钟, 0 表示队列结束后直接进入倒计时
     */
    AfterAccomplishDelay?: (number | null);
    /**
     * 是否为循环队列: 定时与循环互斥, 循环队列按队列项各自的周期持续运行
     */
    CycleEnabled?: (boolean | null);
    /**
     * 队列级运行后脚本: 运行结束后执行一次, 先于「完成后操作」
     */
    IfScriptAfterTask?: (boolean | null);
    /**
     * 队列级运行前脚本: 一次运行只执行一次, 循环队列在整个运行期间不重复执行
     */
    IfScriptBeforeTask?: (boolean | null);
    /**
     * 队列名称
     */
    Name?: (string | null);
    /**
     * 队列运行后脚本路径
     */
    ScriptAfterTask?: (string | null);
    /**
     * 队列运行前脚本路径
     */
    ScriptBeforeTask?: (string | null);
    /**
     * 是否在启动时自动运行
     */
    StartUpMode?: ('Never' | 'Always' | 'DailyFirst' | null);
    /**
     * 是否启用定时启动
     */
    TimeEnabled?: (boolean | null);
};

