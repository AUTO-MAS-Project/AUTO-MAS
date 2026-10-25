/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ScriptMirrorCdkIn = {
    /**
     * 脚本类型，决定凭据回退规则
     */
    type: string;
    /**
     * 待校验的 CDK；留空回退全局 CDK
     */
    cdk?: string;
};

