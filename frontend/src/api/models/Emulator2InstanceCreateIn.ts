/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2InstanceCreateIn = {
    /**
     * 配置ID
     */
    emulatorId: string;
    /**
     * 在哪条模拟器安装下新建
     */
    pathId: string;
    /**
     * 新实例名称, 留空由模拟器自己命名
     */
    name?: (string | null);
    /**
     * 仅魔改 AVD: 内存 MB, 可选 3072 / 4096 / 5120 / 6144; 留空为 6144
     */
    memoryMb?: (number | null);
    /**
     * 仅魔改 AVD: CPU 核数, 可选 2 / 4 / 6, 留空为 6
     */
    cpu?: (number | null);
    /**
     * 仅魔改 AVD: 帧率 (hw.lcd.vsync), 可选 30 / 60, 留空为 60
     */
    fps?: (number | null);
    /**
     * 仅魔改 AVD: 数据盘上限 GB (16–512), 按实际写入增长, 留空为 64
     */
    dataPartitionGb?: (number | null);
};

