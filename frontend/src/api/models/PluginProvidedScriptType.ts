/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 已启用专项在宿主登记的配置类型及能力。
 */
export type PluginProvidedScriptType = {
    /**
     * 创建托管时使用的脚本类型标识
     */
    scriptKey: string;
    scriptConfigType: string;
    userConfigType: string;
    planConfigType?: (string | null);
    supportsGameBinding: boolean;
    /**
     * 是否支持自动代理桌面分身，单个托管的可用性由运行时检查决定
     */
    supportsDesktopSession: boolean;
    /**
     * 用户配置是否声明 Info.Id
     */
    hasAccountField: boolean;
    /**
     * 用户配置是否声明 Info.Password
     */
    hasPasswordField: boolean;
    firstAccountMode?: PluginProvidedScriptType.firstAccountMode;
    blockSurfaces?: Array<'script' | 'setup' | 'user' | 'plan'>;
};
export namespace PluginProvidedScriptType {
    export enum firstAccountMode {
        DIRECT = 'direct',
        WIZARD = 'wizard',
    }
}

