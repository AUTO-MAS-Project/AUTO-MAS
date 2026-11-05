/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type M9AConfig_TaskInput = {
    /**
     * 账号页任务队列的自定义模板，同一托管的账号共用。JSON 列表，每项 ``{"name": 模板名, "snapshot": {taskOrder, taskChecked, taskOptions, taskLabels?, taskSchedules?}}``， 快照形状同账号的 Task.TaskSnapshot（键是任务实例 id），但不含受管任务、密码字段 与全局选项（globalOptions 归各账号自己）； 名称在托管内唯一。运行流程不读它，只由账号页套用到某个账号的队列。
     */
    Templates?: (string | null);
};

