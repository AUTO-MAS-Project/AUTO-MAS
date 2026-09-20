/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWAgentEnvInfo = {
    /**
     * interface 声明的 agent child_exec
     */
    childExec: string;
    /**
     * 实际使用的解释器或可执行文件
     */
    executable: string;
    /**
     * agent 运行时类型：project_python / project_binary / isolated_venv / embedded / external
     */
    runtimeKind?: (string | null);
    /**
     * 该 agent 专属隔离 venv 路径
     */
    isolatedVenvPath?: (string | null);
    /**
     * 回退原因，供用户排查
     */
    fallbackReason?: (string | null);
};

