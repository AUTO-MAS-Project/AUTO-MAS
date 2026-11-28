/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WhimboxUserConfig_DataInput } from './WhimboxUserConfig_DataInput';
import type { WhimboxUserConfig_gameInput } from './WhimboxUserConfig_gameInput';
import type { WhimboxUserConfig_InfoInput } from './WhimboxUserConfig_InfoInput';
import type { WhimboxUserConfig_NotifyInput } from './WhimboxUserConfig_NotifyInput';
import type { WhimboxUserConfig_OneDragonInput } from './WhimboxUserConfig_OneDragonInput';
import type { WhimboxUserConfig_plugin_infoInput } from './WhimboxUserConfig_plugin_infoInput';
import type { WhimboxUserConfig_plugin_notifyInput } from './WhimboxUserConfig_plugin_notifyInput';
import type { WhimboxUserConfig_TaskInput } from './WhimboxUserConfig_TaskInput';
export type WhimboxUserConfigInput = {
    /**
     * 游戏与设备
     */
    game?: (WhimboxUserConfig_gameInput | null);
    info?: (WhimboxUserConfig_plugin_infoInput | null);
    /**
     * 用户通知
     */
    notify?: (WhimboxUserConfig_plugin_notifyInput | null);
    Data?: (WhimboxUserConfig_DataInput | null);
    Info?: (WhimboxUserConfig_InfoInput | null);
    Notify?: (WhimboxUserConfig_NotifyInput | null);
    OneDragon?: (WhimboxUserConfig_OneDragonInput | null);
    Task?: (WhimboxUserConfig_TaskInput | null);
};

