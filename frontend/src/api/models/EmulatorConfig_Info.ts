/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type EmulatorConfig_Info = {
    /**
     * 模拟器名称
     */
    Name?: (string | null);
    /**
     * 模拟器类型
     */
    Type?: ('general' | 'mumu' | 'ldplayer' | 'emulator2' | null);
    /**
     * 模拟器路径
     */
    Path?: (string | null);
    /**
     * Emulator 2.0 纳管的模拟器路径列表（JSON）
     */
    Paths?: (string | null);
    /**
     * Emulator 2.0 的设备号槽位表（JSON）
     */
    Slots?: (string | null);
    /**
     * 老板键快捷键配置
     */
    BossKey?: (string | null);
    /**
     * 最大等待时间（秒）
     */
    MaxWaitTime?: (number | null);
    /**
     * 关闭 MuMu 时强力清理残留进程
     */
    ForceKillOnClose?: (boolean | null);
};

