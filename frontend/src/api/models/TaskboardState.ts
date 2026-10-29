/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskboardArchivedActivity } from './TaskboardArchivedActivity';
import type { TaskboardDoneRecord } from './TaskboardDoneRecord';
import type { TaskboardVersionStoryRecord } from './TaskboardVersionStoryRecord';
import type { TaskboardWeeklyRecord } from './TaskboardWeeklyRecord';
export type TaskboardState = {
    /**
     * 任务台勾选的游戏；为空表示尚未保存
     */
    selected_games?: (Array<string> | null);
    /**
     * 每周任务单独勾选的游戏；为空表示跟随任务台游戏选择
     */
    weekly_games?: (Array<string> | null);
    /**
     * 已归档活动的展示缓存
     */
    archived?: Array<TaskboardArchivedActivity>;
    /**
     * 活动完成日期，key 为游戏与活动的组合键
     */
    done_at?: Record<string, TaskboardDoneRecord>;
    /**
     * 每周任务完成状态，key 为任务台游戏标识
     */
    weekly?: Record<string, TaskboardWeeklyRecord>;
    /**
     * 本地积累的版本主线目录，key 为游戏与版本的组合键
     */
    version_story?: Record<string, TaskboardVersionStoryRecord>;
    /**
     * 版本主线完成记录，key 与 version_story 一致
     */
    version_story_done?: Record<string, TaskboardDoneRecord>;
};

