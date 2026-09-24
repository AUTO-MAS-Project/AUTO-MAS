<template>
  <!-- 配置会话遮罩层：MAA / SRC / MaaEnd / ok-ww 共用一份，按会话种类取文案 -->
  <div v-if="configMaskView" class="maa-config-mask">
    <div class="mask-content">
      <div class="mask-icon">
        <SettingOutlined :style="{ fontSize: '48px', color: configMaskView.iconColor }" />
      </div>
      <h2 class="mask-title">{{ configMaskView.title }}</h2>
      <p class="mask-description">
        {{ configMaskView.description }}
        <br />
        {{ configMaskView.tip }}
      </p>
      <div class="mask-actions">
        <a-button type="primary" size="large" @click="handleSaveConfigMask">
          {{ configMaskView.button }}
        </a-button>
      </div>
    </div>
  </div>

  <!-- 主要内容 -->
  <div class="scripts-header">
    <div class="header-left">
      <h1 class="page-title">{{ t('scripts.title') }}</h1>
      <DocLink :url="MAS_DOC_URLS.scripts" />
      <a-input
        v-model:value="scriptSearchKeyword"
        allow-clear
        class="script-search"
        :placeholder="t('scripts.searchPlaceholder')"
        :aria-label="t('scripts.searchAria')"
      >
        <template #prefix><SearchOutlined /></template>
      </a-input>
    </div>
    <div class="header-actions">
      <a-space size="middle">
        <a-tooltip :title="t('scripts.collapseAllTip')">
          <a-button
            size="large"
            :disabled="scripts.length === 0 || isSearching"
            @click="handleCollapseAll"
          >
            <template #icon><UpOutlined /></template>
            {{ t('scripts.collapseAll') }}
          </a-button>
        </a-tooltip>
        <a-tooltip :title="t('scripts.expandAllTip')">
          <a-button
            size="large"
            :disabled="scripts.length === 0 || isSearching"
            @click="handleExpandAll"
          >
            <template #icon><DownOutlined /></template>
            {{ t('scripts.expandAll') }}
          </a-button>
        </a-tooltip>
        <a-button type="primary" size="large" class="link" @click="handleAddScript">
          <template #icon>
            <PlusOutlined />
          </template>
          {{ t('scripts.create.title') }}
        </a-button>
      </a-space>
    </div>
  </div>

  <!-- 空状态 -->
  <!-- 增加 loadedOnce 条件，避免初始渲染时闪烁 -->
  <div v-if="!addLoading && loadedOnce && scripts.length === 0" class="empty-state">
    <div class="empty-content">
      <div class="empty-image-container">
        <img src="@/assets/NoData.png" :alt="t('scripts.empty.alt')" class="empty-image" />
      </div>
      <div class="empty-text-content">
        <h3 class="empty-title">{{ t('scripts.empty.title') }}</h3>
        <p class="empty-description">{{ t('scripts.empty.desc') }}</p>
      </div>
    </div>
  </div>

  <div v-else-if="!addLoading && loadedOnce && filteredScripts.length === 0" class="empty-state">
    <a-empty :description="t('scripts.empty.noMatch')">
      <a-button @click="scriptSearchKeyword = ''">{{ t('scripts.clearSearch') }}</a-button>
    </a-empty>
  </div>

  <ScriptTable
    v-else
    ref="scriptTableRef"
    :scripts="filteredScripts"
    :searching="isSearching"
    :active-connections="activeConnections"
    :copying-script-id="copyingScriptId"
    @edit="handleEditScript"
    @copy="handleCopyScript"
    @delete="handleDeleteScript"
    @add-user="handleAddUser"
    @edit-user="handleEditUser"
    @delete-user="handleDeleteUser"
    @start-maa-config="handleStartMAAConfig"
    @start-src-config="handleStartSRCConfig"
    @start-maa-end-config="handleStartMaaEndConfig"
    @start-maa-end-user-config="handleStartMaaEndUserConfig"
    @start-okww-config="handleStartOkwwConfig"
    @toggle-user-status="handleToggleUserStatus"
    @scripts-reordered="handleScriptsReordered"
  />

  <ScriptCreateDialog
    v-model:open="scriptCreateVisible"
    :templates="templates"
    :submitting="addLoading || templateLoading"
    :template-loading="templateLoading"
    :template-error="templateError"
    @request-templates="loadTemplates"
    @submit="handleSubmitScriptCreate"
  />
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  DownOutlined,
  PlusOutlined,
  SearchOutlined,
  SettingOutlined,
  UpOutlined,
} from '@ant-design/icons-vue'
import ScriptTable from '@/components/ScriptTable.vue'
import ScriptCreateDialog from '@/views/scripts/components/ScriptCreateDialog.vue'
import type { Script, ScriptType, User } from '@/types/script'
import {
  getScriptEditSegment,
  type ScriptCreateRequest,
} from '@/views/scripts/components/scriptCreateFlow'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import { useWebSocket } from '@/composables/useWebSocket'
import {
  WS_TASK_COMPLETED,
  WS_TASK_NOTICE,
  type WSTaskCompletedData,
  type WSTaskNoticeData,
} from '@/services/websocket/types'
import { useTemplateApi, type WebConfigTemplate } from '@/composables/useTemplateApi'
import { Service } from '@/api/services/Service'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import DocLink from '@/components/DocLink.vue'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { filterScriptsByKeyword } from '@/views/scripts/scriptSearch'

