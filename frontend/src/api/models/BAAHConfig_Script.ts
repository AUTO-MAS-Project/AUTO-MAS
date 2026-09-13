/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BAAHConfig_Script = {
    /**
     * BAAH 主程序路径；程序目录、配置目录与日志目录均由此派生
     */
    BAAHPath?: (string | null);
    /**
     * 是否托管 BAAH 运行所需的关键配置
     */
    IfManageConfig?: (boolean | null);
    /**
     * 是否在任务报告中保留 BAAH 的运行日志
     */
    PushLogEnabled?: (boolean | null);
};

