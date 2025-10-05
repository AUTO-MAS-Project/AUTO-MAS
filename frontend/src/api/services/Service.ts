/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type {
  CancelablePromise,
  ComboBoxOut,
  DispatchIn,
  EmulatorDeleteIn,
  EmulatorDevicesIn,
  EmulatorDevicesOut,
  EmulatorGetOut,
  EmulatorOutBase,
  EmulatorSearchOut,
  EmulatorStartIn,
  EmulatorStartOut,
  EmulatorStatusIn,
  EmulatorStatusOut,
  EmulatorStopIn,
  EmulatorUpdateIn,
  GetStageIn,
  HistoryDataGetIn,
  HistoryDataGetOut,
  HistorySearchIn,
  HistorySearchOut,
  InfoOut,
  NoticeOut,
  OutBase,
  PlanCreateIn,
  PlanCreateOut,
  PlanDeleteIn,
  PlanGetIn,
  PlanGetOut,
  PlanReorderIn,
  PlanUpdateIn,
  PowerIn,
  QueueCreateOut,
  QueueDeleteIn,
  QueueGetIn,
  QueueGetOut,
  QueueItemCreateOut,
  QueueItemDeleteIn,
  QueueItemGetIn,
  QueueItemGetOut,
  QueueItemReorderIn,
  QueueItemUpdateIn,
  QueueReorderIn,
  QueueSetInBase,
  QueueUpdateIn,
  ScriptCreateIn,
  ScriptCreateOut,
  ScriptDeleteIn,
  ScriptFileIn,
  ScriptGetIn,
  ScriptGetOut,
  ScriptReorderIn,
  ScriptUpdateIn,
  ScriptUploadIn,
  ScriptUrlIn,
  SettingGetOut,
  SettingUpdateIn,
  TaskCreateIn,
  TaskCreateOut,
  TimeSetCreateOut,
  TimeSetDeleteIn,
  TimeSetGetIn,
  TimeSetGetOut,
  TimeSetReorderIn,
  TimeSetUpdateIn,
  UpdateCheckIn,
  UpdateCheckOut,
  UserCreateOut,
  UserDeleteIn,
  UserGetIn,
  UserGetOut,
  UserInBase,
  UserReorderIn,
  UserSetIn,
  UserUpdateIn,
  VersionOut,
  WebhookCreateOut,
  WebhookDeleteIn,
  WebhookGetIn,
  WebhookGetOut,
  WebhookInBase,
  WebhookReorderIn,
  WebhookTestIn,
  WebhookUpdateIn,
} from '@/api'
import { OpenAPI } from '@/api'
import { request as __request } from '../core/request'

