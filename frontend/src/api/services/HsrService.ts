/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRCapabilitiesOut } from '../models/HSRCapabilitiesOut';
import type { HSRDirectConfigImportIn } from '../models/HSRDirectConfigImportIn';
import type { HSRDirectConfigImportOut } from '../models/HSRDirectConfigImportOut';
import type { HSRManagedConfigOut } from '../models/HSRManagedConfigOut';
import type { HSRSRAProfilesOut } from '../models/HSRSRAProfilesOut';
import type { HSRStageOptionsOut } from '../models/HSRStageOptionsOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class HsrService {
    /**
     * 获取 HSR 体力副本动态选项
     * 返回 M7A/SRA 原生副本字段。
     *
     * ``userId`` 仅用于校验用户归属；``slot`` 是兼容参数，动态选项当前
     * 按引擎统一返回，不按 slot 生成不同结果。
     * @param scriptId
     * @param engine
     * @param userId
     * @param slot
     * @returns HSRStageOptionsOut Successful Response
     * @throws ApiError
     */
    public static getHsrStageOptionsApiApiScriptsHsrStageOptionsGet(
        scriptId?: (string | null),
        engine: 'M7A' | 'SRA' = 'M7A',
        userId?: (string | null),
        slot: 'main' | 'eow' = 'main',
    ): CancelablePromise<HSRStageOptionsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/hsr/stage-options',
            query: {
                'scriptId': scriptId,
                'engine': engine,
                'userId': userId,
                'slot': slot,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取内置 HSR 能力快照
     * 返回内置 HSR 的能力快照，不暴露原生编辑器会话。
     * @param scriptId
     * @returns HSRCapabilitiesOut Successful Response
     * @throws ApiError
     */
    public static getHsrCapabilitiesApiApiScriptsHsrCapabilitiesGet(
        scriptId?: (string | null),
    ): CancelablePromise<HSRCapabilitiesOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/hsr/capabilities',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 HSR 托管配置字段
     * 返回原生动态托管字段；用户 ID 只负责归属校验。
     * @param scriptId
     * @param userId
     * @returns HSRManagedConfigOut Successful Response
     * @throws ApiError
     */
    public static getHsrManagedConfigApiApiScriptsHsrManagedConfigGet(
        scriptId?: (string | null),
        userId?: (string | null),
    ): CancelablePromise<HSRManagedConfigOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/hsr/managed-config',
            query: {
                'scriptId': scriptId,
                'userId': userId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 HSR 可选的 SRA 配置档案
     * 列出 ``%APPDATA%/SRA/configs`` 下的配置档案，并标出脚本当前生效的那份。
     * @param scriptId
     * @returns HSRSRAProfilesOut Successful Response
     * @throws ApiError
     */
    public static getHsrSraProfilesApiApiScriptsHsrSraProfilesGet(
        scriptId?: (string | null),
    ): CancelablePromise<HSRSRAProfilesOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/hsr/sra-profiles',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 导入 HSR 原生配置快照
     * @param requestBody
     * @returns HSRDirectConfigImportOut Successful Response
     * @throws ApiError
     */
    public static importHsrDirectConfigApiApiScriptsHsrDirectConfigImportPost(
        requestBody: HSRDirectConfigImportIn,
    ): CancelablePromise<HSRDirectConfigImportOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/hsr/direct-config/import',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 清除 HSR 用户的直控配置快照
     * 清掉该用户导入的快照，直控回到直接使用脚本当前原生配置。
     * @param requestBody
     * @returns HSRDirectConfigImportOut Successful Response
     * @throws ApiError
     */
    public static clearHsrDirectConfigApiApiScriptsHsrDirectConfigClearPost(
        requestBody: HSRDirectConfigImportIn,
    ): CancelablePromise<HSRDirectConfigImportOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/hsr/direct-config/clear',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