const { t } = useI18n()

defineOptions({ name: 'ScriptsPage' })

const logger = window.electronAPI.getLogger('脚本管理')

const router = useRouter()
const { addScript, deleteScript, getScriptsWithUsers } = useScriptApi()
const { updateUser, deleteUser } = useUserApi()
const { subscribe, unsubscribe } = useWebSocket()
const { getWebConfigTemplates, importScriptFromWeb, error: templateError } = useTemplateApi()

const scripts = ref<Script[]>([])
const scriptSearchKeyword = ref('')
const isSearching = computed(() => Boolean(scriptSearchKeyword.value.trim()))
const filteredScripts = computed(() =>
  filterScriptsByKeyword(scripts.value, scriptSearchKeyword.value)
)
const scriptTableRef = ref<InstanceType<typeof ScriptTable> | null>(null)
// 增加：标记是否已经完成过一次脚本列表加载（成功或失败都算一次）
const loadedOnce = ref(false)
const scriptCreateVisible = ref(false)
const templates = ref<WebConfigTemplate[]>([])
const addLoading = ref(false)
const copyingScriptId = ref<string | null>(null)
const templateLoading = ref(false)

// 配置会话遮罩：同一时刻只会有一个配置会话在前台
type ConfigMaskKind = 'MAA' | 'SRC' | 'MaaEnd' | 'Okww'
const configMask = ref<{ kind: ConfigMaskKind; script: Script; user: User | null } | null>(null)
const clearConfigMask = () => {
  configMask.value = null
}
const configMaskView = computed(() => {
  const mask = configMask.value
  if (!mask) return null
  switch (mask.kind) {
    case 'MAA':
      return {
        iconColor: '#1890ff',
        title: t('scripts.mask.maaTitle'),
        description: t('scripts.mask.maaDesc'),
        tip: t('scripts.mask.unlockTip'),
        button: t('scripts.mask.saveConfig'),
      }
    case 'SRC':
      return {
        iconColor: '#722ed1',
        title: t('scripts.mask.srcTitle'),
        description: t('scripts.mask.srcDesc'),
        tip: t('scripts.mask.unlockTip'),
        button: t('scripts.mask.saveConfig'),
      }
    case 'MaaEnd':
      return {
        iconColor: 'var(--ant-color-primary)',
        title: mask.user ? t('scripts.mask.maaEndUserTitle') : t('scripts.mask.maaEndScriptTitle'),
        description: mask.user
          ? t('scripts.mask.maaEndUserDesc', { name: mask.user.Info.Name })
          : t('scripts.mask.maaEndScriptDesc'),
        tip: t('scripts.mask.maaEndUnlockTip'),
        button: t('scripts.mask.saveConfig'),
      }
    case 'Okww':
      return {
        iconColor: 'var(--ant-color-primary)',
        title: t('scripts.mask.okwwTitle'),
        description: t('scripts.mask.okwwDesc'),
        tip: t('scripts.mask.okwwUnlockTip'),
        button: t('scripts.mask.saveSettings'),
      }
    default:
      return null
  }
})
const handleSaveConfigMask = () => {
  const mask = configMask.value
  if (!mask) return
  switch (mask.kind) {
    case 'MAA':
      void handleSaveMAAConfig(mask.script)
      break
    case 'SRC':
      void handleSaveSRCConfig(mask.script)
      break
    case 'MaaEnd':
      void handleSaveMaaEndConfig(mask.script)
      break
    case 'Okww':
      void handleSaveOkwwConfig(mask.script)
      break
  }
}

