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
      <h1 class="page-title app-page-title">{{ t('core.scripts.title') }}</h1>
      <DocLink :url="MAS_DOC_URLS.scripts" />
      <a-input
        v-model:value="scriptSearchKeyword"
        allow-clear
        class="script-search"
        :placeholder="t('core.scripts.searchPlaceholder')"
        :aria-label="t('core.scripts.searchAria')"
      >
        <template #prefix><SearchOutlined /></template>
      </a-input>
    </div>
    <div class="header-actions">
      <a-space size="middle">
        <a-tooltip :title="t('core.scripts.collapseAllTip')">
          <a-button
            size="large"
            :disabled="scripts.length === 0 || isSearching"
            @click="handleCollapseAll"
          >
            <template #icon><UpOutlined /></template>
            {{ t('core.scripts.collapseAll') }}
          </a-button>
        </a-tooltip>
        <a-tooltip :title="t('core.scripts.expandAllTip')">
          <a-button
            size="large"
            :disabled="scripts.length === 0 || isSearching"
            @click="handleExpandAll"
          >
            <template #icon><DownOutlined /></template>
            {{ t('core.scripts.expandAll') }}
          </a-button>
        </a-tooltip>
        <a-button type="primary" size="large" class="link" @click="handleAddScript">
          <template #icon>
            <PlusOutlined />
          </template>
          {{ t('core.scripts.create.title') }}
        </a-button>
      </a-space>
    </div>
  </div>

  <a-alert
    v-if="scriptListError"
    type="error"
    show-icon
    :message="scriptListError"
    class="script-list-error"
  >
    <template #action>
      <a-button :loading="listLoading" @click="loadScripts">{{
        t('core.apiErrors.retry')
      }}</a-button>
    </template>
  </a-alert>

  <!-- 空状态 -->
  <!-- 增加 loadedOnce 条件，避免初始渲染时闪烁 -->
  <div v-if="listLoading && !scriptListError && scripts.length === 0" class="scripts-loading">
    <a-spin size="large" />
  </div>
  <div
    v-else-if="
      !scriptListError && !listLoading && !addLoading && loadedOnce && scripts.length === 0
    "
    class="empty-state"
  >
    <NoData :image-style="{ height: '120px' }">
      <template #description>
        <h3 class="empty-title">{{ t('core.scripts.empty.title') }}</h3>
        <p class="empty-description">{{ t('core.scripts.empty.desc') }}</p>
      </template>
    </NoData>
  </div>

  <div
    v-else-if="
      !scriptListError && !listLoading && !addLoading && loadedOnce && filteredScripts.length === 0
    "
    class="empty-state"
  >
    <NoData :description="t('core.scripts.empty.noMatch')">
      <a-button @click="scriptSearchKeyword = ''">{{ t('core.scripts.clearSearch') }}</a-button>
    </NoData>
  </div>

  <ScriptTable
    v-else
    ref="scriptTableRef"
    :scripts="filteredScripts"
    :searching="isSearching"
    :active-connections="activeConnections"
    :copying-script-id="copyingScriptId"
    :retrying-users="retryingUsers"
    @retry-users="retryScriptUsers"
    @edit="handleEditScript"
    @copy="handleCopyScript"
    @delete="handleDeleteScript"
    @add-user="handleAddUser"
    @edit-user="handleEditUser"
    @delete-user="handleDeleteUser"
    @start-maa-config="handleStartMAAConfig"
    @start-src-config="handleStartSRCConfig"
    @start-maa-end-config="handleStartMaaEndConfig"
    @start-okww-config="handleStartOkwwConfig"
    @start-whimbox-config="handleStartWhimboxConfig"
    @toggle-user-status="handleToggleUserStatus"
    @scripts-reordered="handleScriptsReordered"
  />

  <ScriptCreateDialog
    v-model:open="scriptCreateVisible"
    :templates="templates"
    :submitting="addLoading || templateLoading"
    :template-loading="templateLoading"
    :template-error="templateError"
    :template-page="templatePage"
    :template-page-size="TEMPLATE_PAGE_SIZE"
    :template-total="templateTotal"
    :mfw-sources="mfwSources"
    :mfw-sources-loading="mfwSourcesLoading"
    :mfw-sources-error="mfwSourcesError"
    @request-templates="loadTemplates"
    @request-mfw-sources="loadMfwSources"
    @submit="handleSubmitScriptCreate"
  />
</template>

