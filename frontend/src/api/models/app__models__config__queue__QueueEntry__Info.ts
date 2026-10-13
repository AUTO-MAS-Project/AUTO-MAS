/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type app__models__config__queue__QueueEntry__Info = {
    /**
     * 队列名称
     */
    name?: string;
    /**
     * 是否启用定时
     */
    time_enabled?: boolean;
    /**
     * 调度模式
     */
    schedule_mode?: app__models__config__queue__QueueEntry__Info.schedule_mode;
    /**
     * 启动时运行策略
     */
    start_up_mode?: app__models__config__queue__QueueEntry__Info.start_up_mode;
    /**
     * 完成后操作
     */
    after_accomplish?: app__models__config__queue__QueueEntry__Info.after_accomplish;
};
export namespace app__models__config__queue__QueueEntry__Info {
    /**
     * 调度模式
     */
    export enum schedule_mode {
        TIMED = 'timed',
        CYCLE = 'cycle',
    }
    /**
     * 启动时运行策略
     */
    export enum start_up_mode {
        NEVER = 'Never',
        ALWAYS = 'Always',
        DAILY_FIRST = 'DailyFirst',
    }
    /**
     * 完成后操作
     */
    export enum after_accomplish {
        NO_ACTION = 'NoAction',
        SHUTDOWN = 'Shutdown',
        SHUTDOWN_FORCE = 'ShutdownForce',
        REBOOT = 'Reboot',
        HIBERNATE = 'Hibernate',
        SLEEP = 'Sleep',
        KILL_SELF = 'KillSelf',
        LOGOFF = 'Logoff',
    }
}

