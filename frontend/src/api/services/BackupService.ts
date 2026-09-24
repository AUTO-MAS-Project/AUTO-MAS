/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConfigBackupEnsureIn } from '../models/ConfigBackupEnsureIn';
import type { ConfigBackupEnsureOut } from '../models/ConfigBackupEnsureOut';
import type { ConfigBackupFileOut } from '../models/ConfigBackupFileOut';
import type { ConfigBackupListOut } from '../models/ConfigBackupListOut';
import type { ConfigBackupPreviewOut } from '../models/ConfigBackupPreviewOut';
import type { ConfigBackupRestoreIn } from '../models/ConfigBackupRestoreIn';
import type { ConfigBackupRestoreOut } from '../models/ConfigBackupRestoreOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class BackupService {
    /**
     * 列出配置备份（时间倒序；target 取值由专项定义，非法值返回 400）
     * 返回 ``items``（``time`` + 备份时点来源标注 ``mode``，倒序）与当前
     * 来源 ``mode``（仅三态池，供前端跨来源提示）；非法 target 返回 400。
     * @param scriptId
     * @param userId
     * @param target
     * @returns ConfigBackupListOut Successful Response
     * @throws ApiError
     */
    public static listConfigBackupsApiApiScriptsBackupListGet(
        scriptId: string,
        userId: string,
        target: string,
    ): CancelablePromise<ConfigBackupListOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/backup/list',
            query: {
                'scriptId': scriptId,
                'userId': userId,
                'target': target,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 按需归档目标池当前配置（指纹去重，无变化跳过；编辑界面进入/退出时机调用）
     * target 取值由专项池定义（如 zzz-od 的 mas/onedragon、ok-nte 的 mas/native）。
     * @param requestBody
     * @returns ConfigBackupEnsureOut Successful Response
     * @throws ApiError
     */
    public static ensureConfigBackupApiApiScriptsBackupEnsurePost(
        requestBody: ConfigBackupEnsureIn,
    ): CancelablePromise<ConfigBackupEnsureOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/backup/ensure',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 把指定备份恢复到目标位置（恢复前自动存底当前配置，误恢复可找回）
     * 恢复语义由专项池定义：脚本原生池恢复到脚本本体，MAS 用户池恢复到
     * 用户配置并按需回填前端表单。备份来自其他配置来源（脚本级/用户级）时
     * 由服务层把配置来源切回备份时点再恢复；提示由前端据备份列表与当前
     * 来源比对给出。
     * @param requestBody
     * @returns ConfigBackupRestoreOut Successful Response
     * @throws ApiError
     */
    public static restoreConfigBackupApiApiScriptsBackupRestorePost(
        requestBody: ConfigBackupRestoreIn,
    ): CancelablePromise<ConfigBackupRestoreOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/backup/restore',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 读取指定备份的配置摘要（纯读不恢复，供「预览配置」快速展示）
     * data 载荷结构由专项定义（前端按 target 消费）；非法 target 返回 400。
     * @param scriptId
     * @param userId
     * @param time
     * @param target
     * @returns ConfigBackupPreviewOut Successful Response
     * @throws ApiError
     */
    public static getConfigBackupPreviewApiApiScriptsBackupPreviewGet(
        scriptId: string,
        userId: string,
        time: string,
        target: string,
    ): CancelablePromise<ConfigBackupPreviewOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/backup/preview',
            query: {
                'scriptId': scriptId,
                'userId': userId,
                'time': time,
                'target': target,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 只读读取指定备份内一个文本文件（预览「查看原始文件」用，路径限归档内）
     * 路径越界/文件超限/池未实现查看能力均返回 400，message 说明原因。
     * @param scriptId
     * @param userId
     * @param time
     * @param target
     * @param path
     * @returns ConfigBackupFileOut Successful Response
     * @throws ApiError
     */
    public static getConfigBackupFileApiApiScriptsBackupFileGet(
        scriptId: string,
        userId: string,
        time: string,
        target: string,
        path: string,
    ): CancelablePromise<ConfigBackupFileOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/backup/file',
            query: {
                'scriptId': scriptId,
                'userId': userId,
                'time': time,
                'target': target,
                'path': path,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
