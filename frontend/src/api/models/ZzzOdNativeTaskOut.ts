/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 直控任务编排条目（原生 app_list 与目录合并后的可选项）。
 */
export type ZzzOdNativeTaskOut = {
    /**
     * 应用ID
     */
    app_id: string;
    /**
     * 应用中文名
     */
    app_name: string;
    /**
     * 是否启用（原生编排状态）
     */
    enabled: boolean;
    /**
     * 是否为 zzz-od 默认一条龙任务
     */
    default_group: boolean;
    /**
     * 是否支持在 MAS 侧直接配置（任务卡片 ⚙ 弹出设置）
     */
    configurable?: boolean;
    /**
     * 是否提供跳转一条龙主界面配置（复杂配置引导进原生 GUI）
     */
    jump?: boolean;
    /**
     * 原生排序权重（小者在前）
     */
    priority: number;
};

