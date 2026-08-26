/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 直连快照元数据；原生配置正文不会进入普通用户 GET 响应。
 */
export type HSRUserConfig_Direct = {
    /**
     * SRA 导入时间
     */
    SRAImportedAt?: (string | null);
    /**
     * M7A 导入时间
     */
    M7AImportedAt?: (string | null);
    /**
     * SRA 快照来源
     */
    SRASource?: (string | null);
    /**
     * M7A 快照来源
     */
    M7ASource?: (string | null);
};

