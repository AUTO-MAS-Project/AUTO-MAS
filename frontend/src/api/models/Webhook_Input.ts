/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { app__models__config__setting__Webhook__Data } from './app__models__config__setting__Webhook__Data';
import type { app__models__config__setting__Webhook__Info } from './app__models__config__setting__Webhook__Info';
import type { Ui } from './Ui';
/**
 * 自定义 Webhook 通知项。
 */
export type Webhook_Input = {
    ui?: Ui;
    /**
     * Webhook基础信息
     */
    info?: app__models__config__setting__Webhook__Info;
    /**
     * Webhook配置数据
     */
    data?: app__models__config__setting__Webhook__Data;
};

