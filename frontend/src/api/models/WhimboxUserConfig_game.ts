/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WhimboxUserConfig_game = {
    /**
     * 升级时无法解析的目标，需重新选择
     */
    readonly unavailable_reason?: (string | null);
    /**
     * 游戏目标；账号留空时继承托管
     */
    game_id?: (string | null);
    /**
     * 所选游戏的设备
     */
    device_id?: (string | null);
};

