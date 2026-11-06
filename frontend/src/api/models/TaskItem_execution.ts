/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TaskItem_execution = {
    /**
     * 本轮运行前脚本
     */
    script_before?: (string | null);
    /**
     * 本轮运行后脚本
     */
    script_after?: (string | null);
    /**
     * 本轮完成后操作
     */
    after_accomplish?: ('NoAction' | 'Shutdown' | 'ShutdownForce' | 'Reboot' | 'Hibernate' | 'Sleep' | 'KillSelf' | 'RestartSelf' | 'Logoff' | null);
    /**
     * 完成后操作延时，单位分钟
     */
    after_accomplish_delay?: (number | null);
};
