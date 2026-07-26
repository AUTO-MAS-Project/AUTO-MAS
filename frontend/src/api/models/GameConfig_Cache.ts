/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GameConfig_Cache = {
    /**
     * 本地版本
     */
    LocalVersion?: string;
    /**
     * provider 报告的最新版本
     */
    LatestVersion?: string;
    /**
     * 是否存在可用更新
     */
    NeedsUpdate?: boolean;
    /**
     * 是否已安装
     */
    Installed?: boolean;
    /**
     * 最后检查时间
     */
    LastChecked?: (string | null);
};

