/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Function = {
    /**
     * 历史记录保留时间, 0表示永久保存
     */
    history_retention_time?: Function.history_retention_time;
    /**
     * 允许休眠
     */
    if_allow_sleep?: boolean;
    /**
     * 静默模式
     */
    if_silence?: boolean;
    /**
     * 同意哔哩哔哩用户协议
     */
    if_agree_bilibili?: boolean;
    /**
     * 屏蔽模拟器广告
     */
    if_block_ad?: boolean;
};
export namespace Function {
    /**
     * 历史记录保留时间, 0表示永久保存
     */
    export enum history_retention_time {
        '_7' = 7,
        '_15' = 15,
        '_30' = 30,
        '_60' = 60,
        '_90' = 90,
        '_180' = 180,
        '_365' = 365,
        '_0' = 0,
    }
}