const scriptEditPathMap: Record<ScriptType, string> = {
  MAA: 'maa',
  General: 'general',
  Okww: 'okww',
  OkNte: 'oknte',
  SRC: 'src',
  MaaEnd: 'maaend',
  M9A: 'm9a',
  MaaFW: 'maafw',
  HSR: 'hsr',
  BetterGI: 'bettergi',
  ZzzOd: 'zzzod',
  BAAH: 'baah',
}

const getScriptEditPath = (type: ScriptType) => scriptEditPathMap[type]

// 配置会话超时：30 分钟没保存就自动断开
const CONFIG_SESSION_TIMEOUT_MS = 30 * 60 * 1000

// WebSocket连接管理：scriptId/userId -> { subscriptionIds, taskId, timeoutId }
const activeConnections = ref<
  Map<
    string,
    { subscriptionIds: string[]; taskId: string; timeoutId?: ReturnType<typeof setTimeout> }
  >
>(new Map())

onMounted(() => {
  loadScripts()
})

// 离开页面时释放全部配置会话订阅并清掉超时定时器，不会在其他页面弹出提示
onUnmounted(() => {
  for (const connection of activeConnections.value.values()) {
    for (const subscriptionId of connection.subscriptionIds) {
      unsubscribe(subscriptionId)
    }
    if (connection.timeoutId) clearTimeout(connection.timeoutId)
  }
  activeConnections.value.clear()
})

