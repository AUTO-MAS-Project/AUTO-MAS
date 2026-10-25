/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OpenClawQQGroup } from './OpenClawQQGroup';
/**
 * QQ 通知接收位置及自动记录的群。
 */
export type OpenClawQQGroupsOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 可本地化的错误标识
     */
    errorCode?: string;
    /**
     * 错误码文案里的占位符参数
     */
    errorParams?: (Record<string, any> | null);
    /**
     * 绑定版本，用于拒绝旧页面保存
     */
    bindingId?: string;
    /**
     * 通知接收位置
     */
    targetType?: OpenClawQQGroupsOut.targetType;
    /**
     * 自动记录的群
     */
    groups?: Array<OpenClawQQGroup>;
};
export namespace OpenClawQQGroupsOut {
    /**
     * 通知接收位置
     */
    export enum targetType {
        C2C = 'c2c',
        GROUP = 'group',
        ALL = 'all',
    }
}

