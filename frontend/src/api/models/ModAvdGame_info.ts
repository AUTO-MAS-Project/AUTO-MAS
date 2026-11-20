/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ModAvdGame_info = {
    /**
     * 实例命名
     */
    name?: (string | null);
    /**
     * 是否允许并发运行
     */
    concurrent_execution?: (boolean | null);
    /**
     * ModAVD 的 sdk/emulator/emulator.exe；组件未安装时可暂缺
     */
    path?: (string | null);
    /**
     * 操作最大等待时间（秒）
     */
    max_wait_time?: (number | null);
    /**
     * 启动前确保适合自动化的稳定设置，关闭不还原
     */
    stable_mode?: (boolean | null);
    /**
     * 启动前与关闭后确保已保存的用户设置
     */
    config_guard?: (boolean | null);
    /**
     * 启动前清理残留进程
     */
    force_kill_before_launch?: (boolean | null);
    /**
     * 关闭时清理残留进程
     */
    force_kill_on_close?: (boolean | null);
    /**
     * 老板键快捷键
     */
    boss_key?: (Array<string> | null);
};

