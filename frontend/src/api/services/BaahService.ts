/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BlueArchiveActivityStatusOut } from '../models/BlueArchiveActivityStatusOut';
import type { ComboBoxOut } from '../models/ComboBoxOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class BaahService {
    /**
     * 获取 BAAH 配置文件名列表
     * 返回 BAAH 配置目录下已有的配置文件名（不含 ``.json`` 后缀）。
     *
     * 配置目录由脚本配置里的主程序路径派生（``BAAH.exe`` 同级的 ``BAAH_CONFIGS``），
     * 与运行时读写的是同一个目录，供界面下拉选择，避免手输一个不存在的配置名。
     * @param scriptId
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getBaahConfigNamesApiApiScriptsBaahConfigNamesGet(
        scriptId: string,
    ): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/baah/config-names',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取碧蓝档案活动状态
     * 返回指定服正在进行的活动，没有则返回下一个未开始的活动。
     *
     * 与 BAAH 活动适配用的是同一份数据、同一套口径（只认「活动」分类，同一
     * 活动被拆成多条时保留结束最晚的那条），界面据此显示当前会按哪一边切换。
     * @param lineType
     * @returns BlueArchiveActivityStatusOut Successful Response
     * @throws ApiError
     */
    public static getBaahActivityStatusApiApiScriptsBaahActivityStatusGet(
        lineType: 'JP' | 'Globle' | 'CN' = 'CN',
    ): CancelablePromise<BlueArchiveActivityStatusOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/baah/activity-status',
            query: {
                'lineType': lineType,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
