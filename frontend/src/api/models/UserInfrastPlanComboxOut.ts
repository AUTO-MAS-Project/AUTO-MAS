/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { UserInfrastPlanComboxItem } from './UserInfrastPlanComboxItem';
export type UserInfrastPlanComboxOut = {
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
     * 排班表时段形态（mixed=时段不一致不可用）
     */
    state: UserInfrastPlanComboxOut.state;
    /**
     * 班次选项
     */
    data: Array<UserInfrastPlanComboxItem>;
};
export namespace UserInfrastPlanComboxOut {
    /**
     * 排班表时段形态（mixed=时段不一致不可用）
     */
    export enum state {
        PERIOD = 'period',
        ROTATE = 'rotate',
        MIXED = 'mixed',
        EMPTY = 'empty',
    }
}

