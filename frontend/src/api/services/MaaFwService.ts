/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWAgentEnvPrepareIn } from '../models/MaaFWAgentEnvPrepareIn';
import type { MaaFWAgentEnvPrepareOut } from '../models/MaaFWAgentEnvPrepareOut';
import type { MaaFWInterfacePreviewIn } from '../models/MaaFWInterfacePreviewIn';
import type { MaaFWInterfacePreviewOut } from '../models/MaaFWInterfacePreviewOut';
import type { MaaFWProjectUpdateIn } from '../models/MaaFWProjectUpdateIn';
import type { MaaFWProjectUpdateOut } from '../models/MaaFWProjectUpdateOut';
import type { MaaFWWindowPreviewIn } from '../models/MaaFWWindowPreviewIn';
import type { MaaFWWindowPreviewOut } from '../models/MaaFWWindowPreviewOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class MaaFwService {
    /**
     * 预览 MaaFW ProjectInterface
     * 读取 MaaFW 项目目录中的 interface.json，返回 MAS UI 可消费的摘要。
     * @param requestBody
     * @returns MaaFWInterfacePreviewOut Successful Response
     * @throws ApiError
     */
    public static previewMaafwInterfaceApiScriptsMaafwInterfacePreviewPost(
        requestBody: MaaFWInterfacePreviewIn,
    ): CancelablePromise<MaaFWInterfacePreviewOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/interface/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 手动更新 MaaFW 项目资源
     * 按脚本更新配置手动检查并应用 MaaFW 项目资源更新。
     * @param requestBody
     * @returns MaaFWProjectUpdateOut Successful Response
     * @throws ApiError
     */
    public static updateMaafwProjectApiScriptsMaafwProjectUpdatePost(
        requestBody: MaaFWProjectUpdateIn,
    ): CancelablePromise<MaaFWProjectUpdateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/project/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Prepare MaaFW agent Python env
     * Prepare MaaFW agent Python envs without loading resources or starting agents.
     * @param requestBody
     * @returns MaaFWAgentEnvPrepareOut Successful Response
     * @throws ApiError
     */
    public static prepareMaafwAgentEnvApiScriptsMaafwAgentEnvPreparePost(
        requestBody: MaaFWAgentEnvPrepareIn,
    ): CancelablePromise<MaaFWAgentEnvPrepareOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/agent-env/prepare',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 读取 MaaFW 本地图片资源
     * 读取 MaaFW interface 描述、任务、选项中引用的本地图片资源。
     * @param root MaaFW 项目根目录
     * @param path 相对 MaaFW 项目根目录的图片路径
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getMaafwAssetApiScriptsMaafwAssetGet(
        root: string,
        path: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/maafw/asset',
            query: {
                'root': root,
                'path': path,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 扫描 MaaFW PC 客户端窗口
     * 按 interface.json 中的 Win32 窗口规则扫描本机桌面窗口。
     * @param requestBody
     * @returns MaaFWWindowPreviewOut Successful Response
     * @throws ApiError
     */
    public static previewMaafwWindowsApiScriptsMaafwWindowsPreviewPost(
        requestBody: MaaFWWindowPreviewIn,
    ): CancelablePromise<MaaFWWindowPreviewOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/windows/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
