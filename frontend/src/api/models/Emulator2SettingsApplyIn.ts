/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2SettingsApplyIn = {
    /**
     * 模拟器配置ID
     */
    emulatorId: string;
    /**
     * 设备号
     */
    slot: string;
    /**
     * 要写入的字段; 只提交用户改过的, 其余键原样保留
     */
    changes: Record<string, number>;
    /**
     * 表单打开时看到的值; 对不上说明文件被改过, 拒绝覆盖
     */
    expected?: Record<string, (number | null)>;
};