const loadScripts = async () => {
  try {
    const scriptDetails = await getScriptsWithUsers()

    // 将 ScriptDetail 转换为 Script 格式（为了兼容现有的表格组件）
    scripts.value = scriptDetails.map(detail => ({
      id: detail.uid,
      type: detail.type as ScriptType,
      name: detail.name,
      config: detail.config,
      users: (detail.users || []).filter((user): user is NonNullable<typeof user> => user !== null),
    }))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本列表失败: ${errorMsg}`)
    message.error(t('scripts.toast.loadListFailed', { error: errorMsg }))
  } finally {
    // 首次加载结束（不论成功失败）后置位，避免初始闪烁
    loadedOnce.value = true
  }
}

const handleAddScript = () => {
  scriptCreateVisible.value = true
}

const handleCollapseAll = () => {
  scriptTableRef.value?.collapseAllUsers()
}

const handleExpandAll = () => {
  scriptTableRef.value?.expandAllUsers()
}

// 拖拽排序已写回后端，父级列表同步成新顺序，否则后续共享对象改动会把顺序弹回去
const handleScriptsReordered = (reordered: Script[]) => {
  scripts.value = [...reordered]
}

const navigateToCreatedScript = (
  scriptId: string,
  type: ScriptType,
  data?: Record<string, unknown>
) => {
  const route = {
    // MFW 新建后进分步引导；其余类型直接进编辑页
    path:
      type === 'MaaFW'
        ? `/scripts/${scriptId}/setup/maafw`
        : `/scripts/${scriptId}/edit/${getScriptEditSegment(type)}`,
    ...(data
      ? {
          state: {
            scriptData: {
              id: scriptId,
              type,
              config: JSON.parse(JSON.stringify(data)),
            },
          },
        }
      : {}),
  }
  router.push(route)
}

const handleSubmitScriptCreate = async (request: ScriptCreateRequest) => {
  addLoading.value = true
  try {
    const type = request.kind === 'new' ? request.type : 'General'
    const result = await addScript(type)
    if (!result) return

    if (request.kind === 'general-template') {
      const imported = await importScriptFromWeb(result.scriptId, request.template.downloadUrl)
      if (!imported) return
      message.success(t('scripts.toast.createdFromTemplate', { name: request.template.configName }))
      await loadScripts()
      scriptCreateVisible.value = false
      navigateToCreatedScript(result.scriptId, 'General')
      return
    }

    scriptCreateVisible.value = false
    navigateToCreatedScript(result.scriptId, type, result.data)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`创建脚本失败: ${errorMsg}`)
  } finally {
    addLoading.value = false
  }
}

const loadTemplates = async () => {
  templateLoading.value = true
  try {
    templates.value = await getWebConfigTemplates()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载模板列表失败: ${errorMsg}`)
  } finally {
    templateLoading.value = false
  }
}

const handleEditScript = (script: Script) => {
  router.push(`/scripts/${script.id}/edit/${getScriptEditPath(script.type)}`)
}

const handleDeleteScript = async (script: Script) => {
  const result = await deleteScript(script.id)
  if (result) {
    // 后端已删除，本地直接移除即可，不必整份重拉
    scripts.value = scripts.value.filter(item => item.id !== script.id)
  }
}

const handleCopyScript = async (script: Script) => {
  addLoading.value = true
  copyingScriptId.value = script.id
  try {
    const result = await addScript(script.type, script.id)
    if (result) {
      await loadScripts()
      message.success(t('scripts.toast.copied', { name: script.name }))
    }
  } finally {
    addLoading.value = false
    copyingScriptId.value = null
  }
}

const handleAddUser = (script: Script) => {
  // 根据脚本类型跳转到对应的用户添加页面
  if (script.type === 'MAA') {
    router.push(`/scripts/${script.id}/users/add/maa`)
  } else if (script.type === 'SRC') {
    router.push(`/scripts/${script.id}/users/add/src`)
  } else if (script.type === 'MaaEnd') {
    router.push(`/scripts/${script.id}/users/add/maaend`)
  } else if (script.type === 'M9A') {
    router.push(`/scripts/${script.id}/users/add/m9a`)
  } else if (script.type === 'MaaFW') {
    router.push(`/scripts/${script.id}/users/add/maafw`)
  } else if (script.type === 'Okww') {
    router.push(`/scripts/${script.id}/users/add/okww`)
  } else if (script.type === 'OkNte') {
    router.push(`/scripts/${script.id}/users/add/oknte`)
  } else if (script.type === 'HSR') {
    router.push(`/scripts/${script.id}/users/add/hsr`)
  } else if (script.type === 'BetterGI') {
    router.push(`/scripts/${script.id}/users/add/bettergi`)
  } else if (script.type === 'ZzzOd') {
    router.push(`/scripts/${script.id}/users/add/zzzod`)
  } else if (script.type === 'BAAH') {
    router.push(`/scripts/${script.id}/users/add/baah`)
  } else {
    router.push(`/scripts/${script.id}/users/add/general`)
  }
}

