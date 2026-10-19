/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ZzzOdUserConfig_OneDragon = {
    /**
     * 游戏结束后操作（仅 MAS 拉起的一条龙运行消费：CLI 传参 --close-game / --shutdown 60；无=不传参，游戏保持运行。 与一条龙原生 GUI 的「结束后」下拉无关——原生 after_done 只在 从 GUI 内启动运行时被消费，CLI 路径不读它）
     */
    AfterDone?: ('无' | '关闭游戏' | '关机' | null);
    /**
     * 一条龙任务编排（JSON 数组字符串 [{"app_id": "...", "enabled": true}, ...]， 数组顺序即执行顺序；enabled=false 的任务由 zzz-od 跳过）
     */
    AppList?: (string | null);
};

