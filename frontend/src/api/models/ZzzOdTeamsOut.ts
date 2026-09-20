/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ComboBoxItem } from './ComboBoxItem';
import type { ZzzOdTeamItemOut } from './ZzzOdTeamItemOut';
/**
 * 预备编队列表 + 配队方案/代理人选项
 */
export type ZzzOdTeamsOut = {
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
     * 编队列表（固定 20 个）
     */
    teams: Array<ZzzOdTeamItemOut>;
    /**
     * 配队方案选项
     */
    autoBattle: Array<ComboBoxItem>;
    /**
     * 代理人选项（label=名称，value=agent_id）
     */
    agentOptions?: Array<ComboBoxItem>;
};

