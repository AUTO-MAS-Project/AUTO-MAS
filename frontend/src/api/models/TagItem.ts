/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 前端标签：文本 + 预置色板颜色。
 */
export type TagItem = {
    /**
     * 标签文本
     */
    text: string;
    /**
     * 标签颜色
     */
    color: TagItem.color;
};
export namespace TagItem {
    /**
     * 标签颜色
     */
    export enum color {
        RED = 'red',
        BLUE = 'blue',
        GREEN = 'green',
        YELLOW = 'yellow',
        ORANGE = 'orange',
        PURPLE = 'purple',
        PINK = 'pink',
        BROWN = 'brown',
        BLACK = 'black',
        WHITE = 'white',
        GRAY = 'gray',
        SILVER = 'silver',
        GOLD = 'gold',
    }
}

