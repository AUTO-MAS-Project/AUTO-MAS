/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWWindowPreviewIn = {
    /**
     * MaaFW 项目根目录，应包含 interface.json
     */
    path: string;
    /**
     * 指定 controller 名称；留空时扫描全部 Win32/Gamepad controller
     */
    controllerName?: (string | null);
};

