/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MSSUserConfig_Task = {
    /**
     * 当前选中的 interface preset 名称，留空时使用 interface 默认逻辑
     */
    SelectedPreset?: (string | null);
    /**
     * 当前用户的任务快照，结构为 taskOrder/taskChecked/taskOptions/globalOptions， 可选 taskLabels（用户给某一份实例起的显示名，只影响界面显示）； 除 globalOptions 外各键都是任务实例 id，同一个任务可以重复入队（见 MaaFWTaskSnapshot）； globalOptions 是全局选项的值，每个用户一份、所有任务共用。 默认的空快照在建用户、读用户与运行前按项目默认（预设或默认勾选）补成实打实的队列， 见 app/task/MaaFW/tools/embedded/default_snapshot.py
     */
    TaskSnapshot?: (string | null);
};

