/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdUpdateCheckIn = {
    /**
     * 魔改 AVD 根目录; 必须已加进 Emulator 2.0, 别的目录一律拒绝
     */
    root: string;
    /**
     * 不走 4 小时缓存重新查; 用户点「检查更新」时传 true
     */
    force?: boolean;
};

