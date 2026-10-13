/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { app__models__config__plugin__PluginRecord__Info } from './app__models__config__plugin__PluginRecord__Info';
import type { Ui } from './Ui';
/**
 * 已安装插件注册表项：元数据 + 状态由 Manager 回写；四 Trigger 仅开闸。
 *
 * 不用配置信号维护级联/状态。前端 update 须剔除非 Trigger 字段。
 *
 * 运行时一律挂本 live 条目的 PrivateAttr（不落盘）：
 * ``_plugin`` / ``_plugin_cls`` / ``_config`` / ``_degraded_wants`` / ``_project_dir``。
 */
export type PluginRecord = {
    ui?: Ui;
    /**
     * 插件注册表项
     */
    info?: app__models__config__plugin__PluginRecord__Info;
};

