/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkNteConfig_GameInput } from './OkNteConfig_GameInput';
import type { OkNteConfig_InfoInput } from './OkNteConfig_InfoInput';
import type { OkNteConfig_plugin_gameInput } from './OkNteConfig_plugin_gameInput';
import type { OkNteConfig_RunInput } from './OkNteConfig_RunInput';
import type { OkNteConfig_ScriptInput } from './OkNteConfig_ScriptInput';
export type OkNteConfigInput = {
    /**
     * 游戏与设备
     */
    game?: (OkNteConfig_plugin_gameInput | null);
    Game?: (OkNteConfig_GameInput | null);
    Info?: (OkNteConfig_InfoInput | null);
    Run?: (OkNteConfig_RunInput | null);
    Script?: (OkNteConfig_ScriptInput | null);
};

