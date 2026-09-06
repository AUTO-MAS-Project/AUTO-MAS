/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2SettingField } from './Emulator2SettingField';
export type Emulator2DeviceItem = {
    /**
     * 设备号, 脚本绑定用它
     */
    slot: string;
    /**
     * 所属路径标识
     */
    pathId: string;
    /**
     * 所属安装的别名
     */
    alias?: string;
    /**
     * 设备的真实模拟器类型, 不是配置的类型
     */
    realType?: string;
    /**
     * 模拟器自己的实例索引
     */
    nativeIndex: string;
    /**
     * ok 正常 / missing 这次没枚举到 / unavailable 该安装暂时不可达
     */
    availability?: string;
    /**
     * 实例名称
     */
    title?: string;
    /**
     * 设备状态码
     */
    status?: number;
    /**
     * ADB 地址
     */
    adbAddress?: string;
    /**
     * 已保存设置, 下次启动使用; 不是运行中实例的当前配置
     */
    settings?: Record<string, Emulator2SettingField>;
    /**
     * 稳定模式是否已生效(所有干扰项都处在安全状态)
     */
    stableMode?: boolean;
    /**
     * 还没进入安全状态的项
     */
    stableUnsafe?: Array<string>;
};

