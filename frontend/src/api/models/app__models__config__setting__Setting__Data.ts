/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Virtual_str_ } from './Virtual_str_';
export type app__models__config__setting__Setting__Data = {
    /**
     * 全局实例 UID
     */
    uid?: string;
    /**
     * 上次统计上报时间
     */
    last_statistics_upload?: string;
    /**
     * 关卡数据上次更新时间
     */
    last_stage_updated?: string;
    /**
     * 关卡数据 ETag
     */
    stage_etag?: string;
    /**
     * 关卡原始数据 JSON
     */
    stage_data?: string;
    /**
     * 活动关卡下拉数据（由 stage_data 推导）
     */
    stage?: Virtual_str_;
    /**
     * 公告上次更新时间
     */
    last_notice_updated?: string;
    /**
     * 公告 ETag
     */
    notice_etag?: string;
    /**
     * 是否显示公告
     */
    if_show_notice?: boolean;
    /**
     * 公告内容 JSON
     */
    notice?: string;
    /**
     * Web 配置上次更新时间
     */
    last_web_config_updated?: string;
    /**
     * Web 配置 JSON 列表
     */
    web_config?: string;
};

