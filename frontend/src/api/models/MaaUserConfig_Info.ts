/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaUserConfig_Info = {
    /**
     * 用户名
     */
    Name?: (string | null);
    /**
     * 用户ID
     */
    Id?: (string | null);
    /**
     * 用户配置模式
     */
    Mode?: ('简洁' | '详细' | null);
    /**
     * 关卡配置模式
     */
    StageMode?: (string | null);
    /**
     * 服务器
     */
    Server?: ('Official' | 'Bilibili' | 'YoStarEN' | 'YoStarJP' | 'YoStarKR' | 'txwy' | null);
    /**
     * 用户状态
     */
    Status?: (boolean | null);
    /**
     * 剩余天数
     */
    RemainedDay?: (number | null);
    /**
     * 剿灭模式
     */
    Annihilation?: ('Close' | 'Annihilation' | 'Chernobog@Annihilation' | 'LungmenOutskirts@Annihilation' | 'LungmenDowntown@Annihilation' | null);
    /**
     * 是否启用日常
     */
    Routine?: (boolean | null);
    /**
     * 基建模式
     */
    InfrastMode?: ('Normal' | 'Rotation' | 'Custom' | null);
    /**
     * 自定义基建文件路径
     */
    InfrastPath?: (string | null);
    /**
     * 密码
     */
    Password?: (string | null);
    /**
     * 备注
     */
    Notes?: (string | null);
    /**
     * 吃理智药数量
     */
    MedicineNumb?: (number | null);
    /**
     * 连战次数
     */
    SeriesNumb?: ('0' | '6' | '5' | '4' | '3' | '2' | '1' | '-1' | null);
    /**
     * 关卡选择
     */
    Stage?: (string | null);
    /**
     * 备选关卡 - 1
     */
    Stage_1?: (string | null);
    /**
     * 备选关卡 - 2
     */
    Stage_2?: (string | null);
    /**
     * 备选关卡 - 3
     */
    Stage_3?: (string | null);
    /**
     * 剩余理智关卡
     */
    Stage_Remain?: (string | null);
    /**
     * 是否启用森空岛签到
     */
    IfSkland?: (boolean | null);
    /**
     * SklandToken
     */
    SklandToken?: (string | null);
};

