/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWAgentEnvPrepareIn } from '../models/MaaFWAgentEnvPrepareIn';
import type { MaaFWAgentEnvPrepareOut } from '../models/MaaFWAgentEnvPrepareOut';
import type { MaaFWGamePackageIn } from '../models/MaaFWGamePackageIn';
import type { MaaFWGamePackageOut } from '../models/MaaFWGamePackageOut';
import type { MaaFWInterfacePreviewIn } from '../models/MaaFWInterfacePreviewIn';
import type { MaaFWInterfacePreviewOut } from '../models/MaaFWInterfacePreviewOut';
import type { MaaFWProjectUpdateIn } from '../models/MaaFWProjectUpdateIn';
import type { MaaFWProjectUpdateOut } from '../models/MaaFWProjectUpdateOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class MaaFwService {
    /**
     * 按所选 resource 推断 MFW 项目的安卓游戏包名
     * 脚本编辑页读完 interface / 切换 resource 时调用，把推出来的包名直接填进表单。
     *
     * 只看 resource 的 pipeline，不带用户任务的 pipeline_override（编辑脚本时还没有
     * 运行计划）；推不出或多个候选都按原样返回，由前端决定不填。
     * @param requestBody
     * @returns MaaFWGamePackageOut Successful Response
     * @throws ApiError
     */
    public static resolveMaafwGamePackageApiScriptsMaafwGamePackagePost(
        requestBody: MaaFWGamePackageIn,
    ): CancelablePromise<MaaFWGamePackageOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/game-package',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 预览 MFW interface
     * 读取 MaaFW 项目 interface，并返回 controller/resource/task 摘要。
     * @param requestBody
     * @returns MaaFWInterfacePreviewOut Successful Response
     * @throws ApiError
     */
    public static previewMaafwInterfaceApiScriptsMaafwPreviewPost(
        requestBody: MaaFWInterfacePreviewIn,
    ): CancelablePromise<MaaFWInterfacePreviewOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 检查或执行 MFW 项目更新
     * 按脚本 ``Update.*`` 配置检查或应用 MaaFW 项目目录更新。
     *
     * ``action=check`` 只读取 interface 版本与更新源元数据，返回是否有新版本；
     * ``action=apply`` 触发下载并原地应用更新包。失败时返回明确 ``message``。
     * @param requestBody
     * @returns MaaFWProjectUpdateOut Successful Response
     * @throws ApiError
     */
    public static updateMaafwProjectApiScriptsMaafwUpdatePost(
        requestBody: MaaFWProjectUpdateIn,
    ): CancelablePromise<MaaFWProjectUpdateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 预备 MFW 运行环境
     * 按项目 interface 预备 Runner 运行时与各 agent 的 Python 环境。
     *
     * 在项目引导里读到 interface 之后调用，把首次运行才会付出的下载与建环境
     * 成本提前到配置阶段。与 ``/maafw/update`` 一样是同步端点：整个准备过程
     * 在请求内完成，首次冷启动可能耗时数分钟。
     *
     * 编辑页每打开一次就会调一次，所以先比一遍项目输入指纹：项目没更新过、上次
     * 准备的环境也还在盘上，就直接还回上次的结果，不再取锁起进程。用户手动重试
     * 时前端带 ``force``，跳过这层缓存。
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
     * 读取 MFW 项目内的图片资源
     * 把 MFW 项目目录内的图片按需读给前端。
     *
     * 任务说明（interface 的 ``doc`` / ``description``）是 markdown，里面的图片写的是
     * **项目内相对路径**，浏览器没法直接读本地文件，必须由后端转一手。
     *
     * 前端侧对应 ``buildMaaFWAssetUrl``：它已经拦掉了绝对路径、UNC、上跳与远程 URL，
     * 但那只是省一次往返，安全边界在这里 —— 请求可以绕过前端直接打过来。
     * @param root MFW 项目根目录
     * @param path 项目根目录内的相对图片路径
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
}
