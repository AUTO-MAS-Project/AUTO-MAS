/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaUserConfig_TaskInput = {
    /**
     * 活动关优先任务吃理智药数量
     */
    ActivityMedicineNumb?: (number | null);
    /**
     * 优先刷取的活动关卡序号
     */
    ActivityStageIndex?: (number | null);
    /**
     * 剿灭模式
     */
    Annihilation?: ('Close' | 'Annihilation' | 'Chernobog@Annihilation' | 'LungmenOutskirts@Annihilation' | 'LungmenDowntown@Annihilation' | null);
    /**
     * 剿灭开始星期
     */
    AnnihilationStartWeekday?: ('Monday' | 'Tuesday' | 'Wednesday' | 'Thursday' | 'Friday' | 'Saturday' | 'Sunday' | null);
    /**
     * 是否注入 MAA 原生干员培养任务
     */
    CultivateAutoRaise?: (boolean | null);
    /**
     * 活动期间是否跳过养成计划
     */
    CultivateSkipDuringActivity?: (boolean | null);
    /**
     * 资源收集期是否跳过养成计划
     */
    CultivateSkipDuringResourceCollection?: (boolean | null);
    /**
     * 预计材料时间是否计入月卡每日额外 80 理智，仅用于估算
     */
    CultivateMonthlyCard?: (boolean | null);
    /**
     * 森空岛绑定：签到账号组 UUID（凭据引用，凭据本体只存签到域）
     */
    CultivateSklandAccount?: (string | null);
    /**
     * 森空岛绑定：绑定角色的游戏 uid（非森空岛 userId）
     */
    CultivateSklandUid?: (string | null);
    /**
     * 普通库存保持每条计划使用理智药数量；留空沿用 MAA 配置
     */
    DepotMaintainMedicineNumb?: (number | null);
    /**
     * 普通库存保持每条计划使用源石数量；留空沿用 MAA 配置
     */
    DepotMaintainStoneNumb?: (number | null);
    /**
     * 干员养成每条计划使用理智药数量；留空沿用 MAA 配置
     */
    CultivateMedicineNumb?: (number | null);
    /**
     * 干员养成每条计划使用源石数量；留空沿用 MAA 配置
     */
    CultivateStoneNumb?: (number | null);
    /**
     * 干员养成目标
     */
    CultivateTargets?: (string | null);
    /**
     * 库存保持计划（快速配置面板维护；MAA 侧同名 PlanList 为透传载体）
     */
    DepotMaintainPlans?: (string | null);
    /**
     * 活动库存保持计划，保存材料关序号及目标库存，运行时解析当前活动
     */
    EventDepotMaintainPlans?: (string | null);
    /**
     * 活动库存保持每条计划使用理智药数量；留空沿用 MAA 配置
     */
    EventDepotMaintainMedicineNumb?: (number | null);
    /**
     * 活动库存保持每条计划使用源石数量；留空沿用 MAA 配置
     */
    EventDepotMaintainStoneNumb?: (number | null);
    /**
     * 活动期间是否优先刷活动关
     */
    IfActivityFirst?: (boolean | null);
    /**
     * 是否领取奖励
     */
    IfAward?: (boolean | null);
    /**
     * 是否干员养成
     */
    IfCultivate?: (boolean | null);
    /**
     * 是否库存保持
     */
    IfDepotMaintain?: (boolean | null);
    /**
     * 是否启用活动关均衡理智
     */
    IfEventDepotMaintain?: (boolean | null);
    /**
     * 是否理智作战
     */
    IfFight?: (boolean | null);
    /**
     * 是否每月自动购买一次绿票商店
     */
    IfGreenTicketStore?: (boolean | null);
    /**
     * 是否基建换班
     */
    IfInfrast?: (boolean | null);
    /**
     * 是否信用收支
     */
    IfMall?: (boolean | null);
    /**
     * 是否公开招募
     */
    IfRecruit?: (boolean | null);
    /**
     * 是否自动唤醒
     */
    IfStartUp?: (boolean | null);
    /**
     * 是否更换主题（主题名称在 MAA 侧配置，MAS 仅透传）
     */
    IfSwitchTheme?: (boolean | null);
    /**
     * 基建模式
     */
    InfrastMode?: ('Normal' | 'Rotation' | 'Custom' | null);
    /**
     * 基建配置名称
     */
    readonly InfrastName?: (string | null);
};

