/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { app__models__config__queue__QueueEntry__Data } from './app__models__config__queue__QueueEntry__Data';
import type { app__models__config__queue__QueueEntry__Info } from './app__models__config__queue__QueueEntry__Info';
import type { ConfigCollection_QueueItemEntry_ } from './ConfigCollection_QueueItemEntry_';
import type { ConfigCollection_TimeSetEntry_ } from './ConfigCollection_TimeSetEntry_';
import type { Ui } from './Ui';
/**
 * 单条调度队列。
 */
export type QueueEntry_Input = {
    ui?: Ui;
    /**
     * 队列信息
     */
    info?: app__models__config__queue__QueueEntry__Info;
    /**
     * 队列运行时数据
     */
    data?: app__models__config__queue__QueueEntry__Data;
    time_sets?: ConfigCollection_TimeSetEntry_;
    items?: ConfigCollection_QueueItemEntry_;
};

