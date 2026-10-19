/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type M9AConfig_Device = {
    /**
     * ADB 地址，留空时启动脚本级模拟器获取
     */
    AdbAddress?: (string | null);
    /**
     * ADB 输入方法，默认优先模拟器增强，失败后回退到 MaaTouch / MiniTouch / ADB 同上，仅第二层适用；第一层运行期写死 InputMethods=18446744073709551607
     */
    AdbInputMethods?: (number | null);
    /**
     * ADB 路径，留空时从 MAS 模拟器配置或 MaaFW Toolkit 推导
     */
    AdbPath?: (string | null);
    /**
     * ADB 截图方法，默认优先模拟器增强，失败后回退到 ADB 截图 仅第二层（MAS 进程内 runner）适用：第一层由外壳自己创建控制器，运行期按 M9A 专项的既验证取值写死（ScreencapMethods=64），本项不参与外部运行， 接线前不要暴露到前端，否则用户改了不会生效也没有提示
     */
    AdbScreencapMethods?: (number | null);
    /**
     * Gamepad 类型，默认 Xbox360
     */
    GamepadType?: (number | null);
    /**
     * Win32 / Gamepad 窗口句柄，0 表示未指定
     */
    HWnd?: (number | null);
    /**
     * PlayCover 地址
     */
    PlayCoverAddress?: (string | null);
    /**
     * PlayCover UUID
     */
    PlayCoverUuid?: (string | null);
    /**
     * Win32 键盘方法，0 表示使用 interface 声明或 MaaFW 默认值
     */
    Win32KeyboardMethod?: (number | null);
    /**
     * Win32 鼠标方法，0 表示使用 interface 声明或 MaaFW 默认值
     */
    Win32MouseMethod?: (number | null);
    /**
     * Win32 截图方法，0 表示使用 interface 声明或 MaaFW 默认值
     */
    Win32ScreencapMethod?: (number | null);
};

