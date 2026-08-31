/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWAgentEnvInfo } from './MaaFWAgentEnvInfo';
export type MaaFWAgentEnvPrepareData = {
    /**
     * MFW 项目根目录
     */
    path: string;
    /**
     * agent 数量
     */
    agentCount?: number;
    /**
     * 各 agent 的运行环境信息
     */
    agents?: Array<MaaFWAgentEnvInfo>;
    /**
     * 准备过程日志
     */
    logs?: Array<string>;
    /**
     * Runtime Pool 中的 runtime ID
     */
    runtimeId?: (string | null);
    /**
     * Runtime Pool 身份
     */
    poolId?: (string | null);
    /**
     * Runner 使用的 Python 解释器
     */
    pythonExecutable?: (string | null);
    /**
     * Runner 虚拟环境路径
     */
    venvPath?: (string | null);
    /**
     * 实际解析到的 MaaFramework 版本
     */
    maafwVersion?: (string | null);
};

