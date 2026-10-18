/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWGamePackageData = {
    /**
     * 推断结果：唯一 / 没找到 / 多个互相矛盾
     */
    reason: MaaFWGamePackageData.reason;
    /**
     * 推出来的包名，仅 resolved 时非空
     */
    package?: string;
    /**
     * ambiguous 时列出全部候选，供界面提示
     */
    candidates?: Array<string>;
};
export namespace MaaFWGamePackageData {
    /**
     * 推断结果：唯一 / 没找到 / 多个互相矛盾
     */
    export enum reason {
        RESOLVED = 'resolved',
        NOT_FOUND = 'not-found',
        AMBIGUOUS = 'ambiguous',
    }
}

