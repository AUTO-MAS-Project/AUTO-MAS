import { getApiErrorMessage } from '@/utils/apiError'
import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  type ScriptUpdateIn,
  type ScriptGetOut,
  type HSRStageOptionsData,
  type MaaEndOptionsOut,
  type MaaFWInterfacePreviewOut,
  type MaaFWAgentEnvPrepareOut,
  type ScriptCreateIn,
  type ScriptReorderIn,
  HsrService,
  MaaFwService,
  Service,
} from '@/api'
import type { ScriptDetail, ScriptType } from '@/types/script'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { getTaskRuntimeStates } from '@/composables/useTaskRuntimeState'
import { isScriptConfigLocked } from '@/utils/scriptConfigLock'
import { maafwScriptTypeByConfigType } from '@/composables/useMaaFWFlavor'

const logger = window.electronAPI.getLogger('脚本API')

// 首页卫星与活动区共用在途的列表请求，完成后释放，后续读取仍取最新数据。
interface ScriptListRequest {
  promise: Promise<ScriptGetOut>
  errorNotified: boolean
}
let scriptListRequest: ScriptListRequest | null = null

type HSRStageEngine = 'M7A' | 'SRA'
const SCRIPT_TYPE_BY_CONFIG_TYPE: Record<string, ScriptType> = {
  MaaConfig: 'MAA',
  SrcConfig: 'SRC',
  OkwwConfig: 'Okww',
  OkNteConfig: 'OkNte',
  MaaEndConfig: 'MaaEnd',
  HSRConfig: 'HSR',
  BetterGIConfig: 'BetterGI',
  ZzzOdConfig: 'ZzzOd',
  BAAHConfig: 'BAAH',
  WhimboxConfig: 'Whimbox',
  // MaaFW 与各特调（M9A / MSS ……）的配置类名由特调注册表提供
  ...maafwScriptTypeByConfigType(),
}

const resolveScriptType = (configType: string): ScriptType => {
  return SCRIPT_TYPE_BY_CONFIG_TYPE[configType] ?? 'General'
}

