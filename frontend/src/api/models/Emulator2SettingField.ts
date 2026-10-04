/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 一个设置项的值和它的来历。
 *
 * ``state`` 必须四态分开：``.config`` 里没有 ``cpuCount`` 的实例照样跑在雷电默认的
 * 6 核上，把「默认值」显示成「已保存」就是在声称用户设过一个他没设过的值。
 */
export type Emulator2SettingField = {
    /**
     * 当前值, 未设置时为 null
     */
    value?: (number | null);
    /**
     * saved 用户保存过 / default 模拟器默认 / unset 未设置 / unreadable 读不出 / auto 每次启动按要跑的游戏定 (官方模拟器内存按游戏自动, value 为 null)
     */
    state?: string;
};

