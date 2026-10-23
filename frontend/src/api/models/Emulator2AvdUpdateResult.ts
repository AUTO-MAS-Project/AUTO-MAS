/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdUpdateResult = {
    /**
     * update 更新 / rollback 回退 / boot 新版开机确认
     */
    action: string;
    /**
     * 是否成功
     */
    ok?: boolean;
    /**
     * 涉及的版本号
     */
    version?: string;
    /**
     * 失败原因
     */
    error?: string;
};

