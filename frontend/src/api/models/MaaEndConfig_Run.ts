/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndConfig_Run = {
    /**
     * 运行超时时间
     */
    Timeout?: (number | null);
    /**
     * 每日代理次数限制
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 运行次数限制
     */
    RunTimesLimit?: (number | null);
    /**
     * 是否启用切号
     */
    IfAccountSwitch?: (boolean | null);
    /**
     * 切号方式
     */
    AccountSwitchMethod?: (MaaEndConfig_Run.AccountSwitchMethod | null);
    /**
     * Endfield 客户端路径
     */
    GamePath?: (string | null);
    /**
     * 任务结束后是否关闭 Endfield
     */
    CloseGameOnFinish?: (boolean | null);
    /**
     * 控制器类型
     */
    ControllerType?: (MaaEndConfig_Run.ControllerType | null);
};
export namespace MaaEndConfig_Run {
    /**
     * 控制器类型
     */
    export enum ControllerType {
        WIN32_WINDOW = 'Win32-Window',
        WIN32_WINDOW_BACKGROUND = 'Win32-Window-Background',
        WIN32_FRONT = 'Win32-Front',
        ADB = 'ADB',
    }
    /**
     * 切号方式
     */
    export enum AccountSwitchMethod {
        EXIT_GAME = 'ExitGame',
        NO_ACTION = 'NoAction',
    }
}
