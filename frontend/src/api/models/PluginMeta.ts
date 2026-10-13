/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { app__models__config__plugin__PluginMeta__Info } from './app__models__config__plugin__PluginMeta__Info';
import type { Ui } from './Ui';
/**
 * 插件目录（市场）条目：刷新写入；install Trigger 开闸安装。
 *
 * 展示字段：隐藏 ``*_i18n`` 字典 + Virtual 按 ``setting.language.locale`` 暴露。
 */
export type PluginMeta = {
    ui?: Ui;
    /**
     * 目录项
     */
    info?: app__models__config__plugin__PluginMeta__Info;
};

