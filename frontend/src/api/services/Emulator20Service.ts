/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2DevicesIn } from '../models/Emulator2DevicesIn';
import type { Emulator2DevicesOut } from '../models/Emulator2DevicesOut';
import type { Emulator2GuardCaptureOut } from '../models/Emulator2GuardCaptureOut';
import type { Emulator2InstanceCreateIn } from '../models/Emulator2InstanceCreateIn';
import type { Emulator2InstanceCreateOut } from '../models/Emulator2InstanceCreateOut';
import type { Emulator2InstanceDeleteIn } from '../models/Emulator2InstanceDeleteIn';
import type { Emulator2InstanceDeleteOut } from '../models/Emulator2InstanceDeleteOut';
import type { Emulator2InstanceDeletePreviewOut } from '../models/Emulator2InstanceDeletePreviewOut';
import type { Emulator2PathAddIn } from '../models/Emulator2PathAddIn';
import type { Emulator2PathAddOut } from '../models/Emulator2PathAddOut';
import type { Emulator2PathRemoveIn } from '../models/Emulator2PathRemoveIn';
import type { Emulator2PathRemoveOut } from '../models/Emulator2PathRemoveOut';
import type { Emulator2PathRemovePreviewOut } from '../models/Emulator2PathRemovePreviewOut';
import type { Emulator2SearchIn } from '../models/Emulator2SearchIn';
import type { Emulator2SearchOut } from '../models/Emulator2SearchOut';
import type { Emulator2SettingsApplyAllIn } from '../models/Emulator2SettingsApplyAllIn';
import type { Emulator2SettingsApplyAllOut } from '../models/Emulator2SettingsApplyAllOut';
import type { Emulator2SettingsApplyIn } from '../models/Emulator2SettingsApplyIn';
import type { Emulator2SettingsApplyOut } from '../models/Emulator2SettingsApplyOut';
import type { Emulator2StableModeIn } from '../models/Emulator2StableModeIn';
import type { Emulator2StoreOpenIn } from '../models/Emulator2StoreOpenIn';
import type { Emulator2StoreOpenOut } from '../models/Emulator2StoreOpenOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class Emulator20Service {
    /**
     * 搜索可加入 Emulator 2.0 的模拟器
     * 列出本机模拟器并逐条判定。不可添加的**也会列出**并给出原因枚举。
     * @param requestBody
     * @returns Emulator2SearchOut Successful Response
     * @throws ApiError
     */
    public static searchEmulatorsApiEmulator2SearchPost(
        requestBody?: Emulator2SearchIn,
    ): CancelablePromise<Emulator2SearchOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/search',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 添加模拟器路径
     * 探测版本 → 落库 → 为该安装的实例分配设备号。
     *
     * 版本不合要求时返回 ``ok=False`` 与原因枚举，而不是抛错。
     * @param requestBody
     * @returns Emulator2PathAddOut Successful Response
     * @throws ApiError
     */
    public static addPathApiEmulator2PathsAddPost(
        requestBody: Emulator2PathAddIn,
    ): CancelablePromise<Emulator2PathAddOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/paths/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 预览移除模拟器路径的影响
     * 只读。列出会失效的设备号与受影响的脚本，供确认页使用。
     * @param requestBody
     * @returns Emulator2PathRemovePreviewOut Successful Response
     * @throws ApiError
     */
    public static previewRemovePathApiEmulator2PathsRemovePreviewPost(
        requestBody: Emulator2PathRemoveIn,
    ): CancelablePromise<Emulator2PathRemovePreviewOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/paths/remove/preview',
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
     * 查询合并后的设备列表
     * 合并多条安装的实例。键是设备号，另附模拟器自己的实例索引。
     *
     * 枚举失败的安装标 ``unavailable``——一次枚举失败不等于实例被删除，
     * 既不写墓碑也不影响下次恢复。``withSettings=false`` 只取状态，给轮询用。
     * @param requestBody
     * @returns Emulator2DevicesOut Successful Response
     * @throws ApiError
     */
    public static listDevicesApiEmulator2DevicesPost(
        requestBody: Emulator2DevicesIn,
    ): CancelablePromise<Emulator2DevicesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/devices',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 新建模拟器实例
     * 在某条模拟器安装下新建一个实例，并给它分配设备号。
     *
     * 新建成功与否**不看命令返回码**——雷电新建成功时返回码也不为 0，
     * 判据是列表里有没有多出实例。
     * @param requestBody
     * @returns Emulator2InstanceCreateOut Successful Response
     * @throws ApiError
     */
    public static createInstanceApiEmulator2InstancesCreatePost(
        requestBody: Emulator2InstanceCreateIn,
    ): CancelablePromise<Emulator2InstanceCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/instances/create',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 预览删除实例的影响
     * 只读。列出绑定了该设备号的脚本，供确认页使用。
     * @param requestBody
     * @returns Emulator2InstanceDeletePreviewOut Successful Response
     * @throws ApiError
     */
    public static previewDeleteInstanceApiEmulator2InstancesDeletePreviewPost(
        requestBody: Emulator2InstanceDeleteIn,
    ): CancelablePromise<Emulator2InstanceDeletePreviewOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/instances/delete/preview',
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
     * 打开游戏中心
     * 在一台**已在线**的设备上打开模拟器自带的游戏中心。
     *
     * 雷电纯净模式会把游戏中心从桌面藏掉，这是它唯一的图形入口。
     * 拉不起来返回 ``ok=false`` 和一句说明，不算接口错误；只有设备号解析不出来才是 500。
     * @param requestBody
     * @returns Emulator2StoreOpenOut Successful Response
     * @throws ApiError
     */
    public static openStoreApiEmulator2InstancesStoreOpenPost(
        requestBody: Emulator2StoreOpenIn,
    ): CancelablePromise<Emulator2StoreOpenOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/instances/store/open',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 修改实例设置
     * 写一台设备的设置。
     *
     * 只提交用户改过的字段；``expected`` 与文件现状对不上就拒绝写入并交回冲突字段，
     * 绝不把表单打开时的旧值整片盖回去。
     * @param requestBody
     * @returns Emulator2SettingsApplyOut Successful Response
     * @throws ApiError
     */
    public static applySettingsApiEmulator2SettingsApplyPost(
        requestBody: Emulator2SettingsApplyIn,
    ): CancelablePromise<Emulator2SettingsApplyOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/settings/apply',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 批量修改全部实例设置
     * 把同一组设置写到全部实例上。
     *
     * 没有勾选也没有冲突比对——点它就是明确要求「所有实例都设成这组值」。
     * 一台失败不影响其余，逐台交回结果。
     * @param requestBody
     * @returns Emulator2SettingsApplyAllOut Successful Response
     * @throws ApiError
     */
    public static applySettingsToAllApiEmulator2SettingsApplyAllPost(
        requestBody: Emulator2SettingsApplyAllIn,
    ): CancelablePromise<Emulator2SettingsApplyAllOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/settings/apply-all',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 应用稳定模式
     * 把设备切进稳定模式：关掉会干扰截图识别的模拟器功能。
     *
     * ``slots`` 留空表示全部。每台交回实际改动了哪几项；已经安全的返回空改动列表。
     * **关掉稳定模式不由这个接口负责**——我们不知道用户原来想要什么值，不替他猜。
     * @param requestBody
     * @returns Emulator2SettingsApplyAllOut Successful Response
     * @throws ApiError
     */
    public static applyStableModeApiEmulator2StableModeApplyPost(
        requestBody: Emulator2StableModeIn,
    ): CancelablePromise<Emulator2SettingsApplyAllOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/stable-mode/apply',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 记录配置守卫的基准
     * 把当前所有设备的设置记成守卫基准。开启守卫时调一次。
     *
     * 只记用户显式设过的字段：模拟器默认值和从没设过的项没有「应该是什么」可言，
     * 写进基准等于替用户决定。
     * @param requestBody
     * @returns Emulator2GuardCaptureOut Successful Response
     * @throws ApiError
     */
    public static captureBaselinesApiEmulator2GuardCapturePost(
        requestBody: Emulator2DevicesIn,
    ): CancelablePromise<Emulator2GuardCaptureOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/guard/capture',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
