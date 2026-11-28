/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralDevice_actionInput } from './GeneralDevice_actionInput';
import type { GeneralDevice_infoInput } from './GeneralDevice_infoInput';
import type { GeneralDevice_installationInput } from './GeneralDevice_installationInput';
export type GeneralDeviceInput = {
    info?: (GeneralDevice_infoInput | null);
    /**
     * 设备操作
     */
    action?: (GeneralDevice_actionInput | null);
    /**
     * 应用安装
     */
    installation?: (GeneralDevice_installationInput | null);
};

