/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MuMuDevice_action } from './MuMuDevice_action';
import type { MuMuDevice_info } from './MuMuDevice_info';
import type { MuMuDevice_installation } from './MuMuDevice_installation';
export type MuMuDeviceDocument = {
    info?: (MuMuDevice_info | null);
    /**
     * 设备操作
     */
    action?: (MuMuDevice_action | null);
    /**
     * 应用安装
     */
    installation?: (MuMuDevice_installation | null);
};

