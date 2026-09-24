/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ComboBoxItem } from './ComboBoxItem';
export type MaaEndAutoCollectGroup = {
    /**
     * 上游路线选项名
     */
    value: string;
    /**
     * 采集分类展示名
     */
    label: string;
    /**
     * 上游地区开关名，旧版为空
     */
    region: string;
    /**
     * 地区展示名
     */
    regionLabel: string;
    /**
     * 用户路线配置字段
     */
    configKey: MaaEndAutoCollectGroup.configKey;
    /**
     * 该分类的动态路线
     */
    options: Array<ComboBoxItem>;
    /**
     * 上游默认路线
     */
    defaultCases: Array<string>;
};
export namespace MaaEndAutoCollectGroup {
    /**
     * 用户路线配置字段
     */
    export enum configKey {
        AUTO_COLLECT_ROUTES = 'AutoCollectRoutes',
        AUTO_COLLECT_COMMON_ROUTES = 'AutoCollectCommonRoutes',
    }
}

