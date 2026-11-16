/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WhimboxUserConfig_Task = {
    /**
     * 目标/参数覆盖集：JSON map {键: 值}，键集来自任务目录 （上游 OneDragon 节托管字段），只存用户显式选择的值
     */
    Options?: (string | null);
    /**
     * 步骤开关覆盖集：JSON map {步骤键: bool}，键集来自任务目录 （上游 OneDragonDefaultSteps 节），只存用户勾选结果
     */
    Tasks?: (string | null);
};

