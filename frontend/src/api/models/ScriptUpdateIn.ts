/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralConfig } from './GeneralConfig';
import type { MaaConfig } from './MaaConfig';
import type { SrcConfig } from './SrcConfig';
export type ScriptUpdateIn = {
    /**
     * 脚本ID
     */
    scriptId: string;
    /**
     * 脚本更新数据
     */
    data: (MaaConfig | SrcConfig | GeneralConfig);
};

