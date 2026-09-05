/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWConfig_Managed = {
    /**
     * 是否启用托管资源
     */
    Enabled?: (boolean | null);
    /**
     * Project Store 项目 ID
     */
    ProjectId?: (string | null);
    /**
     * Project Store 实例身份
     */
    StoreId?: (string | null);
    /**
     * 当前不可变项目版本
     */
    Version?: (string | null);
    /**
     * MaaFW 运行时约束
     */
    RuntimeConstraint?: (string | null);
    /**
     * 项目资源清单 JSON
     */
    ProjectManifest?: (string | null);
    /**
     * 脚本专属可写 checkout 路径
     */
    CheckoutPath?: (string | null);
    /**
     * 待确认升级事务 JSON
     */
    PendingUpgrade?: (string | null);
    /**
     * 最近资源操作 JSON
     */
    LastOperation?: (string | null);
};

