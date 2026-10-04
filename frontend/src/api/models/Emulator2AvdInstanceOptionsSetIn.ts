/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdInstanceOptionsSetIn = {
    /**
     * Emulator 2.0 配置 ID
     */
    emulatorId: string;
    /**
     * 设备号
     */
    slot: string;
    /**
     * true 无头 (静默, 没有窗口) / false 带窗口; 不传不改; 下次启动生效
     */
    headless?: (boolean | null);
    /**
     * 显示档位: 720 (1280x720, DPI 240) / 1080 (1920x1080, DPI 280); 不传不改
     */
    resolution?: ('720' | '1080' | null);
    /**
     * 内存 MB (3072/4096/5120/6144); 不传不改
     */
    memoryMb?: (number | null);
    /**
     * 空闲页上报 (气球) 开关; 不传不改
     */
    balloon?: (boolean | null);
    /**
     * 客体走镜像自带 ANGLE (GuestAngle); 不传不改
     */
    guestAngle?: (boolean | null);
};

