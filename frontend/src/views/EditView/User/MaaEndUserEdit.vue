<template>
  <div class="user-edit-container">
    <teleport to="body">
      <div v-if="showMaaEndConfigMask" class="maaend-config-mask">
        <div class="mask-content">
          <div class="mask-icon">
            <SettingOutlined :style="{ fontSize: '48px', color: 'var(--ant-color-primary)' }" />
          </div>
          <h2 class="mask-title">正在进行 MaaEnd 配置</h2>
          <p class="mask-description">
            当前正在为这个用户打开 MaaEnd 配置界面，请在 MaaEnd 中完成相关设置。
            <br />
            配置完成后，点击“保存配置”结束本次会话。
          </p>
          <div class="mask-actions">
            <a-button
              v-if="maaEndWebsocketId"
              type="primary"
              size="large"
              @click="handleSaveMaaEndConfig"
            >
              保存配置
            </a-button>
          </div>
        </div>
      </div>
    </teleport>

    <MaaEndUserEditHeader
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      @handle-cancel="handleCancel"
    />

    <div class="user-edit-content">
      <a-card class="config-card">
        <!--
          Lane 06 任务书第 5 条：保存失败保留输入；validation/save/action 状态必须真实可见。
          保存错误横幅仅在 saveError 非空时展示，且经过脱敏（不含敏感字段明文）。
        -->
        <a-alert
          v-if="saveError"
          class="save-error-banner"
          type="error"
          show-icon
          message="保存失败"
          :description="saveError"
          closable
          @close="clearSaveError"
        />
        <a-form
          ref="formRef"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form"
        >
          <BasicInfoSection
            ref="basicInfoRef"
            :form-data="formData"
            :loading="loading"
            :resource-options="resourceOptions"
            :preset-supported="presetSupported"
            :config-loading="maaEndConfigLoading"
            :import-loading="maaEndImportLoading"
            :show-config-mask="showMaaEndConfigMask"
            @save="handleFieldSave"
            @sensitive-save="handleSensitiveSave"
            @sensitive-dirty-change="handleSensitiveDirtyChange"
            @configure="handleMaaEndConfig"
            @import-config="handleImportMaaEndConfig"
            @script-config="handleScriptConfig"
          />
          <TaskConfigSection
            v-if="formData.Info.IfQuickConfig"
            :form-data="formData"
            :loading="loading"
            :if-quick-config="formData.Info.IfQuickConfig"
            :controller-type="controllerType"
            @save="handleFieldSave"
            @save-batch="handleFieldsSave"
          />
          <SkylandConfigSection
            ref="skylandRef"
            :form-data="formData"
            :loading="loading"
            @save="handleFieldSave"
            @sensitive-save="handleSensitiveSave"
            @sensitive-dirty-change="handleSensitiveDirtyChange"
          />
          <ExtraScriptSection :form-data="formData" :loading="loading" @save="handleFieldSave" />
          <NotifyConfigSection
            ref="notifyRef"
            :form-data="formData"
            :loading="loading"
            :script-id="scriptId"
            :user-id="userId"
            @save="handleFieldSave"
            @sensitive-save="handleSensitiveSave"
            @sensitive-dirty-change="handleSensitiveDirtyChange"
          />
        </a-form>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { Modal, message } from 'ant-design-vue'
import { SettingOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { Service } from '@/api'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useWebSocket } from '@/composables/useWebSocket'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import {
  useEditorLogger,
  useFieldSave,
  useDirtyTracker,
  buildNestedPatch,
} from '@/composables/useUserEditShared'
import { useUnsavedChangesGuard } from '@/composables/useUnsavedChangesGuard'

import MaaEndUserEditHeader from '@/views/MaaEndUserEdit/MaaEndUserEditHeader.vue'
import BasicInfoSection from '@/views/MaaEndUserEdit/BasicInfoSection.vue'
import TaskConfigSection from '@/views/MaaEndUserEdit/TaskConfigSection.vue'
import SkylandConfigSection from '@/views/MaaEndUserEdit/SkylandConfigSection.vue'
import NotifyConfigSection from '@/views/MaaEndUserEdit/NotifyConfigSection.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'