export function useScriptApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 添加脚本（支持从已有脚本复制创建）
  const addScript = async (type: ScriptType, scriptId?: string) => {
    loading.value = true
    error.value = null

    try {
      const requestData: ScriptCreateIn = {
        type: type as ScriptCreateIn['type'],
        scriptId: scriptId || null,
      }

      const response = await Service.addScriptApiScriptsAddPost(requestData)

      if (response.code !== 200) {
        const errorMsg = response.message || t('apiErrors.scriptAddFailed')
        throw new Error(errorMsg)
      }

      scriptListRequest = null
      // 播放添加脚本成功音频
      const { playSound } = useAudioPlayer()
      await playSound('add_script_instance')

      return {
        scriptId: response.scriptId,
        message: response.message || t('apiErrors.scriptAdded'),
        data: response.data,
      }
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('apiErrors.scriptAddFailed'))
      error.value = errorMsg
      message.error(errorMsg)
      return null
    } finally {
      loading.value = false
    }
  }

  // 获取脚本列表（可选择是否管理 loading 状态，避免嵌套调用时提前结束 loading）
  const getScripts = async (
    manageLoading: boolean = true,
    options: { showError?: boolean } = {}
  ): Promise<ScriptDetail[]> => {
    if (manageLoading) {
      loading.value = true
      error.value = null
    } else {
      // 仅清理错误，不改变外部 loading
      error.value = null
    }

    let sharedRequest: ScriptListRequest | null = null
    try {
      if (!scriptListRequest) {
        const request: ScriptListRequest = {
          promise: Service.getScriptApiScriptsGetPost({}),
          errorNotified: false,
        }
        request.promise = request.promise.finally(() => {
          if (scriptListRequest === request) scriptListRequest = null
        })
        scriptListRequest = request
      }
      sharedRequest = scriptListRequest
      const response = await sharedRequest.promise

      if (response.code !== 200) {
        const errorMsg = response.message || t('apiErrors.scriptListFailed')
        throw new Error(errorMsg)
      }

      // 将API响应转换为ScriptDetail数组
      return response.index.map(indexItem => ({
        uid: indexItem.uid,
        type: resolveScriptType(indexItem.type),
        activityGame: indexItem.activityGame,
        name: response.data[indexItem.uid]?.Info?.Name || `${indexItem.type}脚本`,
        config: response.data[indexItem.uid],
      }))
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('apiErrors.scriptListFailed'))
      error.value = errorMsg
      // 共享同一在途请求的多个消费者只弹一次；显式重试仍有自己的提示。
      if ((options.showError ?? true) && !sharedRequest?.errorNotified) {
        if (sharedRequest) sharedRequest.errorNotified = true
        message.error(errorMsg)
      }
      return []
    } finally {
      if (manageLoading) {
        loading.value = false
      }
    }
  }

  // 获取单个脚本
  const getScript = async (scriptId: string): Promise<ScriptDetail | null> => {
    loading.value = true
    error.value = null

    try {
      const response = await Service.getScriptApiScriptsGetPost({ scriptId })

      if (response.code !== 200) {
        const errorMsg = response.message || t('apiErrors.scriptLoadFailed')
        throw new Error(errorMsg)
      }

      // 检查是否有数据返回
      if (response.index.length === 0) {
        throw new Error(t('edit.scriptDoesNotExist'))
      }

      const item = response.index[0]
      const config = response.data[item.uid]
      const scriptType = resolveScriptType(item.type)

      return {
        uid: item.uid,
        type: scriptType,
        activityGame: item.activityGame,
        name: config?.Info?.Name || `${item.type}脚本`,
        config,
      }
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('apiErrors.scriptLoadFailed'))
      error.value = errorMsg
      message.error(errorMsg)
      return null
    } finally {
      loading.value = false
    }
  }

  const getHsrStageOptions = async (
    scriptId: string,
    engine: HSRStageEngine
  ): Promise<HSRStageOptionsData | null> => {
    try {
      const payload = await HsrService.getHsrStageOptionsApiApiScriptsHsrStageOptionsGet(
        scriptId,
        engine
      )
      if (payload?.code !== 200) {
        throw new Error(payload?.message || t('apiErrors.invalidResponse'))
      }
      return payload.data ?? null
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('apiErrors.hsrStagesFailed'))
      error.value = errorMsg
      logger.error(`获取 HSR 体力副本选项失败: ${errorMsg}`)
      return null
    }
  }

  // 预览 MaaFW 项目 interface：返回后端原始响应，让编辑页把 code=400 的 message 原样呈现
  const previewMaaFWInterface = async (
    path: string,
    scriptId?: string
  ): Promise<MaaFWInterfacePreviewOut | null> => {
    error.value = null
    try {
      // 带 scriptId 时后端按脚本解析有效根（内嵌副本优先），path 只是兜底。
      return await MaaFwService.previewMaafwInterfaceApiScriptsMaafwPreviewPost({ path, scriptId })
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('apiErrors.maafwPreviewFailed'))
      error.value = errorMsg
      logger.error(`预览 MaaFW interface 失败: ${errorMsg}`)
      return null
    }
  }

  const prepareMaaFWAgentEnv = async (
    path: string,
    scriptId?: string,
    force = false
  ): Promise<MaaFWAgentEnvPrepareOut | null> => {
    error.value = null
    try {
      return await MaaFwService.prepareMaafwAgentEnvApiScriptsMaafwAgentEnvPreparePost({
        path,
        scriptId,
        force,
      })
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('apiErrors.maafwEnvFailed'))
      error.value = errorMsg
      logger.error(`准备 MaaFW 运行环境失败: ${errorMsg}`)
      return null
    }
  }

  const getMaaEndOptions = async (scriptId: string): Promise<MaaEndOptionsOut | null> => {
    try {
      const response = await Service.getMaaendOptionsApiScriptsMaaendOptionsPost({ scriptId })
      if (response?.code !== 200)
        throw new Error(response?.message || t('apiErrors.invalidResponse'))
      return response
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('apiErrors.maaEndOptionsFailed'))
      error.value = errorMsg
      logger.error(`获取 MaaEnd 动态选项失败: ${errorMsg}`)
      message.error(errorMsg)
      return null
    }
  }

  // 删除脚本
  const deleteScript = async (scriptId: string): Promise<boolean> => {
    loading.value = true
    error.value = null

    try {
      const response = await Service.deleteScriptApiScriptsDeletePost({ scriptId })

      if (response.code !== 200) {
        const errorMsg = response.message || t('apiErrors.scriptDeleteFailed')
        throw new Error(errorMsg)
      }

      scriptListRequest = null
      // 播放删除脚本成功音频
      const { playSound } = useAudioPlayer()
      await playSound('delete_script_instance')

      return true
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('apiErrors.scriptDeleteFailed'))
      error.value = errorMsg
      message.error(errorMsg)
      return false
    } finally {
      loading.value = false
    }
  }

  // 更新脚本
  const updateScript = async (
    scriptId: string,
    data: Record<string, unknown>
  ): Promise<boolean> => {
    if (isScriptConfigLocked(getTaskRuntimeStates(), scriptId)) {
      const errorMsg = t('edit.configLocked')
      error.value = errorMsg
      message.warning(errorMsg)
      return false
    }

    loading.value = true
    error.value = null

    try {
      // 脚本保存只提交字段，嵌套用户和通知配置由各自接口维护。
      const dataToSend: Record<string, unknown> = { ...data }
      delete dataToSend.UserData
      delete dataToSend.Notify_CustomWebhooks
      delete dataToSend.ui

      const response = await Service.updateScriptApiScriptsUpdatePost({
        scriptId,
        data: dataToSend as ScriptUpdateIn['data'],
      })

      if (response.code !== 200) {
        const errorMsg = response.message || t('apiErrors.scriptSaveFailed')
        throw new Error(errorMsg)
      }

      scriptListRequest = null
      return true
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('apiErrors.scriptSaveFailed'))
      error.value = errorMsg
      message.error(errorMsg)
      return false
    } finally {
      loading.value = false
    }
  }

  // 重新排序脚本
  const reorderScript = async (scriptIds: string[]): Promise<boolean> => {
    // loading.value = true // 排序通常不需要全屏loading，或者可以使用局部loading
    error.value = null

    try {
      const requestData: ScriptReorderIn = {
        indexList: scriptIds,
      }

      const response = await Service.reorderScriptApiScriptsOrderPost(requestData)

      if (response.code !== 200) {
        const errorMsg = response.message || t('apiErrors.scriptOrderFailed')
        throw new Error(errorMsg)
      }

      scriptListRequest = null
      return true
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('apiErrors.scriptOrderFailed'))
      error.value = errorMsg
      message.error(errorMsg)
      return false
    } finally {
      // loading.value = false
    }
  }

  const importScriptConfigFile = (scriptId: string, userId: string | null) =>
    Service.importScriptConfigFileApiScriptsConfigImportPost({ scriptId, userId }).then(
      response => {
        if (response.code === 200) scriptListRequest = null
        return response
      }
    )

  return {
    loading,
    error,
    addScript,
    getScripts,
    getScript,
    getHsrStageOptions,
    getMaaEndOptions,
    previewMaaFWInterface,
    prepareMaaFWAgentEnv,
    deleteScript,
    updateScript,
    reorderScript,
    importScriptConfigFile,
  }
}