export class Service {
  /**
   * Close
   * 关闭后端程序
   * @returns any Successful Response
   * @throws ApiError
   */
  public static closeApiCoreClosePost(): CancelablePromise<any> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/core/close',
    })
  }

  /**
   * 获取后端git版本信息
   * @returns VersionOut Successful Response
   * @throws ApiError
   */
  public static getGitVersionApiInfoVersionPost(): CancelablePromise<VersionOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/info/version',
    })
  }

  /**
   * 获取关卡号下拉框信息
   * @param requestBody
   * @returns ComboBoxOut Successful Response
   * @throws ApiError
   */
  public static getStageComboxApiInfoComboxStagePost(
    requestBody: GetStageIn
  ): CancelablePromise<ComboBoxOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/info/combox/stage',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 获取脚本下拉框信息
   * @returns ComboBoxOut Successful Response
   * @throws ApiError
   */
  public static getScriptComboxApiInfoComboxScriptPost(): CancelablePromise<ComboBoxOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/info/combox/script',
    })
  }

  /**
   * 获取可选任务下拉框信息
   * @returns ComboBoxOut Successful Response
   * @throws ApiError
   */
  public static getTaskComboxApiInfoComboxTaskPost(): CancelablePromise<ComboBoxOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/info/combox/task',
    })
  }

  /**
   * 获取可选计划下拉框信息
   * @returns ComboBoxOut Successful Response
   * @throws ApiError
   */
  public static getPlanComboxApiInfoComboxPlanPost(): CancelablePromise<ComboBoxOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/info/combox/plan',
    })
  }

  /**
   * 获取通知信息
   * @returns NoticeOut Successful Response
   * @throws ApiError
   */
  public static getNoticeInfoApiInfoNoticeGetPost(): CancelablePromise<NoticeOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/info/notice/get',
    })
  }

  /**
   * 确认通知
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static confirmNoticeApiInfoNoticeConfirmPost(): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/info/notice/confirm',
    })
  }

  /**
   * 获取配置分享中心的配置信息
   * @returns InfoOut Successful Response
   * @throws ApiError
   */
  public static getWebConfigApiInfoWebconfigPost(): CancelablePromise<InfoOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/info/webconfig',
    })
  }

  /**
   * 信息总览
   * @returns InfoOut Successful Response
   * @throws ApiError
   */
  public static getOverviewApiInfoGetOverviewPost(): CancelablePromise<InfoOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/info/get/overview',
    })
  }

  /**
   * 添加脚本
   * @param requestBody
   * @returns ScriptCreateOut Successful Response
   * @throws ApiError
   */
  public static addScriptApiScriptsAddPost(
    requestBody: ScriptCreateIn
  ): CancelablePromise<ScriptCreateOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/add',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 查询脚本配置信息
   * @param requestBody
   * @returns ScriptGetOut Successful Response
   * @throws ApiError
   */
  public static getScriptApiScriptsGetPost(
    requestBody: ScriptGetIn
  ): CancelablePromise<ScriptGetOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/get',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 更新脚本配置信息
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static updateScriptApiScriptsUpdatePost(
    requestBody: ScriptUpdateIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/update',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 删除脚本
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static deleteScriptApiScriptsDeletePost(
    requestBody: ScriptDeleteIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/delete',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 重新排序脚本
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static reorderScriptApiScriptsOrderPost(
    requestBody: ScriptReorderIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/order',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 从文件加载脚本
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static importScriptFromFileApiScriptsImportFilePost(
    requestBody: ScriptFileIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/import/file',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 导出脚本到文件
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static exportScriptToFileApiScriptsExportFilePost(
    requestBody: ScriptFileIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/export/file',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 从网络加载脚本
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static importScriptFromWebApiScriptsImportWebPost(
    requestBody: ScriptUrlIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/import/web',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 上传脚本配置到网络
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static uploadScriptToWebApiScriptsUploadWebPost(
    requestBody: ScriptUploadIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/Upload/web',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 查询用户
   * @param requestBody
   * @returns UserGetOut Successful Response
   * @throws ApiError
   */
  public static getUserApiScriptsUserGetPost(
    requestBody: UserGetIn
  ): CancelablePromise<UserGetOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/user/get',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 添加用户
   * @param requestBody
   * @returns UserCreateOut Successful Response
   * @throws ApiError
   */
  public static addUserApiScriptsUserAddPost(
    requestBody: UserInBase
  ): CancelablePromise<UserCreateOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/user/add',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 更新用户配置信息
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static updateUserApiScriptsUserUpdatePost(
    requestBody: UserUpdateIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/user/update',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 删除用户
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static deleteUserApiScriptsUserDeletePost(
    requestBody: UserDeleteIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/user/delete',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 重新排序用户
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static reorderUserApiScriptsUserOrderPost(
    requestBody: UserReorderIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/user/order',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 导入基建配置文件
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static importInfrastructureApiScriptsUserInfrastructurePost(
    requestBody: UserSetIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/user/infrastructure',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 查询 webhook 配置
   * @param requestBody
   * @returns WebhookGetOut Successful Response
   * @throws ApiError
   */
  public static getWebhookApiScriptsWebhookGetPost(
    requestBody: WebhookGetIn
  ): CancelablePromise<WebhookGetOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/webhook/get',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 添加webhook项
   * @param requestBody
   * @returns WebhookCreateOut Successful Response
   * @throws ApiError
   */
  public static addWebhookApiScriptsWebhookAddPost(
    requestBody: WebhookInBase
  ): CancelablePromise<WebhookCreateOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/webhook/add',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 更新webhook项
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static updateWebhookApiScriptsWebhookUpdatePost(
    requestBody: WebhookUpdateIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/webhook/update',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 删除webhook项
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static deleteWebhookApiScriptsWebhookDeletePost(
    requestBody: WebhookDeleteIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/webhook/delete',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 重新排序webhook项
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static reorderWebhookApiScriptsWebhookOrderPost(
    requestBody: WebhookReorderIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/scripts/webhook/order',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 添加计划表
   * @param requestBody
   * @returns PlanCreateOut Successful Response
   * @throws ApiError
   */
  public static addPlanApiPlanAddPost(requestBody: PlanCreateIn): CancelablePromise<PlanCreateOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/plan/add',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 查询计划表
   * @param requestBody
   * @returns PlanGetOut Successful Response
   * @throws ApiError
   */
  public static getPlanApiPlanGetPost(requestBody: PlanGetIn): CancelablePromise<PlanGetOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/plan/get',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 更新计划表配置信息
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static updatePlanApiPlanUpdatePost(requestBody: PlanUpdateIn): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/plan/update',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 删除计划表
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static deletePlanApiPlanDeletePost(requestBody: PlanDeleteIn): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/plan/delete',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 重新排序计划表
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static reorderPlanApiPlanOrderPost(
    requestBody: PlanReorderIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/plan/order',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 添加调度队列
   * @returns QueueCreateOut Successful Response
   * @throws ApiError
   */
  public static addQueueApiQueueAddPost(): CancelablePromise<QueueCreateOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/queue/add',
    })
  }

  /**
   * 查询调度队列配置信息
   * @param requestBody
   * @returns QueueGetOut Successful Response
   * @throws ApiError
   */
  public static getQueuesApiQueueGetPost(requestBody: QueueGetIn): CancelablePromise<QueueGetOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/queue/get',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 更新调度队列配置信息
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static updateQueueApiQueueUpdatePost(
    requestBody: QueueUpdateIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/queue/update',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 删除调度队列
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static deleteQueueApiQueueDeletePost(
    requestBody: QueueDeleteIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/queue/delete',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 重新排序
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static reorderQueueApiQueueOrderPost(
    requestBody: QueueReorderIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/queue/order',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 查询定时项
   * @param requestBody
   * @returns TimeSetGetOut Successful Response
   * @throws ApiError
   */
  public static getTimeSetApiQueueTimeGetPost(
    requestBody: TimeSetGetIn
  ): CancelablePromise<TimeSetGetOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/queue/time/get',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 添加定时项
   * @param requestBody
   * @returns TimeSetCreateOut Successful Response
   * @throws ApiError
   */
  public static addTimeSetApiQueueTimeAddPost(
    requestBody: QueueSetInBase
  ): CancelablePromise<TimeSetCreateOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/queue/time/add',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 更新定时项
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static updateTimeSetApiQueueTimeUpdatePost(
    requestBody: TimeSetUpdateIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/queue/time/update',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 删除定时项
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static deleteTimeSetApiQueueTimeDeletePost(
    requestBody: TimeSetDeleteIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/queue/time/delete',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 重新排序定时项
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static reorderTimeSetApiQueueTimeOrderPost(
    requestBody: TimeSetReorderIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/queue/time/order',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 查询队列项
   * @param requestBody
   * @returns QueueItemGetOut Successful Response
   * @throws ApiError
   */
  public static getItemApiQueueItemGetPost(
    requestBody: QueueItemGetIn
  ): CancelablePromise<QueueItemGetOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/queue/item/get',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 添加队列项
   * @param requestBody
   * @returns QueueItemCreateOut Successful Response
   * @throws ApiError
   */
  public static addItemApiQueueItemAddPost(
    requestBody: QueueSetInBase
  ): CancelablePromise<QueueItemCreateOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/queue/item/add',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 更新队列项
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static updateItemApiQueueItemUpdatePost(
    requestBody: QueueItemUpdateIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/queue/item/update',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 删除队列项
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static deleteItemApiQueueItemDeletePost(
    requestBody: QueueItemDeleteIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/queue/item/delete',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 重新排序队列项
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static reorderItemApiQueueItemOrderPost(
    requestBody: QueueItemReorderIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/queue/item/order',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 添加任务
   * @param requestBody
   * @returns TaskCreateOut Successful Response
   * @throws ApiError
   */
  public static addTaskApiDispatchStartPost(
    requestBody: TaskCreateIn
  ): CancelablePromise<TaskCreateOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/dispatch/start',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 中止任务
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static stopTaskApiDispatchStopPost(requestBody: DispatchIn): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/dispatch/stop',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 设置电源标志
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static setPowerApiDispatchSetPowerPost(requestBody: PowerIn): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/dispatch/set/power',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 取消电源任务
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static cancelPowerTaskApiDispatchCancelPowerPost(): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/dispatch/cancel/power',
    })
  }

  /**
   * 搜索历史记录总览信息
   * @param requestBody
   * @returns HistorySearchOut Successful Response
   * @throws ApiError
   */
  public static searchHistoryApiHistorySearchPost(
    requestBody: HistorySearchIn
  ): CancelablePromise<HistorySearchOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/history/search',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 从指定文件内获取历史记录数据
   * @param requestBody
   * @returns HistoryDataGetOut Successful Response
   * @throws ApiError
   */
  public static getHistoryDataApiHistoryDataPost(
    requestBody: HistoryDataGetIn
  ): CancelablePromise<HistoryDataGetOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/history/data',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 查询配置
   * 查询配置
   * @returns SettingGetOut Successful Response
   * @throws ApiError
   */
  public static getScriptsApiSettingGetPost(): CancelablePromise<SettingGetOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/get',
    })
  }

  /**
   * 更新配置
   * 更新配置
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static updateScriptApiSettingUpdatePost(
    requestBody: SettingUpdateIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/update',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 测试通知
   * 测试通知
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static testNotifyApiSettingTestNotifyPost(): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/test_notify',
    })
  }

  /**
   * 查询 webhook 配置
   * @param requestBody
   * @returns WebhookGetOut Successful Response
   * @throws ApiError
   */
  public static getWebhookApiSettingWebhookGetPost(
    requestBody: WebhookGetIn
  ): CancelablePromise<WebhookGetOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/webhook/get',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 添加webhook项
   * @returns WebhookCreateOut Successful Response
   * @throws ApiError
   */
  public static addWebhookApiSettingWebhookAddPost(): CancelablePromise<WebhookCreateOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/webhook/add',
    })
  }

  /**
   * 更新webhook项
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static updateWebhookApiSettingWebhookUpdatePost(
    requestBody: WebhookUpdateIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/webhook/update',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 删除webhook项
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static deleteWebhookApiSettingWebhookDeletePost(
    requestBody: WebhookDeleteIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/webhook/delete',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 重新排序webhook项
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static reorderWebhookApiSettingWebhookOrderPost(
    requestBody: WebhookReorderIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/webhook/order',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 测试Webhook配置
   * 测试自定义Webhook
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static testWebhookApiSettingWebhookTestPost(
    requestBody: WebhookTestIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/webhook/test',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 查询全部模拟器配置
   * 查询模拟器配置
   * @returns EmulatorGetOut Successful Response
   * @throws ApiError
   */
  public static getEmulatorsApiSettingEmulatorGetPost(): CancelablePromise<EmulatorGetOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/emulator/get',
    })
  }

  /**
   * 添加模拟器配置
   * 添加新的模拟器配置
   * @returns EmulatorOutBase Successful Response
   * @throws ApiError
   */
  public static addEmulatorApiSettingEmulatorAddPost(): CancelablePromise<EmulatorOutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/emulator/add',
    })
  }

  /**
   * 更新模拟器配置
   * 更新模拟器配置
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static updateEmulatorApiSettingEmulatorUpdatePost(
    requestBody: EmulatorUpdateIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/emulator/update',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 删除模拟器配置
   * 删除模拟器配置
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static deleteEmulatorApiSettingEmulatorDeletePost(
    requestBody: EmulatorDeleteIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/emulator/delete',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 获取模拟器设备信息
   * 获取指定模拟器下的所有设备信息
   * @param requestBody
   * @returns EmulatorDevicesOut Successful Response
   * @throws ApiError
   */
  public static getEmulatorDevicesApiSettingEmulatorDevicesPost(
    requestBody: EmulatorDevicesIn
  ): CancelablePromise<EmulatorDevicesOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/emulator/devices',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 自动搜索模拟器
   * 自动搜索系统中安装的模拟器
   * @returns EmulatorSearchOut Successful Response
   * @throws ApiError
   */
  public static searchEmulatorsApiSettingEmulatorSearchPost(): CancelablePromise<EmulatorSearchOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/emulator/search',
    })
  }

  /**
   * 启动指定模拟器
   * 根据UUID和索引启动指定模拟器
   * @param requestBody
   * @returns EmulatorStartOut Successful Response
   * @throws ApiError
   */
  public static startEmulatorApiSettingEmulatorStartPost(
    requestBody: EmulatorStartIn
  ): CancelablePromise<EmulatorStartOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/emulator/start',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 关闭指定模拟器
   * 根据UUID和索引关闭指定模拟器
   * @param requestBody
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static stopEmulatorApiSettingEmulatorStopPost(
    requestBody: EmulatorStopIn
  ): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/emulator/stop',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 获取模拟器状态
   * 获取指定UUID的模拟器状态，或获取所有模拟器状态（不传UUID时）
   * @param requestBody
   * @returns EmulatorStatusOut Successful Response
   * @throws ApiError
   */
  public static getEmulatorStatusApiApiSettingEmulatorStatusPost(
    requestBody: EmulatorStatusIn
  ): CancelablePromise<EmulatorStatusOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/setting/emulator/status',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 检查更新
   * @param requestBody
   * @returns UpdateCheckOut Successful Response
   * @throws ApiError
   */
  public static checkUpdateApiUpdateCheckPost(
    requestBody: UpdateCheckIn
  ): CancelablePromise<UpdateCheckOut> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/update/check',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    })
  }

  /**
   * 下载更新
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static downloadUpdateApiUpdateDownloadPost(): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/update/download',
    })
  }

  /**
   * 安装更新
   * @returns OutBase Successful Response
   * @throws ApiError
   */
  public static installUpdateApiUpdateInstallPost(): CancelablePromise<OutBase> {
    return __request(OpenAPI, {
      method: 'POST',
      url: '/api/update/install',
    })
  }
}
