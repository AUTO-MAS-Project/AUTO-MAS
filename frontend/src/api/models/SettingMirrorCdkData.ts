/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SettingMirrorCdkData = {
    /**
     * CDK 状态：ok / absent / error / expired / invalid / quota / mismatched / blocked
     */
    status: string;
    /**
     * CDK 到期时间（unix 秒）；未返回时为空
     */
    expiredTime?: (number | null);
};

