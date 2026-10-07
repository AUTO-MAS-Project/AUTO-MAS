/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ShareAppearanceUploadOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 分享站文件 ID
     */
    fileId?: number;
    /**
     * 分享站文件标识
     */
    fileKey?: string;
    /**
     * 本次上传的版本号
     */
    versionNo?: number;
    /**
     * 审核状态, 管理员上传自动通过
     */
    reviewStatus?: ShareAppearanceUploadOut.reviewStatus;
    /**
     * 是否新建了文件
     */
    isNewFile?: boolean;
    /**
     * 外观 ID
     */
    appearanceId?: string;
    /**
     * 分享站拒绝的类别: pendingLimit 待审核数超限, conflict 新建时名称被占用或新版本内容未变, tooLarge 超过体积上限
     */
    reason?: ('pendingLimit' | 'conflict' | 'tooLarge' | null);
};
export namespace ShareAppearanceUploadOut {
    /**
     * 审核状态, 管理员上传自动通过
     */
    export enum reviewStatus {
        PENDING = 'pending',
        APPROVED = 'approved',
    }
}

