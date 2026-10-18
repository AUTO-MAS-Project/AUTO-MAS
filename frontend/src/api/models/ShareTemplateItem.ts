/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ShareTemplateItem = {
    /**
     * 配置中心项目标识
     */
    projectKey: string;
    /**
     * 配置中心分类标识
     */
    categoryKey: string;
    /**
     * 配置中心配置标识
     */
    configKey: string;
    /**
     * 配置名称
     */
    displayName: string;
    /**
     * 配置描述
     */
    description?: string;
    /**
     * 分享者用户名
     */
    ownerUsername?: string;
    /**
     * 已发布的版本号
     */
    publishedVersionNo?: (number | null);
    /**
     * 发布时间
     */
    publishedAt?: string;
    /**
     * 更新时间
     */
    updatedAt?: string;
};

