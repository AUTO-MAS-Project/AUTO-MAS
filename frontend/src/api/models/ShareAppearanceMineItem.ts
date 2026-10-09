/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ShareAppearanceMineItem = {
    /**
     * 分享站文件 ID
     */
    fileId: number;
    /**
     * 分享站文件标识
     */
    fileKey?: string;
    /**
     * 外观名称
     */
    displayName?: string;
    /**
     * 外观描述
     */
    description?: string;
    /**
     * 文件状态
     */
    status?: string;
    /**
     * 已发布的版本号, 没有已发布版本时为空
     */
    publishedVersionNo?: (number | null);
    /**
     * 最新版本号
     */
    latestVersionNo?: number;
    /**
     * 最新版本的审核状态
     */
    latestReviewStatus?: ('pending' | 'approved' | 'rejected' | null);
    /**
     * 最新版本的审核意见, 没有则为空
     */
    latestReviewComment?: string;
    /**
     * 最新版本是否带封面
     */
    latestHasCover?: boolean;
    /**
     * 最近更新时间
     */
    updatedAt?: string;
};

