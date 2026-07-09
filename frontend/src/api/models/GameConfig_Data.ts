/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GameConfig_Data = {
    /**
     * PC 游戏安装目录
     */
    InstallPath?: (string | null);
    /**
     * 安卓包名
     */
    PackageName?: (string | null);
    /**
     * 关联模拟器 ID
     */
    EmulatorId?: (string | null);
    /**
     * 模拟器多开索引
     */
    EmulatorIndex?: (string | null);
    /**
     * 通用模拟器 adb 路径兜底
     */
    AdbPath?: (string | null);
    /**
     * 启动参数
     */
    LaunchArgs?: (string | null);
    /**
     * 鹰角高级自动更新开关
     */
    HgAutoPatchEnabled?: (boolean | null);
};

