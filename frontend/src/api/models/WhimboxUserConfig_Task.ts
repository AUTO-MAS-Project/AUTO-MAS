/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 奇想盒任务覆盖集（键集来自任务目录，MAS 不建模字段定义）
 */
export type WhimboxUserConfig_Task = {
    /**
     * 步骤开关覆盖集 JSON map {步骤键: bool}，键集来自任务目录
     */
    Tasks?: (string | Record<string, any> | null);
    /**
     * 目标/参数覆盖集 JSON map {键: 值}，键集来自任务目录
     */
    Options?: (string | Record<string, any> | null);
};

