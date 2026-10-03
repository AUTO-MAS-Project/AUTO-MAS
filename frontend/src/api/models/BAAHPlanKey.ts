/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BAAH 计划表某一天要打的关卡。
 *
 * 六个字段各自有三种状态，缺一不可地区分：
 * 缺席（字段不在 key 里）＝今天这一类不干预，BAAH 沿用自己配置文件里的关卡与开关；
 * 空数组＝今天不打这一类；有值（如 ``[3, -1, 1]``）＝今天按这个参数打这一类。
 * 因此默认值是 ``None`` 而不是某套具体关卡：补成默认值会把「不干预」静默变成
 * 「按默认关卡打」。
 */
export type BAAHPlanKey = {
    /**
     * 活动关卡：关卡序号、扫荡次数；缺席表示今天不干预这一类
     */
    Event?: (Array<number> | null);
    /**
     * 悬赏通缉：地区、关卡、次数；缺席表示今天不干预这一类
     */
    Wanted?: (Array<number> | null);
    /**
     * 特殊任务：地区、关卡、次数；缺席表示今天不干预这一类
     */
    Special?: (Array<number> | null);
    /**
     * 学园交流会：学院、关卡、次数；缺席表示今天不干预这一类
     */
    Exchange?: (Array<number> | null);
    /**
     * 困难图扫荡：章节、关卡、次数；缺席表示今天不干预这一类
     */
    Hard?: (Array<number> | null);
    /**
     * 普通图扫荡：章节、关卡、次数；缺席表示今天不干预这一类
     */
    Normal?: (Array<number> | null);
};

