/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MSSConfig_Task = {
    /**
     * 用户页任务队列的自定义模板，同一脚本的用户共用。JSON 列表，每项 ``{"name": 模板名, "snapshot": {taskOrder, taskChecked, taskOptions, taskLabels?}}``， 快照形状同用户的 Task.TaskSnapshot（键是任务实例 id），但不含受管任务、密码字段 与全局选项（globalOptions 归各用户自己）； 名称在脚本内唯一。运行流程不读它，只由用户页套用到某个用户的队列。
     */
    Templates?: (string | null);
};