<script setup lang="ts">
import { requestTaskStart, stopNativeConfig } from '@/composables/useTaskApi'

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
import ScriptTable from '@/views/scripts/components/ScriptTable.vue'
import { getApiErrorMessage } from '@/utils/apiError'
import ScriptCreateDialog from '@/views/scripts/components/ScriptCreateDialog.vue'
import type { ScriptType } from '@/types/script'
import type { ScriptListItem, ScriptListUser } from '@/views/scripts/scriptListModel'
import {
  getScriptEditSegment,
  isMfwFamily,
  type TemplateRequest,
} from '@/views/scripts/components/scriptCreateFlow'
import { maafwRouteLocation } from '@/router/maafwFlavorRoutes'
import { useScriptApi } from '@/composables/useScriptApi'
import { useScriptList } from '@/views/scripts/useScriptList'
import { useUserApi } from '@/composables/useUserApi'
import { useWebSocket } from '@/composables/useWebSocket'
import { onTaskRuntimeEvent } from '@/composables/useTaskRuntimeState'
import {
  WS_TASK_COMPLETED,
  WS_TASK_CONFIG_DISCARDED,
  WS_TASK_NOTICE,
  type WSTaskCompletedData,
  type WSTaskConfigDiscardedData,
  type WSTaskNoticeData,
} from '@/services/websocket/types'
import {
  TEMPLATE_PAGE_SIZE,
  useTemplateApi,
  type ShareTemplateItem,
} from '@/composables/useTemplateApi'
import { useMaaFWEmbeddedApi } from '@/composables/useMaaFWEmbeddedApi'
import type { MaaFWEmbeddedSourceItem } from '@/api'
import { Service } from '@/api/services/Service'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import DocLink from '@/components/DocLink.vue'
import { showConfigDiscardWarning } from '@/utils/configSessionDiscard'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { filterScriptsByKeyword } from '@/views/scripts/scriptSearch'
import { useScriptCreation } from '@/views/scripts/useScriptCreation'

const { t } = useI18n()

defineOptions({ name: 'ScriptsPage' })

const logger = window.electronAPI.getLogger('脚本管理')

const router = useRouter()
const { deleteScript } = useScriptApi()
const {
  getScriptsWithUsers,
  getScriptUsers,
  loading: listLoading,
  error: scriptListError,
} = useScriptList()
const retryingUsers = ref(new Set<string>())
const { updateUser, deleteUser } = useUserApi()
const { subscribe, unsubscribe } = useWebSocket()
const { getShareTemplates, importScriptFromTemplate, error: templateError } = useTemplateApi()
const { listEmbeddedSources, cloneEmbedded } = useMaaFWEmbeddedApi()

const scripts = ref<ScriptListItem[]>([])
const scriptSearchKeyword = ref('')
const isSearching = computed(() => Boolean(scriptSearchKeyword.value.trim()))
const filteredScripts = computed(() =>
  filterScriptsByKeyword(scripts.value, scriptSearchKeyword.value)
)
const scriptTableRef = ref<InstanceType<typeof ScriptTable> | null>(null)
// 增加：标记是否已经完成过一次脚本列表加载（成功或失败都算一次）
const loadedOnce = ref(false)
const scriptCreateVisible = ref(false)
const templates = ref<ShareTemplateItem[]>([])
const templatePage = ref(1)
const templateTotal = ref(0)
let templateRequestId = 0
const templateLoading = ref(false)
// 新建 MFW 脚本第二步「复用已有脚本的项目」的候选：有健康副本的 MFW / M9A 脚本
const mfwSources = ref<MaaFWEmbeddedSourceItem[]>([])
const mfwSourcesLoading = ref(false)
const mfwSourcesError = ref<string | null>(null)

