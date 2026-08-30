/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWConfig_Run = {
    /**
     * MaaFW 运行引擎：embedded 由 MAS 进程内 runner 直接驱动（默认）；external 启动项目自己的 UI shell。前端不暴露该开关，external 仅作为配置级自救通道保留
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
     * MaaFW 运行引擎：embedded 由 MAS 进程内 runner 直接驱动（默认）；external 启动项目自己的 UI shell。前端不暴露该开关，external 仅作为配置级自救通道保留
     */
    export enum Engine {
        EXTERNAL = 'external',
        EMBEDDED = 'embedded',
    }
}

