/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 选择通知位置并可选更新群控制成员白名单。
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
     * 群控制成员 OpenID 白名单；省略保持现值，空列表允许所有成员
     */
    groupCommandWhitelist?: (Array<string> | null);
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

