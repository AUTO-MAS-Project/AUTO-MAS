/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 显式选择私聊或一个已发现的群。
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
    /**
     * 选择群聊时的群 OpenID
     */
    groupOpenId?: (string | null);
};
export namespace OpenClawQQTargetIn {
    /**
     * 通知接收位置
     */
    export enum targetType {
        C2C = 'c2c',
        GROUP = 'group',
    }
}

