/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaUserConfig_Stage = {
    /**
     * 理智药数量
     */
    MedicineNumb?: (number | null);
    /**
     * 连战次数
     */
    SeriesNumb?: ('0' | '6' | '5' | '4' | '3' | '2' | '1' | '-1' | null);
    /**
     * 主关卡
     */
    Stage?: (string | null);
    /**
     * 关卡模式（Fixed 或关卡计划表 UUID）
     */
    StageMode?: (string | null);
    /**
     * 备选关卡 1
     */
    Stage_1?: (string | null);
    /**
     * 备选关卡 2
     */
    Stage_2?: (string | null);
    /**
     * 备选关卡 3
     */
    Stage_3?: (string | null);
};

