/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type M9AConfig_Info = {
    /**
     * MaaFW controller 名称，留空时按 interface 和设备配置自动选择
     */
    Controller?: (string | null);
    /**
     * MaaFW 脚本名称
     */
    Name?: (string | null);
    /**
     * MaaFW 项目的导入来源目录，应包含 interface.json；导入后可删，删了也原样保留
     */
    Path?: (string | null);
    /**
     * 项目标签，可用于区分同一 ProjectInterface 的不同实例
     */
    ProjectLabel?: (string | null);
    /**
     * MaaFW resource 名称，留空时选择匹配 controller 的第一个 resource
     */
    Resource?: (string | null);
};