// 配置会话遮罩：同一时刻只会有一个配置会话在前台
type ConfigMaskKind = 'MAA' | 'SRC' | 'MaaEnd' | 'Okww' | 'Whimbox'
const configMask = ref<{ kind: ConfigMaskKind; script: ScriptListItem } | null>(null)
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
        title: t('core.scripts.mask.maaTitle'),
        description: t('core.scripts.mask.maaDesc'),
        tip: t('core.scripts.mask.unlockTip'),
        button: t('core.scripts.mask.saveConfig'),
      }
    case 'SRC':
      return {
        iconColor: '#722ed1',
        title: t('core.scripts.mask.srcTitle'),
        description: t('core.scripts.mask.srcDesc'),
        tip: t('core.scripts.mask.unlockTip'),
        button: t('core.scripts.mask.saveConfig'),
      }
    case 'MaaEnd':
      return {
        iconColor: 'var(--ant-color-primary)',
        title: t('core.scripts.mask.maaEndScriptTitle'),
        description: t('core.scripts.mask.maaEndScriptDesc'),
        tip: t('core.scripts.mask.maaEndUnlockTip'),
        button: t('core.scripts.mask.saveConfig'),
      }
    case 'Okww':
      return {
        iconColor: 'var(--ant-color-primary)',
        title: t('core.scripts.mask.okwwTitle'),
        description: t('core.scripts.mask.okwwDesc'),
        tip: t('core.scripts.mask.okwwUnlockTip'),
        button: t('core.scripts.mask.saveSettings'),
      }
    case 'Whimbox':
      return {
        iconColor: 'var(--ant-color-primary)',
        title: t('core.scripts.mask.whimboxTitle'),
        description: t('core.scripts.mask.whimboxDesc'),
        tip: t('core.scripts.mask.whimboxUnlockTip'),
        button: t('core.scripts.mask.saveSettings'),
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
    case 'Whimbox':
      void handleSaveWhimboxConfig(mask.script)
      break
  }
}

// 与新建流程同一张表（MaaFW 与各特调的后缀取自特调注册表）
const getScriptEditPath = (type: ScriptType) => getScriptEditSegment(type)

// 配置会话超时：30 分钟没保存就自动断开
const CONFIG_SESSION_TIMEOUT_MS = 30 * 60 * 1000
// 丢弃帧由任务收尾过程发出，与停止响应分属两条链路：停止后等一个回合再判定改动是否生效
const DISCARD_FRAME_GRACE_MS = 300

// 配置会话的连接记录（键为 scriptId）
type ConfigSessionConnection = {
  subscriptionIds: string[]
  taskId: string
  timeoutId?: ReturnType<typeof setTimeout>
  /** 后端下发的丢弃原因（structure/unreadable/not_written），改动未被丢弃为 null */
  discardedReason: string | null
  /** 丢弃提示是否已弹过：完成帧与停止响应都会走到会话结束，只提示一次 */
  discardWarned: boolean
}

// WebSocket连接管理：scriptId -> ConfigSessionConnection
const activeConnections = ref<Map<string, ConfigSessionConnection>>(new Map())

// 定时队列等别处发起的任务结束后，用户的代理状态已在后端更新，防抖后重新拉一次列表；
// removed 是断线期间结束、没收到完成通知的任务
const TASK_COMPLETED_RELOAD_DELAY_MS = 1000
let taskCompletedReloadTimer: ReturnType<typeof setTimeout> | undefined
let disposeTaskRuntimeListener: (() => void) | undefined

onMounted(() => {
  loadScripts()
  disposeTaskRuntimeListener = onTaskRuntimeEvent(event => {
    const ended =
      event.type === 'removed' ||
      (event.type === 'completed' && event.state.mode !== 'ScriptConfig')
    if (!ended) return
    clearTimeout(taskCompletedReloadTimer)
    taskCompletedReloadTimer = setTimeout(() => void loadScripts(), TASK_COMPLETED_RELOAD_DELAY_MS)
  })
})

// 离开页面时释放全部配置会话订阅并清掉超时定时器，不会在其他页面弹出提示
onUnmounted(() => {
  disposeTaskRuntimeListener?.()
  clearTimeout(taskCompletedReloadTimer)
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
    const result = await getScriptsWithUsers()
    if (!scriptListError.value) scripts.value = result
  } catch (error) {
    const errorMsg = getApiErrorMessage(error, t('core.apiErrors.scriptListFailed'))
    logger.error(`加载脚本列表失败: ${errorMsg}`)
    scriptListError.value = errorMsg
  } finally {
    // 首次加载结束（不论成功失败）后置位，避免初始闪烁
    loadedOnce.value = true
  }
}

