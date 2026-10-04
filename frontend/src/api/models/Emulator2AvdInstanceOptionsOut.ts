/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdInstanceOptionsOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 是否无头运行, 下次启动生效
     */
    headless?: boolean;
    /**
     * 显示档位 720 / 1080
     */
    resolution?: string;
    /**
     * 内存是否按游戏自动 (方舟 / 1999 / 崩坏三 4 GB, 星铁 5 GB, 其它 4 GB)
     */
    memoryAuto?: boolean;
    /**
     * 空闲页上报 (气球) 是否开启
     */
    balloon?: boolean;
    /**
     * 是否启用 GuestAngle
     */
    guestAngle?: boolean;
    /**
     * 手动指定的内存 MB; 按游戏自动时为兜底值 4096
     */
    memoryMb?: (number | null);
    /**
     * CPU 核数
     */
    cpu?: (number | null);
    /**
     * 数据盘上限 GB
     */
    dataPartitionGb?: (number | null);
    /**
     * 首次开机初始化是否已完成 (关 WiFi / 去预装等)
     */
    initialized?: boolean;
    /**
     * 当前桌面包名, pixel 为原生桌面
     */
    launcher?: string;
    /**
     * 首次开机记录的渲染器 (GLES 行)
     */
    renderer?: string;
    /**
     * 是否在用软件渲染 (SwiftShader); 为 true 时应提示用户更新显卡驱动
     */
    softwareRenderer?: boolean;
    /**
     * 控制台端口
     */
    consolePort?: number;
    /**
     * adb 端口
     */
    adbPort?: number;
    /**
     * gRPC 端口 (带 token 鉴权)
     */
    grpcPort?: number;
};

