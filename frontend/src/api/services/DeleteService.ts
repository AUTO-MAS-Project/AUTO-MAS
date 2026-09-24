/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2InstanceDeleteIn } from '../models/Emulator2InstanceDeleteIn';
import type { Emulator2InstanceDeleteOut } from '../models/Emulator2InstanceDeleteOut';
import type { Emulator2PathRemoveIn } from '../models/Emulator2PathRemoveIn';
import type { Emulator2PathRemoveOut } from '../models/Emulator2PathRemoveOut';
import type { EmulatorDeleteIn } from '../models/EmulatorDeleteIn';
import type { OutBase } from '../models/OutBase';
import type { PlanDeleteIn } from '../models/PlanDeleteIn';
import type { QueueDeleteIn } from '../models/QueueDeleteIn';
import type { QueueItemDeleteIn } from '../models/QueueItemDeleteIn';
import type { ScriptDeleteIn } from '../models/ScriptDeleteIn';
import type { TimeSetDeleteIn } from '../models/TimeSetDeleteIn';
import type { UserDeleteIn } from '../models/UserDeleteIn';
import type { WebhookDeleteIn } from '../models/WebhookDeleteIn';
import type { ZzzOdInstanceDeleteIn } from '../models/ZzzOdInstanceDeleteIn';
import type { ZzzOdInstancesOut } from '../models/ZzzOdInstancesOut';
import type { ZzzOdRecycleClearIn } from '../models/ZzzOdRecycleClearIn';
import type { ZzzOdRecycleClearOut } from '../models/ZzzOdRecycleClearOut';
import type { ZzzOdRecycleRestoreIn } from '../models/ZzzOdRecycleRestoreIn';
import type { ZzzOdSlotCleanIn } from '../models/ZzzOdSlotCleanIn';
import type { ZzzOdSlotCleanOut } from '../models/ZzzOdSlotCleanOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DeleteService {
    /**
     * 删除脚本
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteScriptApiScriptsDeletePost(
        requestBody: ScriptDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除用户
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteUserApiScriptsUserDeletePost(
        requestBody: UserDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/user/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除webhook项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteWebhookApiScriptsWebhookDeletePost(
        requestBody: WebhookDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/webhook/delete',
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
     * 清理无主实例槽（先归档进回收池再删目录）
     * 原生实例与被任一 ZzzOd 用户绑定的槽一律不动，返回实际回收的槽号。
     * @param requestBody
     * @returns ZzzOdSlotCleanOut Successful Response
     * @throws ApiError
     */
    public static cleanZzzodSlotsApiApiScriptsZzzodSlotsCleanPost(
        requestBody: ZzzOdSlotCleanIn,
    ): CancelablePromise<ZzzOdSlotCleanOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/slots/clean',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 清空实例槽回收池（删除后不可找回，不碰配置恢复池）
     * 只删 recycle 池；onedragon 原生池与 mas 配置恢复池不受影响。
     * @param requestBody
     * @returns ZzzOdRecycleClearOut Successful Response
     * @throws ApiError
     */
    public static clearZzzodRecycleApiApiScriptsZzzodRecycleClearPost(
        requestBody: ZzzOdRecycleClearIn,
    ): CancelablePromise<ZzzOdRecycleClearOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/recycle/clear',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 把回收池里的槽快照恢复给某个 MAS 用户（现有用户或新建用户，先存底）
     * 恢复的落点是**用户的绑定槽**（``targetUser`` 指定现有用户，或
     * ``newUserName`` 新建一个用户）——只物化内容而不建立绑定的恢复没有出口，
     * MAS 下次运行不会认领它。目标用户已有绑定槽时覆盖其内容，恢复前先存底。
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static restoreZzzodRecycleApiApiScriptsZzzodRecycleRestorePost(
        requestBody: ZzzOdRecycleRestoreIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/recycle/restore',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除计划表
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deletePlanApiPlanDeletePost(
        requestBody: PlanDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plan/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除模拟器项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteEmulatorApiEmulatorDeletePost(
        requestBody: EmulatorDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 移除模拟器路径
     * 移除一条路径。设备号**失效并保留**，不会再分配给其他设备。
     * @param requestBody
     * @returns Emulator2PathRemoveOut Successful Response
     * @throws ApiError
     */
    public static removePathApiEmulator2PathsRemovePost(
        requestBody: Emulator2PathRemoveIn,
    ): CancelablePromise<Emulator2PathRemoveOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/paths/remove',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除模拟器实例
     * 删除一个实例。实例必须先关闭。
     *
     * 设备号不写墓碑——以后在同一原生索引重建实例仍然是这个设备号；
     * 在那之前该设备号显示为「未找到」，绑定它的脚本下一次执行直接失败。
     * @param requestBody
     * @returns Emulator2InstanceDeleteOut Successful Response
     * @throws ApiError
     */
    public static deleteInstanceApiEmulator2InstancesDeletePost(
        requestBody: Emulator2InstanceDeleteIn,
    ): CancelablePromise<Emulator2InstanceDeleteOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/instances/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除调度队列
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteQueueApiQueueDeletePost(
        requestBody: QueueDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除定时项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteTimeSetApiQueueTimeDeletePost(
        requestBody: TimeSetDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/time/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除队列项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteItemApiQueueItemDeletePost(
        requestBody: QueueItemDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/item/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除webhook项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteWebhookApiSettingWebhookDeletePost(
        requestBody: WebhookDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/webhook/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
