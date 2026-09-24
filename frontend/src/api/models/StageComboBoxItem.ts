/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 关卡下拉选项。活动关标记属关卡语义，只挂在这里，不上跨专项共享的 ComboBoxItem
 */
export type StageComboBoxItem = {
    /**
     * 展示值
     */
    label: string;
    /**
     * 实际值
     */
    value: (string | null);
    /**
     * 是否为进行中的活动关（仅关卡下拉选项携带）
     */
    activity?: (boolean | null);
};

