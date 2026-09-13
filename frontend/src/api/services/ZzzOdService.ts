/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OutBase } from '../models/OutBase';
import type { ZzzOdAppConfigOut } from '../models/ZzzOdAppConfigOut';
import type { ZzzOdAppConfigSaveIn } from '../models/ZzzOdAppConfigSaveIn';
import type { ZzzOdCatalogOut } from '../models/ZzzOdCatalogOut';
import type { ZzzOdImportIn } from '../models/ZzzOdImportIn';
import type { ZzzOdImportOut } from '../models/ZzzOdImportOut';
import type { ZzzOdInstanceActiveIn } from '../models/ZzzOdInstanceActiveIn';
import type { ZzzOdInstanceAddIn } from '../models/ZzzOdInstanceAddIn';
import type { ZzzOdInstanceDeleteIn } from '../models/ZzzOdInstanceDeleteIn';
import type { ZzzOdInstanceFlagIn } from '../models/ZzzOdInstanceFlagIn';
import type { ZzzOdInstanceForceLoginIn } from '../models/ZzzOdInstanceForceLoginIn';
import type { ZzzOdInstanceRenameIn } from '../models/ZzzOdInstanceRenameIn';
import type { ZzzOdInstanceRunModeIn } from '../models/ZzzOdInstanceRunModeIn';
import type { ZzzOdInstancesOut } from '../models/ZzzOdInstancesOut';
import type { ZzzOdLauncherOut } from '../models/ZzzOdLauncherOut';
import type { ZzzOdNativeConfigIn } from '../models/ZzzOdNativeConfigIn';
import type { ZzzOdNativeConfigOut } from '../models/ZzzOdNativeConfigOut';
import type { ZzzOdTaskOptionsOut } from '../models/ZzzOdTaskOptionsOut';
import type { ZzzOdTeamsOut } from '../models/ZzzOdTeamsOut';
import type { ZzzOdTeamsSaveIn } from '../models/ZzzOdTeamsSaveIn';
import type { ZzzOdTeamsSaveOut } from '../models/ZzzOdTeamsSaveOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ZzzOdService {
    /**
     * 获取 zzz-od 实例（账号）列表
     * 返回 zzz-od 实例列表（供「快速导入」选择来源实例）。
     * @param scriptId
     * @returns ZzzOdInstancesOut Successful Response
     * @throws ApiError
     */
    public static getZzzodInstancesApiApiScriptsZzzodInstancesGet(
        scriptId: string,
    ): CancelablePromise<ZzzOdInstancesOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/zzzod/instances',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 新建一条龙实例（直控实例管理）
     * 创建实例（最小空闲槽，避开原生与跨脚本 MAS 绑定槽），返回更新后的实例列表。
     * @param requestBody
     * @returns ZzzOdInstancesOut Successful Response
     * @throws ApiError
     */
    public static addZzzodInstanceApiApiScriptsZzzodInstancesAddPost(
        requestBody: ZzzOdInstanceAddIn,
    ): CancelablePromise<ZzzOdInstancesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/instances/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 重命名一条龙实例（直控实例管理）
     * 只改注册表 name（实例目录不变），返回更新后的实例列表。
     * @param requestBody
     * @returns ZzzOdInstancesOut Successful Response
     * @throws ApiError
     */
    public static renameZzzodInstanceApiApiScriptsZzzodInstancesRenamePost(
        requestBody: ZzzOdInstanceRenameIn,
    ): CancelablePromise<ZzzOdInstancesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/instances/rename',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 切换实例是否参与「全部实例」运行（直控实例管理）
     * 切换 active_in_od 标志位，返回更新后的实例列表。
     * @param requestBody
     * @returns ZzzOdInstancesOut Successful Response
     * @throws ApiError
     */
    public static setZzzodInstanceActiveInOdApiApiScriptsZzzodInstancesActiveInOdPost(
        requestBody: ZzzOdInstanceFlagIn,
    ): CancelablePromise<ZzzOdInstancesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/instances/active-in-od',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 把所选实例设为当前活跃（直控「选择即运行」）
     * 把目标实例设为注册表 active（其余清 False），返回更新后的实例列表。
     * @param requestBody
     * @returns ZzzOdInstancesOut Successful Response
     * @throws ApiError
     */
    public static setZzzodActiveInstanceApiApiScriptsZzzodInstancesSetActivePost(
        requestBody: ZzzOdInstanceActiveIn,
    ): CancelablePromise<ZzzOdInstancesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/instances/set-active',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 切换实例「运行前切换账号」（直控实例管理；一条龙原生能力）
     * 切换实例条目的 force_login_before_run（一条龙自己消费），返回更新后的实例列表。
     * @param requestBody
     * @returns ZzzOdInstancesOut Successful Response
     * @throws ApiError
     */
    public static setZzzodInstanceForceLoginApiApiScriptsZzzodInstancesForceLoginPost(
        requestBody: ZzzOdInstanceForceLoginIn,
    ): CancelablePromise<ZzzOdInstancesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/instances/force-login',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 设置运行实例（直控；one_dragon.yml 全局 instance_run）
     * 白名单校验后写回全局 instance_run（与直控页当前编辑哪个实例无关）。
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static setZzzodInstanceRunModeApiApiScriptsZzzodInstancesRunModePost(
        requestBody: ZzzOdInstanceRunModeIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/instances/run-mode',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除一条龙实例（直控实例管理；受 MAS 绑定槽保护）
     * 删除注册表条目与实例目录，返回更新后的实例列表。
     * @param requestBody
     * @returns ZzzOdInstancesOut Successful Response
     * @throws ApiError
     */
    public static deleteZzzodInstanceApiApiScriptsZzzodInstancesDeletePost(
        requestBody: ZzzOdInstanceDeleteIn,
    ): CancelablePromise<ZzzOdInstancesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/instances/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取预备编队列表（名称 + 绑定配队方案）
     * 读绑定槽（直控传 instanceIdx 读原生实例）的 team.yml（固定 20 个编队）。
     * @param scriptId
     * @param userId
     * @param instanceIdx
     * @returns ZzzOdTeamsOut Successful Response
     * @throws ApiError
     */
    public static getZzzodTeamsApiApiScriptsZzzodTeamsGet(
        scriptId: string,
        userId: string,
        instanceIdx?: (number | null),
    ): CancelablePromise<ZzzOdTeamsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/zzzod/teams',
            query: {
                'scriptId': scriptId,
                'userId': userId,
                'instanceIdx': instanceIdx,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 整表保存预备编队（名称 + 绑定配队方案；成员按行保留）
     * 直控传 instanceIdx 直接写原生实例，缺省写用户绑定槽。
     * @param requestBody
     * @returns ZzzOdTeamsSaveOut Successful Response
     * @throws ApiError
     */
    public static saveZzzodTeamsApiApiScriptsZzzodTeamsSavePost(
        requestBody: ZzzOdTeamsSaveIn,
    ): CancelablePromise<ZzzOdTeamsSaveOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/teams/save',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取一条龙任务目录
     * 静态解析安装目录下的应用注册信息，供用户配置渲染任务卡片中文名。
     * @param scriptId
     * @returns ZzzOdCatalogOut Successful Response
     * @throws ApiError
     */
    public static getZzzodCatalogApiApiScriptsZzzodCatalogGet(
        scriptId: string,
    ): CancelablePromise<ZzzOdCatalogOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/zzzod/catalog',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取任务级配置（字段元数据 + 当前值）
     * 返回任务可配置字段、选项与当前值（直控传 instanceIdx 读原生实例，否则读绑定槽）。
     * @param scriptId
     * @param userId
     * @param appId
     * @param instanceIdx
     * @returns ZzzOdAppConfigOut Successful Response
     * @throws ApiError
     */
    public static getZzzodAppConfigApiApiScriptsZzzodAppConfigGet(
        scriptId: string,
        userId: string,
        appId: string,
        instanceIdx?: (number | null),
    ): CancelablePromise<ZzzOdAppConfigOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/zzzod/app-config',
            query: {
                'scriptId': scriptId,
                'userId': userId,
                'appId': appId,
                'instanceIdx': instanceIdx,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取任务计划的动态选项（副本级联树/配队方案/挑战配置）
     * 静态读取安装目录（compendium 数据 + 配置目录扫描），与一条龙原生 GUI 选项同源。
     * @param scriptId
     * @param appId
     * @returns ZzzOdTaskOptionsOut Successful Response
     * @throws ApiError
     */
    public static getZzzodTaskOptionsApiApiScriptsZzzodOptionsGet(
        scriptId: string,
        appId: string,
    ): CancelablePromise<ZzzOdTaskOptionsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/zzzod/options',
            query: {
                'scriptId': scriptId,
                'appId': appId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 保存任务级配置（绑定槽；直控传 instanceIdx 直接写原生实例）
     * 字段白名单校验后写入 per-app YAML（缺省写用户绑定槽，直控写指定原生实例）。
     * @param requestBody
     * @returns ZzzOdAppConfigOut Successful Response
     * @throws ApiError
     */
    public static saveZzzodAppConfigApiApiScriptsZzzodAppConfigSavePost(
        requestBody: ZzzOdAppConfigSaveIn,
    ): CancelablePromise<ZzzOdAppConfigOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/app-config/save',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取实例原生配置（直控页面表单数据）
     * 读取所选实例 game_account.yml 与 _group.yml（含默认值合并与任务目录并入）。
     * @param scriptId
     * @param instanceIdx
     * @returns ZzzOdNativeConfigOut Successful Response
     * @throws ApiError
     */
    public static getZzzodNativeConfigApiApiScriptsZzzodNativeConfigGet(
        scriptId: string,
        instanceIdx: number,
    ): CancelablePromise<ZzzOdNativeConfigOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/zzzod/native-config',
            query: {
                'scriptId': scriptId,
                'instanceIdx': instanceIdx,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 保存实例原生配置（直控模式直接写回一条龙原始 YAML）
     * 白名单过滤后写回所选实例 game_account.yml、_group.yml 与 instance_run，随后回读最新数据。
     * @param requestBody
     * @returns ZzzOdNativeConfigOut Successful Response
     * @throws ApiError
     */
    public static saveZzzodNativeConfigApiApiScriptsZzzodNativeConfigSavePost(
        requestBody: ZzzOdNativeConfigIn,
    ): CancelablePromise<ZzzOdNativeConfigOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/native-config/save',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取一条龙两种启动器的安装情况与默认项
     * 渲染「启动器」下拉用（直控/用户两态通用）：未安装的启动器选项禁用变灰。
     * @param scriptId
     * @returns ZzzOdLauncherOut Successful Response
     * @throws ApiError
     */
    public static getZzzodLaunchersApiApiScriptsZzzodLaunchersGet(
        scriptId: string,
    ): CancelablePromise<ZzzOdLauncherOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/zzzod/launchers',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 基于一条龙已有实例快速生成当前用户配置（覆盖前自动归档当前配置）
     * 把来源实例的账号信息与已启用任务编排写入本用户；覆盖前强制归档当前 MAS 槽配置，
     * 导入前状态可在「配置恢复」中找回。
     * @param requestBody
     * @returns ZzzOdImportOut Successful Response
     * @throws ApiError
     */
    public static importZzzodConfigApiApiScriptsZzzodImportPost(
        requestBody: ZzzOdImportIn,
    ): CancelablePromise<ZzzOdImportOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/import',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