const handleEditUser = (user: User) => {
  // 从用户数据中找到对应的脚本
  const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
  if (script) {
    // 根据脚本类型跳转到对应的用户编辑页面
    if (script.type === 'MAA') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/maa`)
    } else if (script.type === 'SRC') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/src`)
    } else if (script.type === 'MaaEnd') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/maaend`)
    } else if (script.type === 'M9A') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/m9a`)
    } else if (script.type === 'MaaFW') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/maafw`)
    } else if (script.type === 'Okww') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/okww`)
    } else if (script.type === 'OkNte') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/oknte`)
    } else if (script.type === 'HSR') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/hsr`)
    } else if (script.type === 'BetterGI') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/bettergi`)
    } else if (script.type === 'ZzzOd') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/zzzod`)
    } else if (script.type === 'BAAH') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/baah`)
    } else {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/general`)
    }
  } else {
    message.error(t('scripts.toast.scriptNotFound'))
  }
}

const handleDeleteUser = async (user: User) => {
  // 从用户数据中找到对应的脚本
  const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
  if (!script) {
    message.error(t('scripts.toast.scriptNotFound'))
    return
  }

  const result = await deleteUser(script.id, user.id)
  if (result) {
    // 删除成功后，从本地数据中移除用户
    const userIndex = script.users.findIndex(u => u.id === user.id)
    if (userIndex > -1) {
      script.users.splice(userIndex, 1)
    }
  }
}

const clearConfigSession = (
  targetId: string,
  subscriptionIds: string[] | undefined,
  clearState: () => void
) => {
  if (subscriptionIds) {
    for (const subscriptionId of subscriptionIds) {
      unsubscribe(subscriptionId)
    }
  }
  const connection = activeConnections.value.get(targetId)
  if (connection?.timeoutId) clearTimeout(connection.timeoutId)
  activeConnections.value.delete(targetId)
  clearState()
}

// 会话超时定时器挂在连接记录上，会话结束或页面卸载时一并清掉
const scheduleConfigSessionTimeout = (
  targetId: string,
  clearState: () => void,
  onTimeout: () => void
) => {
  const connection = activeConnections.value.get(targetId)
  if (!connection) return
  connection.timeoutId = setTimeout(() => {
    const current = activeConnections.value.get(targetId)
    if (!current) return
    clearConfigSession(targetId, current.subscriptionIds, clearState)
    onTimeout()
  }, CONFIG_SESSION_TIMEOUT_MS)
}

const startConfigSession = async (
  targetId: string,
  label: string,
  setActiveState: () => void,
  clearState: () => void,
  onCompleted?: (data: WSTaskCompletedData) => void
) => {
  if (activeConnections.value.has(targetId)) {
    message.warning(t('scripts.toast.targetConfiguring'))
    return false
  }

  const response = await Service.addTaskApiDispatchStartPost({
    taskId: targetId,
    mode: TaskCreateIn.mode.SCRIPT_CONFIG,
  })
  if (response.code !== 200 || !response.taskId) {
    throw new Error(response.message || t('scripts.toast.startFailedRaw', { label }))
  }

  setActiveState()
  let sessionEnded = false
  const subscriptionIds: string[] = []
  subscriptionIds.push(
    subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
      const data = wsMessage.data as unknown as WSTaskNoticeData
      if (data.level === 'error') {
        message.error(t('scripts.toast.configFailed', { label, error: data.message }))
      }
    }),
    subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, wsMessage => {
      sessionEnded = true
      clearConfigSession(targetId, subscriptionIds, clearState)
      onCompleted?.(wsMessage.data as unknown as WSTaskCompletedData)
    })
  )
  if (sessionEnded) {
    for (const subscriptionId of subscriptionIds) {
      unsubscribe(subscriptionId)
    }
    return false
  }
  activeConnections.value.set(targetId, {
    subscriptionIds,
    taskId: response.taskId,
  })
  return true
}

