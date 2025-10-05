/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type PowerIn = {
  /**
   * 电源操作信号
   */
  signal: PowerIn.signal
}
export namespace PowerIn {
  /**
   * 电源操作信号
   */
  export enum signal {
    NO_ACTION = 'NoAction',
    SHUTDOWN = 'Shutdown',
    SHUTDOWN_FORCE = 'ShutdownForce',
    HIBERNATE = 'Hibernate',
    SLEEP = 'Sleep',
    KILL_SELF = 'KillSelf',
  }
}