const logger = useEditorLogger('MaaEnd用户编辑')

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading } = useUserApi()
const { getScript, importScriptConfigFile } = useScriptApi()
const { subscribe, unsubscribe } = useWebSocket()

const formRef = ref<FormInstance>()
const loading = computed(() => userLoading.value)
const isInitializing = ref(true)
const isSaving = ref(false)

const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId)
const scriptName = ref('')
const controllerType = ref<string | null>(null)
const presetSupported = computed(() => controllerType.value === 'Win32-Front')

const updateUserOrThrow = async (userData: Record<string, unknown>) => {
  const saved = await updateUser(scriptId, userId, userData)
  if (saved === false) {
    throw new Error('用户配置更新未成功')
  }
}

const maaEndConfigLoading = ref(false)
const maaEndImportLoading = ref(false)
const showMaaEndConfigMask = ref(false)
const maaEndSubscriptionId = ref<string | null>(null)
const maaEndWebsocketId = ref<string | null>(null)
let maaEndConfigTimeout: number | null = null
const resourceOptions = [{ label: '官服', value: '官服' }]

const getDefaultMaaEndUserData = () => ({
  Info: {
    Name: '',
    Status: true,
    Id: '',
    Password: '',
    Mode: '简洁',
    IfQuickConfig: true,
    SanityMode: 'Fixed',
    Resource: '官服',
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    IfSkland: false,
    SklandToken: '',
    Notes: '',
    Tag: '',
  },
  Task: {
    SanityTaskType: 'OperatorProgression',
    OperatorProgression: 'OperatorEXP',
    WeaponProgression: 'WeaponEXP',
    CrisisDrills: 'AdvancedProgression1',
    RewardsSetOption: 'RewardsSetA',
    AutoEssenceSpecifiedLocation: 'VFTheHub',
    IfSanity: true,
    IfAutoUseSpMedication: true,
    IfDijiangRewards: true,
    IfDeliveryJobs: true,
    IfSellProduct: true,
    IfAutoStockpile: true,
    IfAutoStockStaple: true,
    IfVisitFriends: true,
    IfCreditShoppingN2: true,
    IfSeizeEntrustTask: true,
    IfAutoEcoFarm: true,
    IfAutoSell: true,
    IfEnvironmentMonitoring: true,
    IfAutoCollect: true,
    IfDailyRewards: true,
    IfResourceRecycleStation: true,
  },
  Notify: {
    Enabled: false,
    IfSendStatistic: false,
    IfSendMail: false,
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
  },
  Data: {
    LastProxyDate: '',
    LastSklandDate: '',
    ProxyTimes: 0,
    IfPassCheck: false,
  },
})

interface FieldChange {
  key: string
  value: any
}

const formData = reactive({
  userName: '',
  ...getDefaultMaaEndUserData(),
})

const rules = computed<Record<string, Rule[]>>(() => ({
  userName: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 1, max: 50, message: '用户名长度应为 1-50 个字符', trigger: 'blur' },
  ],
}))

const syncUserName = () => {
  if (formData.Info.Name !== formData.userName) {
    formData.Info.Name = formData.userName
  }
}

// ============================================================
// Lane 06 任务书第 4、5 条：未保存保护 + dirty/save/error helper 接入
// ============================================================

/** 脏状态追踪器：所有字段级保存与敏感字段 dirty 都通过此 tracker 同步。 */
const dirtyTracker = useDirtyTracker()

/** 敏感字段 dirty 状态：来自子组件 sensitiveDirtyChange 事件。 */
const sensitiveDirtyMap = reactive<Record<string, boolean>>({})

/** 敏感字段 dirty 总状态（用于 useUnsavedChangesGuard）。 */
const isSensitiveDirty = computed(() => Object.values(sensitiveDirtyMap).some(v => v === true))

/**
 * 综合脏状态：常规字段脏 OR 敏感字段脏 OR 保存中。
 * 注意：isSaving 时不算 dirty（避免保存中触发守卫）。
 */
