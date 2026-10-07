/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ShareAppearanceUploadIn = {
    /**
     * 本地外观 ZIP 路径
     */
    zipPath: string;
    /**
     * 外观名称
     */
    displayName: string;
    /**
     * 外观描述
     */
    description?: string;
    /**
     * 变更说明
     */
    changeNote?: string;
    /**
     * 已上传文件的 ID, 非空表示给该文件发新版本
     */
    fileId?: (number | null);
    /**
     * 封面图片路径, 为空时使用外观包 theme.json 的 preview
     */
    coverPath?: (string | null);
};

