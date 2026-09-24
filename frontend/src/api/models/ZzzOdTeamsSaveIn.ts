/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 整表保存预备编队（名称 + 绑定配队方案 + 成员 agent_id_list）
 */
export type ZzzOdTeamsSaveIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 目标用户ID
     */
    userId: string;
    /**
     * 编队列表（name/autoBattle/agent_id_list）
     */
    teams: Array<Record<string, any>>;
    /**
     * 直控模式：直接写入的原生实例下标（缺省写入用户绑定槽）
     */
    instanceIdx?: (number | null);
};

