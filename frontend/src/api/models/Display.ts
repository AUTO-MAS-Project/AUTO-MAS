/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Display = {
    /**
     * 自动保障桌面显示输出
     */
    if_enable_virtual_display?: boolean;
    /**
     * 虚拟显示器模式
     */
    virtual_display_mode?: Display.virtual_display_mode;
};
export namespace Display {
    /**
     * 虚拟显示器模式
     */
    export enum virtual_display_mode {
        _1920X1080_60 = '1920x1080@60',
        _1920X1080_30 = '1920x1080@30',
    }
}