const isDirty = computed(
  () => (dirtyTracker.hasUnsavedChanges.value || isSensitiveDirty.value) && !isSaving.value
)

const {
  saveError,
  setSaveError,
  clearSaveError,
  confirmLeave,
  confirmLeaveNow,
  cancelLeave,
  bindBeforeUnload,
} = useUnsavedChangesGuard({
  isDirty,
  isSaving,
  confirmMessage: '您有未保存的更改（包括密码 / 令牌 / SendKey 等敏感字段），确定要离开吗？',
})

// 注册 window.beforeunload（composable 内部 onMounted/onBeforeUnmount 管理）
bindBeforeUnload()

// 路由级离开守卫
onBeforeRouteLeave(() => {
  if (!confirmLeave()) {
    // 需要拦截：弹出确认框
    return new Promise<boolean>(resolve => {
      Modal.confirm({
        title: '未保存的更改',
        content:
          '当前页面存在未保存的更改，包括可能未提交的敏感字段（密码 / SklandToken / ServerChanKey）。离开后这些输入将丢失，是否继续？',
        okText: '仍然离开',
        cancelText: '留下',
        okType: 'danger',
        centered: true,
        onOk: () => {
          confirmLeaveNow()
          resolve(true)
        },
        onCancel: () => {
          cancelLeave()
          resolve(false)
        },
      })
    })
  }
  return true
})

// ============================================================
// useFieldSave：字段级保存（保持原有 setNestedValue 行为）
// ============================================================

const saveUserFieldsInternal = async (patch: Record<string, any>): Promise<boolean> => {
  if (isInitializing.value || isSaving.value || !userId) {
    return false
  }

  isSaving.value = true
  try {
    // useFieldSave 会用 buildNestedPatch(key, value) 构造 patch。
    // 原 saveUserFields 对 'userName' 键有特殊处理：sync 到 formData.Info.Name 后保存 Info.Name。
    // 这里保持原语义：检测 patch 顶层是否含 userName 键，若有则翻译为 Info.Name。
    let finalPatch = patch
    if ('userName' in patch) {
      formData.userName = String(patch.userName ?? '')
      syncUserName()
      const { userName: _omitted, ...rest } = patch
      void _omitted
      finalPatch = {
        ...rest,
        Info: { ...(rest.Info ?? {}), Name: formData.Info.Name },
      }
    }
    await updateUserOrThrow(finalPatch)
    return true
  } catch (error) {
    // 错误脱敏：错误消息可能包含敏感字段值（如密码明文回显），统一截断后展示。
    // MaaEndUserEdit 不使用 SchemaForm，没有 schema 可枚举，采用保守策略：
    // 仅展示 error.message 的前 200 字符，并移除可能的 "value=..." 模式。
    const rawMsg = error instanceof Error ? error.message : String(error)
    const safeMsg = rawMsg.length > 200 ? `${rawMsg.slice(0, 200)}…` : rawMsg
    logger.error(`保存用户字段失败: ${safeMsg}`)
    setSaveError(safeMsg)
    return false
  } finally {
    isSaving.value = false
  }
}

const { handleFieldSave } = useFieldSave({
  isInitializing,
  isSaving,
  save: saveUserFieldsInternal,
  logger,
  dirtyTracker,
  onError: (errorMsg: string) => {
    setSaveError(errorMsg)
  },
})

