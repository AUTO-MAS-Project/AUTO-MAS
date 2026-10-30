/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWProjectUpdateData } from './MaaFWProjectUpdateData';
export type MaaFWProjectUpdateJobResult = {
    /**
     * 与 /maafw/update 响应的 code 同义：200 为成功，其余为失败
     */
    code?: number;
    /**
     * 结果摘要；失败时为原因
     */
    message?: string;
    /**
     * 与 /maafw/update 响应的 data 相同；失败时可能为空
     */
    data?: (MaaFWProjectUpdateData | null);
};

