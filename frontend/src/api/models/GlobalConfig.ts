/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GlobalConfig_Display } from './GlobalConfig_Display';
import type { GlobalConfig_download } from './GlobalConfig_download';
import type { GlobalConfig_Function } from './GlobalConfig_Function';
import type { GlobalConfig_Notify } from './GlobalConfig_Notify';
import type { GlobalConfig_plugin } from './GlobalConfig_plugin';
import type { GlobalConfig_Replay } from './GlobalConfig_Replay';
import type { GlobalConfig_Start } from './GlobalConfig_Start';
import type { GlobalConfig_UI } from './GlobalConfig_UI';
import type { GlobalConfig_Update } from './GlobalConfig_Update';
import type { GlobalConfig_Voice } from './GlobalConfig_Voice';
export type GlobalConfig = {
    /**
     * 插件宿主
     */
    plugin?: (GlobalConfig_plugin | null);
    /**
     * 下载管理
     */
    download?: (GlobalConfig_download | null);
    Display?: (GlobalConfig_Display | null);
    Function?: (GlobalConfig_Function | null);
    Notify?: (GlobalConfig_Notify | null);
    Replay?: (GlobalConfig_Replay | null);
    Start?: (GlobalConfig_Start | null);
    UI?: (GlobalConfig_UI | null);
    Update?: (GlobalConfig_Update | null);
    Voice?: (GlobalConfig_Voice | null);
};