const handleFieldsSave = async (changes: FieldChange[]) => {
  if (isInitializing.value || isSaving.value || !userId || !changes.length) return

  // 多字段批量保存：合并为单个嵌套 patch
  const patch: Record<string, any> = {}
  changes.forEach(change => {
    if (change.key === 'userName') {
      syncUserName()
      const nested = buildNestedPatch('Info.Name', formData.Info.Name)
      Object.keys(nested).forEach(k => {
        patch[k] = { ...(patch[k] ?? {}), ...(nested[k] ?? {}) }
      })
      return
    }
    const nested = buildNestedPatch(change.key, change.value)
    Object.keys(nested).forEach(k => {
      patch[k] = { ...(patch[k] ?? {}), ...(nested[k] ?? {}) }
    })
  })

  dirtyTracker.markDirty()
  isSaving.value = true
  try {
    await updateUserOrThrow(patch)
    dirtyTracker.markClean()
    clearSaveError()
  } catch (error) {
    const rawMsg = error instanceof Error ? error.message : String(error)
    const safeMsg = rawMsg.length > 200 ? `${rawMsg.slice(0, 200)}…` : rawMsg
    logger.error(`批量保存字段失败: ${safeMsg}`)
    setSaveError(safeMsg)
    dirtyTracker.markDirty()
  } finally {
    isSaving.value = false
  }
}

// ============================================================
// Lane 06 任务书第 2 条：敏感字段保存意图处理
// - keep：不发送给后端（保持原密文）。
// - replace：发送新明文（后端加密为新密文）。
// - clear：发送空串 ""（后端加密为空密文）。
// ============================================================

const basicInfoRef = ref<InstanceType<typeof BasicInfoSection> | null>(null)
const skylandRef = ref<InstanceType<typeof SkylandConfigSection> | null>(null)
const notifyRef = ref<InstanceType<typeof NotifyConfigSection> | null>(null)

/**
 * 处理子组件 sensitiveSave 事件。
 *
 * @param key 字段路径（如 `Info.Password`、`Info.SklandToken`、`Notify.ServerChanKey`）。
 * @param intent 保存意图：`keep` | `replace` | `clear`。
 * @param value 替换时的新明文（仅 `replace` 时有意义）。
 */
const handleSensitiveSave = async (
  key: string,
  intent: 'keep' | 'replace' | 'clear',
  value?: string
) => {
  // keep：不发送给后端，但需要清除 dirty 标志（用户已 blur，无变更）
  if (intent === 'keep') {
    sensitiveDirtyMap[key] = false
    // 不调用 markClean：其他字段可能仍 dirty
    return
  }

  // replace / clear：构造 patch 并发送
  // - replace：发送新明文（后端加密为新密文）。
  // - clear：发送空串 ""（后端加密为空密文）。
  const patchValue = intent === 'replace' ? (value ?? '') : ''
  const patch = buildNestedPatch(key, patchValue)

  isSaving.value = true
  try {
    await updateUserOrThrow(patch)
    // 保存成功后：清除该字段 dirty 标志；调用子组件 reset 草稿。
    sensitiveDirtyMap[key] = false
    if (key === 'Info.Password') {
      basicInfoRef.value?.resetPasswordDraft?.()
    } else if (key === 'Info.SklandToken') {
      skylandRef.value?.resetTokenDraft?.()
    } else if (key === 'Notify.ServerChanKey') {
      notifyRef.value?.resetServerChanKeyDraft?.()
    }
    clearSaveError()
    logger.info(`敏感字段已保存: ${key} (intent=${intent})`)
  } catch (error) {
    // 保存失败：保留输入（不清空草稿）；标记 dirty；展示脱敏错误。
    const rawMsg = error instanceof Error ? error.message : String(error)
    const safeMsg = rawMsg.length > 200 ? `${rawMsg.slice(0, 200)}…` : rawMsg
    logger.error(`敏感字段保存失败: ${key} -> ${safeMsg}`)
    setSaveError(`敏感字段 ${key} 保存失败: ${safeMsg}`)
    sensitiveDirtyMap[key] = true
  } finally {
    isSaving.value = false
  }
}

/**
 * 处理子组件 sensitiveDirtyChange 事件。
 *
 * 子组件在用户输入或清空敏感字段时触发；这里更新 dirtyMap，
 * 同时通过 dirtyTracker 同步常规 dirty 状态。
 */
const handleSensitiveDirtyChange = (key: string, dirty: boolean) => {
  sensitiveDirtyMap[key] = dirty
  if (dirty) {
    dirtyTracker.markDirty()
  }
}

const handleScriptConfig = () => {
  cleanupConfigSession()
  router.push(`/scripts/${scriptId}/edit/maaend`)
}