const retryScriptUsers = async (scriptId: string) => {
  const script = scripts.value.find(item => item.id === scriptId)
  if (!script || retryingUsers.value.has(scriptId)) return
  retryingUsers.value.add(scriptId)
  try {
    const result = await getScriptUsers(scriptId)
    // 整体刷新或删除后，旧的重试结果不再属于当前列表。
    if (!scripts.value.includes(script)) return
    script.users = result.users
    script.usersLoadError = result.error
  } finally {
    retryingUsers.value.delete(scriptId)
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
const handleScriptsReordered = (reordered: ScriptListItem[]) => {
  scripts.value = [...reordered]
}

const {
  addLoading,
  copyingScriptId,
  submit: handleSubmitScriptCreate,
  copy: handleCopyScript,
} = useScriptCreation({
  reloadScripts: () => loadScripts(),
  closeDialog: () => {
    scriptCreateVisible.value = false
  },
  importTemplate: importScriptFromTemplate,
  cloneProject: cloneEmbedded,
})

const loadMfwSources = async () => {
  mfwSourcesLoading.value = true
  mfwSourcesError.value = null
  try {
    mfwSources.value = await listEmbeddedSources()
  } catch (error) {
    // 读失败不能伪装成「没有可复用的脚本」：对话框按错误态显示原因与重试
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载可复用的 MFW 脚本失败: ${errorMsg}`)
    mfwSources.value = []
    mfwSourcesError.value = t('core.scripts.toast.mfwSourcesFailed', { error: errorMsg })
  } finally {
    mfwSourcesLoading.value = false
  }
}

const loadTemplates = async (query: TemplateRequest = { page: 1, keyword: '' }) => {
  const requestId = ++templateRequestId
  templateLoading.value = true
  try {
    const result = await getShareTemplates({
      page: query.page,
      pageSize: TEMPLATE_PAGE_SIZE,
      keyword: query.keyword,
    })
    // 快速改关键字时请求可能乱序返回，只认最后一次
    if (requestId !== templateRequestId) return
    templates.value = result.items
    templatePage.value = result.page
    templateTotal.value = result.total
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载模板列表失败: ${errorMsg}`)
  } finally {
    if (requestId === templateRequestId) templateLoading.value = false
  }
}

const handleEditScript = (script: ScriptListItem) => {
  router.push(
    isMfwFamily(script.type)
      ? maafwRouteLocation(script.type, 'script', { id: script.id })
      : `/scripts/${script.id}/edit/${getScriptEditPath(script.type)}`
  )
}

const handleDeleteScript = async (script: ScriptListItem) => {
  const result = await deleteScript(script.id)
  if (result) {
    // 后端已删除，本地直接移除即可，不必整份重拉
    scripts.value = scripts.value.filter(item => item.id !== script.id)
  }
}

const handleAddUser = (script: ScriptListItem) => {
  // 根据脚本类型跳转到对应的用户添加页面
  if (isMfwFamily(script.type)) {
    // MaaFW 与各特调共用一个用户页，路由按特调注册表生成
    router.push(maafwRouteLocation(script.type, 'userAdd', { scriptId: script.id }))
  } else if (script.type === 'MAA') {
    router.push(`/scripts/${script.id}/users/add/maa`)
  } else if (script.type === 'SRC') {
    router.push(`/scripts/${script.id}/users/add/src`)
  } else if (script.type === 'MaaEnd') {
    router.push(`/scripts/${script.id}/users/add/maaend`)
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
  } else if (script.type === 'Whimbox') {
    router.push(`/scripts/${script.id}/users/add/whimbox`)
  } else {
    router.push(`/scripts/${script.id}/users/add/general`)
  }
}

const handleEditUser = (user: ScriptListUser) => {
  // 从用户数据中找到对应的脚本
  const script = scripts.value.find(s => s.id === user.scriptId)
  if (script) {
    // 根据脚本类型跳转到对应的用户编辑页面
    if (isMfwFamily(script.type)) {
      // MaaFW 与各特调共用一个用户页，路由按特调注册表生成
      router.push(
        maafwRouteLocation(script.type, 'userEdit', { scriptId: script.id, userId: user.id })
      )
    } else if (script.type === 'MAA') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/maa`)
    } else if (script.type === 'SRC') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/src`)
    } else if (script.type === 'MaaEnd') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/maaend`)
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
    } else if (script.type === 'Whimbox') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/whimbox`)
    } else {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/general`)
    }
  } else {
    message.error(t('core.scripts.toast.scriptNotFound'))
  }
}

const handleDeleteUser = async (user: ScriptListUser) => {
  // 从用户数据中找到对应的脚本
  const script = scripts.value.find(s => s.id === user.scriptId)
  if (!script) {
    message.error(t('core.scripts.toast.scriptNotFound'))
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

// 结束一次配置会话：释放订阅与遮罩，必要时补一次「改动被丢弃」提示。
// 返回改动是否生效（false 表示后端已丢弃，调用方不该再提示「已保存」）。
const finishConfigSession = (
  targetId: string,
  connection: ConfigSessionConnection,
  clearState: () => void
) => {
  clearConfigSession(targetId, connection.subscriptionIds, clearState)
  if (connection.discardedReason && !connection.discardWarned) {
    connection.discardWarned = true
    showConfigDiscardWarning(t, connection.discardedReason)
  }
  return connection.discardedReason === null
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
  onCompleted?: (data: WSTaskCompletedData, discardedReason: string | null) => void
) => {
  if (activeConnections.value.has(targetId)) {
    message.warning(t('core.scripts.toast.targetConfiguring'))
    return false
  }

  const response = await requestTaskStart(
    {
      taskId: targetId,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
    },
    { source: 'script_config', target_kind: 'script' }
  )
  if (response.code !== 200 || !response.taskId) {
    throw new Error(response.message || t('core.scripts.toast.startFailedRaw', { label }))
  }

  setActiveState()
  let sessionEnded = false
  // 连接记录先建好：丢弃帧与完成帧都可能早于停止响应到达，两个回调都要读到同一份记录
  const connection: ConfigSessionConnection = {
    subscriptionIds: [],
    taskId: response.taskId,
    discardedReason: null,
    discardWarned: false,
  }
  connection.subscriptionIds.push(
    subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
      const data = wsMessage.data as unknown as WSTaskNoticeData
      if (data.level === 'error') {
        message.error(t('core.scripts.toast.configFailed', { label, error: data.message }))
      }
    }),
    subscribe({ id: response.taskId, type: WS_TASK_CONFIG_DISCARDED }, wsMessage => {
      const data = wsMessage.data as unknown as WSTaskConfigDiscardedData
      connection.discardedReason = data.reason
      logger.info(`收到配置会话丢弃通知: reason=${data.reason}`)
    }),
    subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, wsMessage => {
      sessionEnded = true
      finishConfigSession(targetId, connection, clearState)
      onCompleted?.(wsMessage.data as unknown as WSTaskCompletedData, connection.discardedReason)
    })
  )
  if (sessionEnded) {
    for (const subscriptionId of connection.subscriptionIds) {
      unsubscribe(subscriptionId)
    }
    return false
  }
  activeConnections.value.set(targetId, connection)
  return true
}

const stopConfigSession = async (targetId: string, label: string, clearState: () => void) => {
  const connection = activeConnections.value.get(targetId)
  if (!connection) {
    message.error(t('core.scripts.toast.noSession'))
    return false
  }
  const response = await stopNativeConfig(connection.taskId, 'save')
  if (response.code !== 200) {
    throw new Error(response.message || t('core.scripts.toast.saveFailedRaw', { label }))
  }
  // 丢弃帧先于停止响应写出，但到达顺序不保证，等一个回合再判定改动是否生效
  await new Promise(resolve => setTimeout(resolve, DISCARD_FRAME_GRACE_MS))
  return finishConfigSession(targetId, connection, clearState)
}

// 脚本级配置会话（MAA / SRC / Whimbox）：走通用的 start/stop，带 sessionEnded 竞态守卫
const handleStartScriptConfig = async (script: ScriptListItem, kind: 'MAA' | 'SRC' | 'Whimbox') => {
  try {
    const started = await startConfigSession(
      script.id,
      kind,
      () => {
        configMask.value = { kind, script }
      },
      clearConfigMask,
      (data, discardedReason) => {
        logger.info(`脚本 ${script.name} 配置任务已结束`)
        // 改动被丢弃时弹窗已说明去向，再提示「已完成」互相矛盾
        if (discardedReason) return
        if (data.outcome === 'success') {
          message.success(t('core.scripts.toast.configDone', { name: script.name }))
        }
      }
    )
    if (!started) return

    message.success(t('core.scripts.toast.configStarted', { name: script.name, label: kind }))
    scheduleConfigSessionTimeout(script.id, clearConfigMask, () =>
      message.info(t('core.scripts.toast.sessionTimeout', { name: script.name }))
    )
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动${kind}配置失败: ${errorMsg}`)
    message.error(t('core.scripts.toast.startConfigError', { label: kind, error: errorMsg }))
  }
}

