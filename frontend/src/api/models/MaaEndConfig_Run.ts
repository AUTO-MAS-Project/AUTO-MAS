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
     * 重试次数
     */
    Retry?: (number | null);
    /**
     * 运行次数限制
     */
    RunTimesLimit?: (number | null);
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
        WIN32 = 'Win32',
        ADB = 'ADB',
        PLAY_COVER = 'PlayCover',
    }
}