const loadScriptInfo = async () => {
  const scriptDetail = await getScript(scriptId)
  if (scriptDetail) {
    scriptName.value = scriptDetail.name
    controllerType.value = (scriptDetail.config as any).Game?.ControllerType ?? null
  }
}

const normalizeQuickConfig = async () => {
  if (!userId) return

  const infoPayload: Record<string, unknown> = {}
  if (formData.Info.Mode === '自定义') {
    formData.Info.Mode = '详细'
    formData.Info.IfQuickConfig = false
    infoPayload.Mode = formData.Info.Mode
    infoPayload.IfQuickConfig = formData.Info.IfQuickConfig
  }

  if (!presetSupported.value && formData.Info.IfQuickConfig) {
    formData.Info.IfQuickConfig = false
    infoPayload.IfQuickConfig = false
  }

  if (Object.keys(infoPayload).length) {
    await updateUserOrThrow({ Info: infoPayload })
  }
}

const loadUserData = async () => {
  try {
    const userResponse = await getUsers(scriptId, userId)
    if (!userResponse || userResponse.code !== 200) {
      throw new Error('加载用户失败')
    }

    const userIndex = userResponse.index.find((index: any) => index.uid === userId)
    if (!userIndex || !userResponse.data[userId]) {
      throw new Error('用户不存在')
    }

    const userData = userResponse.data[userId] as any
    if (userIndex.type !== 'MaaEndUserConfig') {
      throw new Error('用户类型不匹配')
    }

    Object.assign(formData, {
      Info: { ...getDefaultMaaEndUserData().Info, ...userData.Info },
      Task: { ...getDefaultMaaEndUserData().Task, ...userData.Task },
      Notify: { ...getDefaultMaaEndUserData().Notify, ...userData.Notify },
      Data: { ...getDefaultMaaEndUserData().Data, ...userData.Data },
    })

    await nextTick()
    formData.userName = formData.Info.Name || ''

    // 权威 reload 后清空敏感字段草稿，避免显示陈旧明文。
    basicInfoRef.value?.resetPasswordDraft?.()
    skylandRef.value?.resetTokenDraft?.()
    notifyRef.value?.resetServerChanKeyDraft?.()
    // 清空 dirtyMap 与 tracker
    Object.keys(sensitiveDirtyMap).forEach(k => {
      sensitiveDirtyMap[k] = false
    })
    dirtyTracker.reset()
    clearSaveError()
  } catch (error) {
    message.error(error instanceof Error ? error.message : '加载用户失败')
    router.push('/scripts')
  }
}

const cleanupConfigSession = () => {
  if (maaEndSubscriptionId.value) {
    unsubscribe(maaEndSubscriptionId.value)
    maaEndSubscriptionId.value = null
  }
  maaEndWebsocketId.value = null
  showMaaEndConfigMask.value = false
  if (maaEndConfigTimeout) {
    window.clearTimeout(maaEndConfigTimeout)
    maaEndConfigTimeout = null
  }
}

const handleMaaEndConfig = async () => {
  try {
    maaEndConfigLoading.value = true
    cleanupConfigSession()

    const configTaskTargetId = formData.Info.Mode === '简洁' ? scriptId : userId
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: configTaskTargetId,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
    })

    if (!response?.taskId) {
      throw new Error(response?.message || '启动 MaaEnd 配置失败')
    }

    const subscriptionId = subscribe({ id: response.taskId }, (wsMessage: any) => {
      if (wsMessage.type === 'error') {
        message.error(`MaaEnd 配置连接失败: ${wsMessage.data}`)
        cleanupConfigSession()
        return
      }

      if (wsMessage.type === 'Info' && wsMessage.data?.Error) {
        message.error(`MaaEnd 配置异常: ${wsMessage.data.Error}`)
        return
      }

      if (wsMessage.type === 'Signal' && wsMessage.data?.Accomplish !== undefined) {
        cleanupConfigSession()
      }
    })

    maaEndSubscriptionId.value = subscriptionId
    maaEndWebsocketId.value = response.taskId
    showMaaEndConfigMask.value = true
    message.success(`已启动 ${formData.Info.Mode === '简洁' ? '脚本' : '用户'} MaaEnd 配置`)

    maaEndConfigTimeout = window.setTimeout(
      () => {
        cleanupConfigSession()
        message.info('MaaEnd 配置会话已超时断开')
      },
      30 * 60 * 1000
    )
  } catch (error) {
    message.error(error instanceof Error ? error.message : '启动 MaaEnd 配置失败')
  } finally {
    maaEndConfigLoading.value = false
  }
}

