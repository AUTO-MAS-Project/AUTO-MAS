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
     * 内存 MB (3072/4096/5120/6144); 不传不改
     */
    memoryMb?: (number | null);
    /**
     * 空闲页上报 (气球) 开关; 不传不改
     */
    balloon?: (boolean | null);
};

