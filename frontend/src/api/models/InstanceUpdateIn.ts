/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type InstanceUpdateIn = {
    gameId: string;
    deviceId: string;
    /**
     * 补丁：只传要改的字段；启动/关闭等 Trigger 写 True 开闸
     */
    data: Record<string, any>;
};

