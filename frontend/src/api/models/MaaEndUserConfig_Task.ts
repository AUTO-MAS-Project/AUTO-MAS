/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndUserConfig_Task = {
    /**
     * 理智任务类型
     */
    SanityTaskType?: ('OperatorProgression' | 'WeaponProgression' | 'CrisisDrills' | 'Essence' | null);
    /**
     * 干员养成任务
     */
    OperatorProgression?: ('OperatorEXP' | 'Promotions' | 'T-Creds' | 'SkillUp' | null);
    /**
     * 武器养成任务
     */
    WeaponProgression?: ('WeaponEXP' | 'WeaponTune' | null);
    /**
     * 危境预演任务
     */
    CrisisDrills?: ('AdvancedProgression1' | 'AdvancedProgression2' | 'AdvancedProgression3' | 'AdvancedProgression4' | 'AdvancedProgression5' | null);
    /**
     * 奖励组选项
     */
    RewardsSetOption?: ('RewardsSetA' | 'RewardsSetB' | null);
    /**
     * 基质刷取指定地点
     */
    AutoEssenceSpecifiedLocation?: ('VFTheHub' | 'VFOriginiumSciencePark' | 'VFOriginLodespring' | 'VFPowerPlateau' | 'WLWulingCity' | 'WLQingboStockade' | 'WLMarkerStone' | null);
    /**
     * 理智任务
     */
    IfSanity?: (boolean | null);
    /**
     * 应急理智加强剂
     */
    IfAutoUseSpMedication?: (boolean | null);
    /**
     * 基建任务
     */
    IfDijiangRewards?: (boolean | null);
    /**
     * 转交委托
     */
    IfDeliveryJobs?: (boolean | null);
    /**
     * 售卖产品
     */
    IfSellProduct?: (boolean | null);
    /**
     * 自动囤货
     */
    IfAutoStockpile?: (boolean | null);
    /**
     * 购买稳定物资
     */
    IfAutoStockStaple?: (boolean | null);
    /**
     * 拜访好友
     */
    IfVisitFriends?: (boolean | null);
    /**
     * 信用点购物
     */
    IfCreditShoppingN2?: (boolean | null);
    /**
     * 抢委托
     */
    IfSeizeEntrustTask?: (boolean | null);
    /**
     * 生态农场
     */
    IfAutoEcoFarm?: (boolean | null);
    /**
     * 售卖弹性物资
     */
    IfAutoSell?: (boolean | null);
    /**
     * 环境监测
     */
    IfEnvironmentMonitoring?: (boolean | null);
    /**
     * 自动采集
     */
    IfAutoCollect?: (boolean | null);
    /**
     * 日常奖励领取
     */
    IfDailyRewards?: (boolean | null);
    /**
     * 资源回收站
     */
    IfResourceRecycleStation?: (boolean | null);
};

