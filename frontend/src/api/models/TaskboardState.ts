/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskboardArchivedActivity } from './TaskboardArchivedActivity';
import type { TaskboardDoneRecord } from './TaskboardDoneRecord';
export type TaskboardState = {
    /**
     * 任务台勾选的游戏；为空表示尚未保存
     */
    selected_games?: (Array<string> | null);
    /**
     * 已归档活动的展示缓存
     */
    archived?: Array<TaskboardArchivedActivity>;
    /**
     * 活动完成日期，key 为游戏与活动的组合键
     */
    done_at?: Record<string, TaskboardDoneRecord>;
};

