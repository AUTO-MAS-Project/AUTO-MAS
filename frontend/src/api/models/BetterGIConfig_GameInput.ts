/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BetterGIConfig_GameInput = {
    /**
     * 任务结束后关闭游戏
     */
    CloseOnFinish?: (boolean | null);
    /**
     * 控制器（游戏控制方式：电脑端-前台 / 电脑端-云原神 / 电脑端-桌面分身） ⚠️ 预留字段：当前运行时不读取（BetterGI 自行管理游戏控制），云原神 / 桌面分身 尚未开发。为将来支持而保留占位并持久化，恒为默认「电脑端-前台」，勿被判定死代码误删。
     */
    Controller?: ('电脑端-前台' | '电脑端-云原神' | '电脑端-桌面分身' | null);
    /**
     * 是否在启动 BetterGI 前由 MAS 检查并接管原神客户端更新
     */
    IfAutoUpdate?: (boolean | null);
};