const stopConfigSession = async (targetId: string, label: string, clearState: () => void) => {
  const connection = activeConnections.value.get(targetId)
  if (!connection) {
    message.error(t('scripts.toast.noSession'))
    return false
  }
  const response = await Service.stopTaskApiDispatchStopPost({
    taskId: connection.taskId,
  })
  if (response.code !== 200) {
    throw new Error(response.message || t('scripts.toast.saveFailedRaw', { label }))
  }
  clearConfigSession(targetId, connection.subscriptionIds, clearState)
  return true
}

// MAA / SRC 脚本级配置会话：走通用的 start/stop，带 sessionEnded 竞态守卫
const handleStartScriptConfig = async (script: Script, kind: 'MAA' | 'SRC') => {
  try {
    const started = await startConfigSession(
      script.id,
      kind,
      () => {
        configMask.value = { kind, script, user: null }
      },
      clearConfigMask,
      data => {
        logger.info(`脚本 ${script.name} 配置任务已结束`)
        if (data.outcome === 'success') {
          message.success(t('scripts.toast.configDone', { name: script.name }))
        }
      }
    )
    if (!started) return

    message.success(t('scripts.toast.configStarted', { name: script.name, label: kind }))
    scheduleConfigSessionTimeout(script.id, clearConfigMask, () =>
      message.info(t('scripts.toast.sessionTimeout', { name: script.name }))
    )
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动${kind}配置失败: ${errorMsg}`)
    message.error(t('scripts.toast.startConfigError', { label: kind, error: errorMsg }))
  }
}

const handleSaveScriptConfig = async (script: Script, kind: 'MAA' | 'SRC') => {
  try {
    const saved = await stopConfigSession(script.id, kind, clearConfigMask)
    if (saved) message.success(t('scripts.toast.configSaved', { name: script.name }))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存${kind}配置失败: ${errorMsg}`)
    message.error(t('scripts.toast.saveConfigError', { label: kind, error: errorMsg }))
  }
}

const handleStartMAAConfig = (script: Script) => handleStartScriptConfig(script, 'MAA')
const handleSaveMAAConfig = (script: Script) => handleSaveScriptConfig(script, 'MAA')
const handleStartSRCConfig = (script: Script) => handleStartScriptConfig(script, 'SRC')
const handleSaveSRCConfig = (script: Script) => handleSaveScriptConfig(script, 'SRC')

const handleStartMaaEndConfig = async (script: Script, user: User | null = null) => {
  try {
    const controllerType = (script.config as any).Game?.ControllerType
    if (!user && controllerType !== 'Win32-Front') {
      message.warning(t('scripts.toast.maaEndUnsupported'))
      return
    }

    const targetId = user?.id ?? script.id
    const started = await startConfigSession(
      targetId,
      'MaaEnd',
      () => {
        configMask.value = { kind: 'MaaEnd', script, user }
      },
      clearConfigMask
    )
    if (!started) return

    message.success(
      user
        ? t('scripts.toast.maaEndUserStarted', { script: script.name, user: user.Info.Name })
        : t('scripts.toast.maaEndScriptStarted', { script: script.name })
    )
    scheduleConfigSessionTimeout(targetId, clearConfigMask, () =>
      message.info(
        user
          ? t('scripts.toast.maaEndUserTimeout', { script: script.name, user: user.Info.Name })
          : t('scripts.toast.sessionTimeout', { name: script.name })
      )
    )
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动 MaaEnd 配置失败: ${errorMsg}`)
    message.error(t('scripts.toast.startConfigError', { label: 'MaaEnd', error: errorMsg }))
  }
}

const handleStartMaaEndUserConfig = async (script: Script, user: User) => {
  await handleStartMaaEndConfig(script, user)
}

const handleSaveMaaEndConfig = async (script: Script) => {
  try {
    const currentUser = configMask.value?.kind === 'MaaEnd' ? configMask.value.user : null
    const targetId = currentUser?.id ?? script.id
    const saved = await stopConfigSession(targetId, 'MaaEnd', clearConfigMask)
    if (saved) {
      message.success(
        currentUser
          ? t('scripts.toast.maaEndUserSaved', { script: script.name, user: currentUser.Info.Name })
          : t('scripts.toast.configSaved', { name: script.name })
      )
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 MaaEnd 配置失败: ${errorMsg}`)
    message.error(t('scripts.toast.saveConfigError', { label: 'MaaEnd', error: errorMsg }))
  }
}

