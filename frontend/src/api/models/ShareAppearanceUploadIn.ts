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
     * 外观名称, 只在新建时使用
     */
    displayName?: string;
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
     * 封面图片路径, coverMode 为 custom 时使用
     */
    coverPath?: (string | null);
    /**
     * 封面来源: package 用外观包的 preview, custom 用 coverPath, inherit 沿用分享站上的封面 (只能用于新版本); 为空时有 coverPath 按 custom, 否则按 package
     */
    coverMode?: ('package' | 'custom' | 'inherit' | null);
};

