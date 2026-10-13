/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { app__models__config__setting__Setting__Data } from './app__models__config__setting__Setting__Data';
import type { Appearance } from './Appearance';
import type { ConfigCollection_Webhook_ } from './ConfigCollection_Webhook_';
import type { Display } from './Display';
import type { Function } from './Function';
import type { Language } from './Language';
import type { Notify } from './Notify';
import type { Start } from './Start';
import type { Ui } from './Ui';
import type { Updates } from './Updates';
import type { Uv } from './Uv';
import type { Voice } from './Voice';
/**
 * 全局设置，对应 ``config/setting.yaml``。
 */
export type Setting_Input = {
    ui?: Ui;
    /**
     * 功能相关配置
     */
    function?: Function;
    /**
     * 语言相关配置
     */
    language?: Language;
    /**
     * 语音相关配置
     */
    voice?: Voice;
    /**
     * 启动相关配置
     */
    start?: Start;
    /**
     * 界面相关配置
     */
    appearance?: Appearance;
    /**
     * 桌面显示保障
     */
    display?: Display;
    /**
     * 通知相关配置
     */
    notify?: Notify;
    /**
     * 更新相关配置
     */
    updates?: Updates;
    /**
     * 全局运行时数据
     */
    data?: app__models__config__setting__Setting__Data;
    /**
     * uv / PyPI 镜像偏好
     */
    uv?: Uv;
    custom_webhooks?: ConfigCollection_Webhook_;
};

