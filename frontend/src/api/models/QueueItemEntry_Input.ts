/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { app__models__config__queue__QueueItemEntry__Data } from './app__models__config__queue__QueueItemEntry__Data';
import type { app__models__config__queue__QueueItemEntry__Info } from './app__models__config__queue__QueueItemEntry__Info';
import type { Schedule } from './Schedule';
import type { Ui } from './Ui';
/**
 * 队列项：引用脚本 uid。
 */
export type QueueItemEntry_Input = {
    ui?: Ui;
    /**
     * 队列项
     */
    info?: app__models__config__queue__QueueItemEntry__Info;
    /**
     * 循环排期
     */
    schedule?: Schedule;
    /**
     * 循环运行记录
     */
    data?: app__models__config__queue__QueueItemEntry__Data;
};

