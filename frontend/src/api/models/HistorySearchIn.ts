/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HistorySearchIn = {
    /**
     * 合并模式
     */
    mode: HistorySearchIn.mode;
    /**
     * 开始日期, 格式YYYY-MM-DD
     */
    start_date: string;
    /**
     * 结束日期, 格式YYYY-MM-DD
     */
    end_date: string;
};
export namespace HistorySearchIn {
    /**
     * 合并模式
     */
    export enum mode {
        DAILY = 'DAILY',
        WEEKLY = 'WEEKLY',
        MONTHLY = 'MONTHLY',
    }
}

