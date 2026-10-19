/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type EmulatorConfig_InfoInput = {
    /**
     * 模拟器类型
     */
    Type?: ('general' | 'mumu' | 'ldplayer' | 'emulator2' | null);
    /**
     * 守卫的基准: {设备号: {字段: 值}}, 只记用户显式设过的字段
     */
    Baselines?: (string | null);
    /**
     * 老板键快捷键配置
     */
    BossKey?: (string | null);
    /**
     * Emulator 2.0 的稳定模式：开着就把会干扰截图识别的模拟器功能压住, 启动实例前顺带确保一次, 这样新建的实例也会跟着进入安全状态。 关掉只是不再确保, **不会把那些项改回去**——不知道用户原本想要什么值。 Emulator 2.0 的配置守卫：以 MAS 存的这份设置为准, 启动前与关闭后各核验一次, 对不上就写回去。与旧雷电那套「开机拍快照关机还原」不是一回事, 见 utils/emulator2/guard.py
     */
    ConfigGuard?: (boolean | null);
    /**
     * 启动 MuMu 实例前先关闭已在运行的实例并强力清理残留进程 用于已有非管理员实例导致新实例无法以管理员身份启动的场景; 会关掉全部实例, 多开慎用
     */
    ForceKillBeforeLaunch?: (boolean | null);
    /**
     * 关闭 MuMu 时强力清理残留进程
     */
    ForceKillOnClose?: (boolean | null);
    /**
     * 最大等待时间（秒）
     */
    MaxWaitTime?: (number | null);
    /**
     * 模拟器名称
     */
    Name?: (string | null);
    /**
     * 模拟器路径
     */
    Path?: (string | null);
    /**
     * Emulator 2.0 纳管的模拟器路径列表 [{"pathId", "installPath", "alias", "type", "version"}]
     */
    Paths?: (string | null);
    /**
     * Emulator 2.0 的设备号槽位表 [{"slot", "pathId", "nativeIndex", "state": "active"|"tombstone"}] 槽位号在本配置内单调递增分配, 移除路径写墓碑, 号码永不复用
     */
    Slots?: (string | null);
    /**
     * Emulator 2.0: 稳定模式是否开启
     */
    StableMode?: (boolean | null);
};