const handleSaveScriptConfig = async (script: ScriptListItem, kind: 'MAA' | 'SRC' | 'Whimbox') => {
  try {
    const saved = await stopConfigSession(script.id, kind, clearConfigMask)
    if (saved) message.success(t('core.scripts.toast.configSaved', { name: script.name }))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存${kind}配置失败: ${errorMsg}`)
    message.error(t('core.scripts.toast.saveConfigError', { label: kind, error: errorMsg }))
  }
}

const handleStartMAAConfig = (script: ScriptListItem) => handleStartScriptConfig(script, 'MAA')
const handleSaveMAAConfig = (script: ScriptListItem) => handleSaveScriptConfig(script, 'MAA')
const handleStartSRCConfig = (script: ScriptListItem) => handleStartScriptConfig(script, 'SRC')
const handleSaveSRCConfig = (script: ScriptListItem) => handleSaveScriptConfig(script, 'SRC')
// 奇想盒：无参数拉起原生 app（下载跑图路线、配置模型/键位等都在那边做，MAS 零写入）
const handleStartWhimboxConfig = (script: ScriptListItem) =>
  handleStartScriptConfig(script, 'Whimbox')
const handleSaveWhimboxConfig = (script: ScriptListItem) =>
  handleSaveScriptConfig(script, 'Whimbox')

const handleStartMaaEndConfig = async (script: ScriptListItem) => {
  try {
    const controllerType = script.controllerType
    if (controllerType !== 'Win32-Front') {
      message.warning(t('core.scripts.toast.maaEndUnsupported'))
      return
    }

    const started = await startConfigSession(
      script.id,
      'MaaEnd',
      () => {
        configMask.value = { kind: 'MaaEnd', script }
      },
      clearConfigMask
    )
    if (!started) return

    message.success(t('core.scripts.toast.maaEndScriptStarted', { script: script.name }))
    scheduleConfigSessionTimeout(script.id, clearConfigMask, () =>
      message.info(t('core.scripts.toast.sessionTimeout', { name: script.name }))
    )
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动 MaaEnd 配置失败: ${errorMsg}`)
    message.error(t('core.scripts.toast.startConfigError', { label: 'MaaEnd', error: errorMsg }))
  }
}

