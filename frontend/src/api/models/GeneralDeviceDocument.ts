/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralDevice_action } from './GeneralDevice_action';
import type { GeneralDevice_info } from './GeneralDevice_info';
import type { GeneralDevice_installation } from './GeneralDevice_installation';
export type GeneralDeviceDocument = {
    info?: (GeneralDevice_info | null);
    /**
     * 设备操作
     */
    action?: (GeneralDevice_action | null);
    /**
     * 应用安装
     */
    installation?: (GeneralDevice_installation | null);
};

