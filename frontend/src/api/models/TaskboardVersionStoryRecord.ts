/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TaskboardVersionStoryRecord = {
    /**
     * 游戏标识
     */
    game: string;
    /**
     * 版本号
     */
    version: string;
    /**
     * 版本名称
     */
    version_name?: string;
    /**
     * 版本开始时间
     */
    start?: string;
    /**
     * 版本结束时间
     */
    end?: string;
    /**
     * 版本封面地址；仅接受公网 https，非法值置空
     */
    cover_url?: string;
    /**
     * 首次记录时间
     */
    first_seen?: string;
    /**
     * 最近一次记录时间
     */
    last_seen?: string;
    /**
     * 最近一次字段更新的观察时间，Unix 毫秒
     */
    observed_at?: number;
};

