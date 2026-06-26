/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWOptionInputInfo = {
    /**
     * 输入项名称
     */
    name: string;
    /**
     * 输入项显示名称
     */
    label?: (string | null);
    /**
     * 输入项描述
     */
    description?: (string | null);
    /**
     * 输入项图标路径
     */
    icon?: (string | null);
    /**
     * 默认值
     */
    default?: (string | null);
    /**
     * pipeline 覆盖值类型
     */
    pipelineType?: (string | null);
    /**
     * 输入校验正则
     */
    verify?: (string | null);
    /**
     * 输入校验提示
     */
    verifyError?: (string | null);
    /**
     * 输入校验提示
     */
    patternMsg?: (string | null);
};

