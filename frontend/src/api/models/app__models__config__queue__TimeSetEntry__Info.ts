/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type app__models__config__queue__TimeSetEntry__Info = {
    /**
     * 是否启用
     */
    enabled?: boolean;
    /**
     * 执行周期, 可多选
     */
    days?: Array<string>;
    /**
     * 时间设置, 格式为HH:MM
     */
    time?: string;
};

