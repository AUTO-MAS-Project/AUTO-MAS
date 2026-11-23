/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TagItem } from './TagItem';
export type MaaUserConfig_plugin_info = {
    readonly name?: (string | null);
    readonly enabled?: (boolean | null);
    readonly config_path?: (string | null);
    /**
     * 配置来源
     */
    mode?: ('脚本' | '用户' | '直控' | null);
    /**
     * 覆写常规配置
     */
    if_quick_config?: (boolean | null);
    /**
     * 代理情况摘要
     */
    proxy_status?: (string | null);
    /**
     * 上次任务结果记录
     */
    last_result?: (string | null);
    /**
     * 关联计划表 uid；- 表示未选
     */
    plan_id?: (string | null);
    readonly tags?: (Array<TagItem> | null);
};

