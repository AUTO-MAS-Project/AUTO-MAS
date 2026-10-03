/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 个人版「灾变防线」这一期的状态：用户页拿它显示「本期未打 / 已打」。
 */
export type MssDefenseStatusData = {
    /**
     * 当前这一期的开始时刻；取不到官网公告时为空
     */
    period?: string;
    /**
     * 这一期认得出来吗（取不到官网公告时为 false）
     */
    known?: boolean;
    /**
     * 这一期已经打过
     */
    done?: boolean;
    /**
     * 已经排进队列、在等这一轮的结果
     */
    armed?: boolean;
    /**
     * 这一期编排过但没跑成的日子
     */
    failedDays?: Array<string>;
    /**
     * 失败日攒够了，这一期不再自动编排
     */
    givenUp?: boolean;
};

