/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MSSUserConfig_TaskInput = {
    /**
     * 当前选中的 interface preset 名称，留空时使用 interface 默认逻辑
     */
    SelectedPreset?: (string | null);
    /**
     * 当前用户的任务快照，结构为 taskOrder/taskChecked/taskOptions/globalOptions， 可选 taskLabels（用户给某一份实例起的显示名，只影响界面显示）， 可选 taskSchedules（``{实例 id: {weekdays: [1..7]}}``，ISO 星期 1=周一，升序去重；只在本机今天的星期在其中时运行这一份，开跑建计划时判一次；七天全选即不限制、不写这一项，空表或非法值按不限制处理）； 除 globalOptions 外各键都是任务实例 id，同一个任务可以重复入队（见 MaaFWTaskSnapshot）； globalOptions 是全局选项的值，每个用户一份、所有任务共用。 默认的空快照在建用户、读用户与运行前按项目默认（预设或默认勾选）补成实打实的队列， 见 app/task/MaaFW/tools/embedded/default_snapshot.py
     */
    TaskSnapshot?: (string | null);
};