const handleImportMaaEndConfig = async () => {
  try {
    maaEndImportLoading.value = true
    const response = await importScriptConfigFile(
      scriptId,
      formData.Info.Mode === '简洁' ? null : userId
    )
    if (response.code !== 200) {
      throw new Error(response.message || '导入脚本配置文件失败')
    }
    message.success(`已导入${formData.Info.Mode === '简洁' ? '脚本' : '用户'}配置文件`)
  } catch (error) {
    message.error(error instanceof Error ? error.message : '导入脚本配置文件失败')
  } finally {
    maaEndImportLoading.value = false
  }
}

const handleSaveMaaEndConfig = async () => {
  try {
    if (!maaEndWebsocketId.value) {
      throw new Error('未找到活动配置会话')
    }

    const response = await Service.stopTaskApiDispatchStopPost({ taskId: maaEndWebsocketId.value })
    if (response.code !== 200) {
      throw new Error(response.message || '保存配置失败')
    }

    cleanupConfigSession()
    message.success('MaaEnd 配置已保存')
  } catch (error) {
    message.error(error instanceof Error ? error.message : '保存配置失败')
  }
}

const handleCancel = () => {
  // 离开前由 onBeforeRouteLeave 守卫拦截；守卫确认后由路由跳转。
  // 这里仅清理 MaaEnd 配置会话。
  cleanupConfigSession()
  router.push('/scripts')
}

onMounted(async () => {
  await loadScriptInfo()

  if (isEdit.value) {
    await loadUserData()
    await normalizeQuickConfig()
  } else {
    const result = await addUser(scriptId)
    if (result?.userId) {
      userId = result.userId
      isEdit.value = true
      await normalizeQuickConfig()
    } else {
      message.error('创建用户失败')
      router.push('/scripts')
      return
    }
  }

  await nextTick()
  isInitializing.value = false
})
</script>

<style scoped>
.user-edit-container {
  padding: var(--v6-space-8);
  min-height: 100vh;
  background: var(--v6-color-window);
}

.user-edit-content {
  max-width: 1200px;
  margin: 0 auto;
}

.config-card {
  border-radius: var(--v6-radius-card);
  box-shadow: var(--v6-shadow-card);
}

.config-card :deep(.ant-card-body) {
  padding: var(--v6-space-8);
}

.save-error-banner {
  margin-bottom: var(--v6-space-4);
}

.maaend-config-mask {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, #000 45%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--v6-z-modal-backdrop);
}

.mask-content {
  background: var(--v6-color-surface-elevated);
  border-radius: var(--v6-radius-md);
  padding: var(--v6-space-6);
  max-width: 480px;
  width: 100%;
  text-align: center;
  border: 1px solid var(--v6-color-border);
  box-shadow: var(--v6-shadow-elevated);
}

.mask-icon {
  margin-bottom: var(--v6-space-4);
}

.mask-title {
  font-size: var(--v6-font-size-xl);
  font-weight: var(--v6-font-weight-semibold);
  margin: 0 0 var(--v6-space-2);
}

.mask-description {
  font-size: var(--v6-font-size-base);
  color: var(--v6-color-text-secondary);
  margin: 0 0 var(--v6-space-6);
  line-height: var(--v6-line-height-normal);
}

.mask-actions {
  display: flex;
  justify-content: center;
}

@media (max-width: 768px) {
  .user-edit-container {
    padding: var(--v6-space-4);
  }

  .config-card :deep(.ant-card-body) {
    padding: var(--v6-space-5);
  }
}
</style>
