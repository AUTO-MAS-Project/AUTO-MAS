/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 选择私聊、全部群聊或两者。
 */
export type OpenClawQQTargetIn = {
    /**
     * 查询群列表时返回的绑定版本
     */
    bindingId: string;
    /**
     * 通知接收位置
     */
    targetType: OpenClawQQTargetIn.targetType;
};
export namespace OpenClawQQTargetIn {
    /**
     * 通知接收位置
     */
    export enum targetType {
        C2C = 'c2c',
        GROUP = 'group',
        ALL = 'all',
    }
}

