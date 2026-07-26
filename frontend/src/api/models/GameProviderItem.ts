/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GameProviderItem = {
    /**
     * provider 稳定名称
     */
    name: string;
    /**
     * provider 展示名称
     */
    displayName: string;
    /**
     * 支持的平台
     */
    platforms?: Array<'pc' | 'emulator'>;
    /**
     * 实际支持的动作
     */
    capabilities?: Array<'check' | 'install_or_update' | 'launch' | 'close'>;
    /**
     * 注册 provider 的插件实例
     */
    owner: string;
};

