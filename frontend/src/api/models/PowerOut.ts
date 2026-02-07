/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type PowerOut = {
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
     * 电源操作信号
     */
    signal: PowerOut.signal;
};
export namespace PowerOut {
    /**
     * 电源操作信号
     */
    export enum signal {
        NO_ACTION = 'NoAction',
        SHUTDOWN = 'Shutdown',
        SHUTDOWN_FORCE = 'ShutdownForce',
        REBOOT = 'Reboot',
        HIBERNATE = 'Hibernate',
        SLEEP = 'Sleep',
        KILL_SELF = 'KillSelf',
    }
}

