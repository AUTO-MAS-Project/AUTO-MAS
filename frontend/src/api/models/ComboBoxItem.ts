/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ComboBoxItem = {
    /**
     * 展示值
     */
    label: string;
    /**
     * 实际值
     */
    value: (string | null);
    /**
     * 任务项支持的执行模式
     */
    supported_modes?: (Array<'AutoProxy' | 'ManualReview' | 'ScriptConfig' | 'CycleRun'> | null);
};