const handleStartOkwwConfig = async (script: Script) => {
  try {
    const started = await startConfigSession(
      script.id,
      'ok-ww',
      () => {
        configMask.value = { kind: 'Okww', script, user: null }
      },
      clearConfigMask
    )
    if (started) message.success(t('scripts.toast.okwwStarted', { name: script.name }))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动 ok-ww 设置失败: ${errorMsg}`)
    message.error(t('scripts.toast.okwwStartFailed', { error: errorMsg }))
  }
}

const handleSaveOkwwConfig = async (script: Script) => {
  try {
    const saved = await stopConfigSession(script.id, 'ok-ww', clearConfigMask)
    if (saved) message.success(t('scripts.toast.okwwSaved', { name: script.name }))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 ok-ww 设置失败: ${errorMsg}`)
    message.error(t('scripts.toast.okwwSaveFailed', { error: errorMsg }))
  }
}

const handleToggleUserStatus = async (user: User) => {
  try {
    // 找到该用户对应的脚本
    const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
    if (!script) {
      message.error(t('scripts.toast.scriptNotFound'))
      return
    }
    const newStatus = !user.Info.Status

    // 后端是单字段 set：只发送 Status，避免 Info.Tag 等虚拟字段混入触发后端报错
    const result = await updateUser(script.id, user.id, {
      Info: { Status: newStatus },
    })

    if (result) {
      message.success(t('scripts.toast.userStatusUpdated'))
      // 更新本地用户状态
      user.Info.Status = newStatus
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新用户状态失败: ${errorMsg}`)
    message.error(t('scripts.toast.userStatusFailed', { error: errorMsg }))
  }
}
</script>

<style scoped>
.maa-config-mask {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.mask-content {
  background: var(--ant-color-bg-elevated);
  border-radius: 8px;
  padding: 24px;
  max-width: 480px;
  width: 100%;
  text-align: center;
  box-shadow:
    0 6px 16px 0 rgba(0, 0, 0, 0.08),
    0 3px 6px -4px rgba(0, 0, 0, 0.12),
    0 9px 28px 8px rgba(0, 0, 0, 0.05);
  border: 1px solid var(--ant-color-border);
}

.mask-icon {
  margin-bottom: 16px;
}

.mask-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--ant-color-text);
}

.mask-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0 0 24px;
  line-height: 1.5;
}

.mask-actions {
  display: flex;
  justify-content: center;
}

.link {
  display: inline-flex;
  align-items: center;
}

.link .anticon {
  margin-right: 8px;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: calc(100vh - 200px);
  text-align: center;
}

.empty-image-container {
  margin-bottom: 16px;
}

.empty-image {
  max-width: 100%;
  height: auto;
}

.empty-title {
  font-size: 18px;
  font-weight: 500;
  margin: 0;
  color: var(--ant-color-text);
}

.empty-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0;
}

.scripts-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 24px;
  padding: 0 4px;
}

.header-left {
  display: flex;
  flex: 1;
  min-width: 0;
  align-items: center;
  gap: 24px;
}

.script-search {
  width: min(360px, 40vw);
}

.header-actions {
  flex-shrink: 0;
  margin-left: 16px;
}

@media (max-width: 768px) {
  .page-title {
    font-size: 24px;
  }

  .scripts-header {
    align-items: stretch;
    flex-direction: column;
    gap: 16px;
    padding: 0 2px;
  }

  .header-left {
    align-items: stretch;
    flex-direction: column;
    gap: 12px;
  }

  .script-search {
    width: 100%;
  }

  .header-actions {
    margin-left: 0;
  }
}

.page-title {
  margin: 0 0 8px 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
