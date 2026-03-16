/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndConfig_Run = {
    /**
     * 杩愯瓒呮椂鏃堕棿
     */
    Timeout?: (number | null);
    /**
     * 閲嶈瘯娆℃暟
     */
    Retry?: (number | null);
    /**
     * 杩愯娆℃暟闄愬埗
     */
    RunTimesLimit?: (number | null);
    /**
     * 鏄惁鍚敤鍒囧彿
     */
    IfAccountSwitch?: (boolean | null);
    /**
     * 鍒囧彿鏂瑰紡
     */
    AccountSwitchMethod?: (MaaEndConfig_Run.AccountSwitchMethod | null);
    /**
     * Endfield 瀹㈡埛绔矾寰?
     */
    GamePath?: (string | null);
    /**
     * 浠诲姟缁撴潫鍚庢槸鍚﹀叧闂?Endfield
     */
    CloseGameOnFinish?: (boolean | null);
    /**
     * 鎺у埗鍣ㄧ被鍨?
     */
    ControllerType?: (MaaEndConfig_Run.ControllerType | null);
};
export namespace MaaEndConfig_Run {
    /**
     * 鎺у埗鍣ㄧ被鍨?
     */
    export enum ControllerType {
        WIN32_WINDOW = 'Win32-Window',
        WIN32_WINDOW_BACKGROUND = 'Win32-Window-Background',
        WIN32_FRONT = 'Win32-Front',
        ADB = 'ADB',
    }
    /**
     * 鍒囧彿鏂瑰紡
     */
    export enum AccountSwitchMethod {
        EXIT_GAME = 'ExitGame',
        NO_ACTION = 'NoAction',
    }
}
