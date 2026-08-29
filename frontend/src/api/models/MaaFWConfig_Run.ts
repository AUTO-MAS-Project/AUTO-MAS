/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWConfig_Run = {
    /**
     * MaaFW 运行引擎：external 启动项目自己的 UI shell；embedded 由 MAS 进程内 runner 直接驱动（实验性，未经真机验证）
     */
    Engine?: MaaFWConfig_Run.Engine;
    /**
     * 代理次数限制
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 运行次数限制
     */
    RunTimesLimit?: (number | null);
    /**
     * 运行时间限制（分钟）
     */
    RunTimeLimit?: (number | null);
    /**
     * 每日正常完成一次后当天跳过的 MaaFW 任务名列表
     */
    DailyOnceTasks?: (string | Array<string> | null);
    /**
     * 每周正常完成一次后本周跳过的 MaaFW 任务名列表
     */
    WeeklyOnceTasks?: (string | Array<string> | null);
    /**
     * 每月正常完成一次后本月跳过的 MaaFW 任务名列表
     */
    MonthlyOnceTasks?: (string | Array<string> | null);
};
export namespace MaaFWConfig_Run {
    /**
     * MaaFW 运行引擎：external 启动项目自己的 UI shell；embedded 由 MAS 进程内 runner 直接驱动（实验性，未经真机验证）
     */
    export enum Engine {
        EXTERNAL = 'external',
        EMBEDDED = 'embedded',
    }
}

