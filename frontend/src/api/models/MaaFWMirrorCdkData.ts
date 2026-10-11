/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWMirrorCdkData = {
    /**
     * CDK 状态：ok / absent（没填）/ unsupported（项目没声明 mirrorchyan_rid 或读不了）/ error（查询失败）/ expired / invalid / quota / mismatched / blocked
     */
    status: string;
    /**
     * Mirror 酱返回的 CDK 到期时间（unix 秒）；没返回时为空
     */
    expiredTime?: (number | null);
};

