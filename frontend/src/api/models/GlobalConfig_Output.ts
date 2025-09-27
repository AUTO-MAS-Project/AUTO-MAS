/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GlobalConfig_Function } from './GlobalConfig_Function';
import type { GlobalConfig_Notify } from './GlobalConfig_Notify';
import type { GlobalConfig_Start } from './GlobalConfig_Start';
import type { GlobalConfig_UI } from './GlobalConfig_UI';
import type { GlobalConfig_Update } from './GlobalConfig_Update';
import type { GlobalConfig_Voice } from './GlobalConfig_Voice';
export type GlobalConfig_Output = {
    /**
     * 功能相关配置
     */
    Function?: (GlobalConfig_Function | null);
    /**
     * 语音相关配置
     */
    Voice?: (GlobalConfig_Voice | null);
    /**
     * 启动相关配置
     */
    Start?: (GlobalConfig_Start | null);
    /**
     * 界面相关配置
     */
    UI?: (GlobalConfig_UI | null);
    /**
     * 通知相关配置
     */
    Notify?: (GlobalConfig_Notify | null);
    /**
     * 更新相关配置
     */
    Update?: (GlobalConfig_Update | null);
};

