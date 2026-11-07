/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 电源动作的统一标识；协议与持久化值保持稳定。
 */
export enum PowerSignal {
    NO_ACTION = 'NoAction',
    SHUTDOWN = 'Shutdown',
    SHUTDOWN_FORCE = 'ShutdownForce',
    REBOOT = 'Reboot',
    HIBERNATE = 'Hibernate',
    SLEEP = 'Sleep',
    KILL_SELF = 'KillSelf',
    RESTART_SELF = 'RestartSelf',
    LOGOFF = 'Logoff',
}
