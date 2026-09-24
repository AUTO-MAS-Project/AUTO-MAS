/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWAgentEnvPrepareIn } from '../models/MaaFWAgentEnvPrepareIn';
import type { MaaFWAgentEnvPrepareOut } from '../models/MaaFWAgentEnvPrepareOut';
import type { MaaFWEmbeddedCloneIn } from '../models/MaaFWEmbeddedCloneIn';
import type { MaaFWEmbeddedIn } from '../models/MaaFWEmbeddedIn';
import type { MaaFWEmbeddedReimportIn } from '../models/MaaFWEmbeddedReimportIn';
import type { MaaFWEmbeddedSourcesIn } from '../models/MaaFWEmbeddedSourcesIn';
import type { MaaFWEmbeddedSourcesOut } from '../models/MaaFWEmbeddedSourcesOut';
import type { MaaFWEmbeddedStatusOut } from '../models/MaaFWEmbeddedStatusOut';
import type { MaaFWGamePackageIn } from '../models/MaaFWGamePackageIn';
import type { MaaFWGamePackageOut } from '../models/MaaFWGamePackageOut';
import type { MaaFWInterfacePreviewIn } from '../models/MaaFWInterfacePreviewIn';
import type { MaaFWInterfacePreviewOut } from '../models/MaaFWInterfacePreviewOut';
import type { MaaFWProjectUpdateIn } from '../models/MaaFWProjectUpdateIn';
import type { MaaFWProjectUpdateOut } from '../models/MaaFWProjectUpdateOut';
import type { MaaFWShellInstanceImportIn } from '../models/MaaFWShellInstanceImportIn';
import type { MaaFWShellInstanceImportOut } from '../models/MaaFWShellInstanceImportOut';
import type { MaaFWShellInstancesIn } from '../models/MaaFWShellInstancesIn';
import type { MaaFWShellInstancesOut } from '../models/MaaFWShellInstancesOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class MaaFwService {
    /**
     * 查看 MFW 脚本的内嵌副本状态
     * @param requestBody
     * @returns MaaFWEmbeddedStatusOut Successful Response
     * @throws ApiError
     */
    public static getMaafwEmbeddedStatusApiScriptsMaafwEmbeddedStatusPost(
        requestBody: MaaFWEmbeddedIn,
    ): CancelablePromise<MaaFWEmbeddedStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/embedded/status',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 按来源目录导入（或重新导入）副本
     * 脚本页选目录就是走这里：第一次是导入，之后是换来源或按当前来源重导。
     *
     * 导入成功才把来源写进 Info.Path；失败时旧副本与旧来源都原样不动。
     * @param requestBody
     * @returns MaaFWEmbeddedStatusOut Successful Response
     * @throws ApiError
     */
    public static reimportMaafwEmbeddedApiScriptsMaafwEmbeddedReimportPost(
        requestBody: MaaFWEmbeddedReimportIn,
    ): CancelablePromise<MaaFWEmbeddedStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/embedded/reimport',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 列出可作为克隆来源的其它 MFW 脚本
     * 新建脚本对话框里「复用已有脚本的项目」的候选：有健康副本的 MFW / M9A 脚本。
     *
     * 新建时脚本还没建出来，所以不要求 ``scriptId``；传了就把它自己排除掉。
     * @param requestBody
     * @returns MaaFWEmbeddedSourcesOut Successful Response
     * @throws ApiError
     */
    public static listMaafwEmbeddedSourcesApiScriptsMaafwEmbeddedSourcesPost(
        requestBody?: MaaFWEmbeddedSourcesIn,
    ): CancelablePromise<MaaFWEmbeddedSourcesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/embedded/sources',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 从另一个 MFW 脚本的副本克隆，同一项目再建一个脚本
     * 同一个项目要开第二、第三个脚本（不同模拟器并行跑）时走这里，不用再选目录
     * 重新投影，来源目录已经删了也能建。
     *
     * 副本从源脚本的副本硬链接克隆（运行时、模型与其它副本共用，只多小文件），
     * ``Info.Path`` 与 ``Embedded.*`` 沿用源脚本的记录；类型随项目（M9A 项目 → M9A）。
     * 用户、任务队列与运行设置不带——那是「复制脚本」的事。
     * @param requestBody
     * @returns MaaFWEmbeddedStatusOut Successful Response
     * @throws ApiError
     */
    public static cloneMaafwEmbeddedApiScriptsMaafwEmbeddedClonePost(
        requestBody: MaaFWEmbeddedCloneIn,
    ): CancelablePromise<MaaFWEmbeddedStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/embedded/clone',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 列出项目目录里外壳（MFAAvalonia / MXU / MFW-PyQt6）保存的配置实例
     * 新建脚本引导最后一步用：外壳里配好的每份实例都可以导入成一个用户。只读外壳文件。
     * @param requestBody
     * @returns MaaFWShellInstancesOut Successful Response
     * @throws ApiError
     */
    public static listMaafwShellInstancesApiScriptsMaafwShellInstancesPost(
        requestBody: MaaFWShellInstancesIn,
    ): CancelablePromise<MaaFWShellInstancesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/shell-instances',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 把选中的外壳配置实例导入成用户
     * 每个实例建一个用户：用户名取实例名，任务队列与任务选项一起导入。
     *
     * 逐个实例独立处理，失败原因与当前项目里对不上而跳过的任务 / 选项写在各项结果里。
     * @param requestBody
     * @returns MaaFWShellInstanceImportOut Successful Response
     * @throws ApiError
     */
    public static importMaafwShellInstancesApiScriptsMaafwShellInstancesImportPost(
        requestBody: MaaFWShellInstanceImportIn,
    ): CancelablePromise<MaaFWShellInstanceImportOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/shell-instances/import',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
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