const handleSaveMaaEndConfig = async (script: ScriptListItem) => {
  try {
    const saved = await stopConfigSession(script.id, 'MaaEnd', clearConfigMask)
    if (saved) {
      message.success(t('core.scripts.toast.configSaved', { name: script.name }))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 MaaEnd 配置失败: ${errorMsg}`)
    message.error(t('core.scripts.toast.saveConfigError', { label: 'MaaEnd', error: errorMsg }))
  }
}

const handleStartOkwwConfig = async (script: ScriptListItem) => {
  try {
    const started = await startConfigSession(
      script.id,
      'ok-ww',
      () => {
        configMask.value = { kind: 'Okww', script }
      },
      clearConfigMask
    )
    if (started) message.success(t('core.scripts.toast.okwwStarted', { name: script.name }))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动 ok-ww 设置失败: ${errorMsg}`)
    message.error(t('core.scripts.toast.okwwStartFailed', { error: errorMsg }))
  }
}

const handleSaveOkwwConfig = async (script: ScriptListItem) => {
  try {
    const saved = await stopConfigSession(script.id, 'ok-ww', clearConfigMask)
    if (saved) message.success(t('core.scripts.toast.okwwSaved', { name: script.name }))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 ok-ww 设置失败: ${errorMsg}`)
    message.error(t('core.scripts.toast.okwwSaveFailed', { error: errorMsg }))
  }
}

const handleToggleUserStatus = async (user: ScriptListUser) => {
  try {
    // 找到该用户对应的脚本
    const script = scripts.value.find(s => s.id === user.scriptId)
    if (!script) {
      message.error(t('core.scripts.toast.scriptNotFound'))
      return
    }
    const newStatus = !user.Info.Status

    // 后端是单字段 set：只发送 Status，避免 Info.Tag 等虚拟字段混入触发后端报错
    const result = await updateUser(script.id, user.id, {
      Info: { Status: newStatus },
    })

    if (result) {
      message.success(t('core.scripts.toast.userStatusUpdated'))
      // 更新本地用户状态
      user.Info.Status = newStatus
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新用户状态失败: ${errorMsg}`)
    message.error(t('core.scripts.toast.userStatusFailed', { error: errorMsg }))
  }
}
</script>

<style scoped>
.script-list-error {
  margin-bottom: 16px;
}

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

.scripts-loading,
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: calc(100vh - 200px);
  text-align: center;
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
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
