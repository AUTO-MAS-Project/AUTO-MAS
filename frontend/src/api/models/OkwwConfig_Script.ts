/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * OK-WW 脚本配置（路径/进程/日志等由 RootPath 派生，不暴露为可配置字段）
 */
export type OkwwConfig_Script = {
    /**
     * 脚本启动附加命令参数
     */
    Arguments?: (string | null);
    /**
     * 更新配置时机, 从不, 仅成功时, 仅失败时, 任务结束时
     */
    UpdateConfigMode?: ('Never' | 'Success' | 'Failure' | 'Always' | null);
};
