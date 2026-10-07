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
        <a-button v-if="configMaskUnknown" size="large" @click="handleQueryConfigMask">
          {{ t('resultUnknown.query') }}
        </a-button>
      </div>
      <!-- 终态未知：会话现场保留，明确告知这次写入是否生效还没确认 -->
      <p v-if="configMaskUnknown" class="mask-unknown-tip" role="alert">
        {{ t('resultUnknown.description') }}
      </p>
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
  isMfwFamily,
  type ScriptCreateRequest,
  type TemplateRequest,
} from '@/views/scripts/components/scriptCreateFlow'
import { maafwRouteLocation } from '@/router/maafwFlavorRoutes'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import { useWebSocket } from '@/composables/useWebSocket'
import { onTaskRuntimeEvent } from '@/composables/useTaskRuntimeState'
import {
  WS_TASK_COMPLETED,
  WS_TASK_CONFIG_DISCARDED,
  WS_TASK_NOTICE,
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
import { TaskOutcome } from '@/api/models/TaskOutcome'
import DocLink from '@/components/DocLink.vue'
import { showConfigDiscardWarning } from '@/utils/configSessionDiscard'
import { taskOutcomeNoticeKind } from '@/utils/taskOutcomeNotice'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { filterScriptsByKeyword } from '@/views/scripts/scriptSearch'

const { t } = useI18n()

defineOptions({ name: 'ScriptsPage' })

const logger = window.electronAPI.getLogger('脚本管理')

const router = useRouter()
const { addScript, deleteScript, getScriptsWithUsers } = useScriptApi()
const { updateUser, deleteUser } = useUserApi()
const { subscribe, unsubscribe } = useWebSocket()
const { getShareTemplates, importScriptFromTemplate, error: templateError } = useTemplateApi()
const { listEmbeddedSources, cloneEmbedded } = useMaaFWEmbeddedApi()

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
const templates = ref<ShareTemplateItem[]>([])
const templatePage = ref(1)
const templateTotal = ref(0)
let templateRequestId = 0
const addLoading = ref(false)
const copyingScriptId = ref<string | null>(null)
const templateLoading = ref(false)
// 新建 MFW 脚本第二步「复用已有脚本的项目」的候选：有健康副本的 MFW / M9A 脚本
const mfwSources = ref<MaaFWEmbeddedSourceItem[]>([])
const mfwSourcesLoading = ref(false)
const mfwSourcesError = ref<string | null>(null)

// 配置会话遮罩：同一时刻只会有一个配置会话在前台
type ConfigMaskKind = 'MAA' | 'SRC' | 'MaaEnd' | 'Okww' | 'Whimbox'
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
    case 'Whimbox':
      return {
        iconColor: 'var(--ant-color-primary)',
        title: t('scripts.mask.whimboxTitle'),
        description: t('scripts.mask.whimboxDesc'),
        tip: t('scripts.mask.whimboxUnlockTip'),
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
// 终态落库晚于完成帧：查不到就按间隔重试几次，仍查不到才算未知
const OUTCOME_QUERY_ATTEMPTS = 5
const OUTCOME_QUERY_RETRY_MS = 300

// 配置会话的连接记录（键为 scriptId/userId）
type ConfigSessionConnection = {
  subscriptionIds: string[]
  taskId: string
  /** 会话标签（MAA/SRC/MaaEnd/ok-ww/Whimbox）：只用于日志 */
  label: string
  /** 终态为 saved 时给用户看的成功文案：停止、完成帧、超时、查询四条路径共用一个口径 */
  savedMessage: string
  timeoutId?: ReturnType<typeof setTimeout>
  /** 后端下发的丢弃原因（structure/unreadable/not_written），改动未被丢弃为 null */
  discardedReason: string | null
  /** 丢弃提示是否已弹过：完成帧与停止响应都会走到会话结束，只提示一次 */
  discardWarned: boolean
  /** 终态判定中或已判定：阻止停止响应与完成帧对同一会话各判一次、各弹一次 */
  settling: boolean
  /** 已应用过的终态（taskId|finishedAt）：断线补发的重复终态帧只应用一次 */
  appliedStamp?: string
  /** 终态未知：会话现场保留，等用户点「查询状态」 */
  unknown: boolean
  /** 停止请求：重复点击复用同一个 promise，保证只发一个请求 */
  stopPromise?: Promise<void>
}

// WebSocket连接管理：scriptId/userId -> ConfigSessionConnection
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
    // MFW 家族新建后进各自类型的分步引导（同一个页面）；其余类型直接进编辑页
    ...(isMfwFamily(type)
      ? maafwRouteLocation(type, 'setup', { id: scriptId })
      : { path: `/scripts/${scriptId}/edit/${getScriptEditSegment(type)}` }),
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
    const type = request.kind === 'new' || request.kind === 'mfw-reuse' ? request.type : 'General'
    const result = await addScript(type)
    if (!result) return

    if (request.kind === 'mfw-reuse') {
      // 同一个项目再建一个脚本：从源脚本的副本克隆，秒级可用；类型随项目（M9A → M9A）。
      // 克隆失败脚本也已经建好了，照样进引导页让用户自己选目录。
      try {
        const { message: text } = await cloneEmbedded(result.scriptId, request.sourceScriptId)
        if (text) message.success(text)
      } catch (error) {
        const reason = error instanceof Error ? error.message : String(error)
        logger.error(`复用已有脚本的项目失败: ${reason}`)
        message.error(t('scripts.toast.reuseFailed', { reason }))
      }
      scriptCreateVisible.value = false
      navigateToCreatedScript(result.scriptId, type)
      return
    }

    if (request.kind === 'general-template') {
      const imported = await importScriptFromTemplate(result.scriptId, request.template)
      // 导入失败就把刚建出来的空脚本删掉，不给用户留一个没有配置的壳
      if (!imported) {
        await deleteScript(result.scriptId)
        await loadScripts()
        return
      }
      message.success(
        t('scripts.toast.createdFromTemplate', { name: request.template.displayName })
      )
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
    mfwSourcesError.value = t('scripts.toast.mfwSourcesFailed', { error: errorMsg })
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

const handleEditScript = (script: Script) => {
  router.push(
    isMfwFamily(script.type)
      ? maafwRouteLocation(script.type, 'script', { id: script.id })
      : `/scripts/${script.id}/edit/${getScriptEditPath(script.type)}`
  )
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

const handleEditUser = (user: User) => {
  // 从用户数据中找到对应的脚本
  const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
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

// 终态查询：完成帧先于终态落库发出，刚结束时可能还查不到，留几次重试窗口
const fetchTaskOutcome = async (taskId: string): Promise<TaskOutcome | null> => {
  for (let attempt = 0; attempt < OUTCOME_QUERY_ATTEMPTS; attempt += 1) {
    const status = await Service.getTaskStatusApiDispatchTaskTaskIdGet(taskId)
    if (status?.taskOutcome) return status.taskOutcome
    if (attempt < OUTCOME_QUERY_ATTEMPTS - 1) {
      await new Promise(resolve => setTimeout(resolve, OUTCOME_QUERY_RETRY_MS))
    }
  }
  return null
}

// 终态查不到：既不清理会话也不谎报成功，保留现场等用户自己查一次
const enterUnknownState = (targetId: string) => {
  const connection = activeConnections.value.get(targetId)
  if (!connection) return
  connection.unknown = true
  // 判定未落定：完成帧、丢弃帧或用户点「查询状态」都还能把结果改过来
  connection.settling = false
  connection.stopPromise = undefined
  void logger.warn(`配置会话终态未知，保留现场等待查询: taskId=${connection.taskId}`)
}

// 按终态收尾：HTTP 200 只说明停止请求被受理，写入是否生效要看 outcome
const applyTaskOutcome = (
  targetId: string,
  connection: ConfigSessionConnection,
  result: TaskOutcome,
  clearState: () => void
) => {
  // 断线补发会对同一终态重放，同一 taskId + finishedAt 只应用一次
  const stamp = `${result.taskId}|${result.finishedAt}`
  if (connection.appliedStamp === stamp) return
  connection.appliedStamp = stamp

  // 分类统一走 utils/taskOutcomeNotice，页面不再各写一套结果判断
  const kind = taskOutcomeNoticeKind(result)
  if (kind === 'unknown') {
    enterUnknownState(targetId)
    return
  }
  clearConfigSession(targetId, connection.subscriptionIds, clearState)
  if (kind === 'saved') {
    message.success(connection.savedMessage)
  } else if (kind === 'discarded') {
    if (!connection.discardWarned) {
      connection.discardWarned = true
      showConfigDiscardWarning(t, result.reason ?? connection.discardedReason ?? 'unknown')
    }
  } else if (kind === 'failed') {
    message.error(t('taskOutcome.failed'))
  } else if (kind === 'without_write') {
    message.info(t('taskOutcome.completedWithoutWrite'))
  }
  // cancelled / completed：这次会话没有写入语义，静默收尾，绝不提示「保存成功」
}

// 会话超时定时器挂在连接记录上，会话结束或页面卸载时一并清掉。
// 超时不直接清会话：先按编辑会话的语义自动结束一次，再以终态判定结果，判不出来就进未知。
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
    current.timeoutId = undefined
    onTimeout()
    void stopConfigSession(targetId, clearState)
  }, CONFIG_SESSION_TIMEOUT_MS)
}

const startConfigSession = async (
  targetId: string,
  label: string,
  setActiveState: () => void,
  clearState: () => void,
  savedMessage: string
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
  // 连接记录先建好：丢弃帧与完成帧都可能早于停止响应到达，两个回调都要读到同一份记录
  const connection: ConfigSessionConnection = {
    subscriptionIds: [],
    taskId: response.taskId,
    label,
    savedMessage,
    discardedReason: null,
    discardWarned: false,
    settling: false,
    unknown: false,
  }
  connection.subscriptionIds.push(
    subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
      const data = wsMessage.data as unknown as WSTaskNoticeData
      if (data.level === 'error') {
        message.error(t('scripts.toast.configFailed', { label, error: data.message }))
      }
    }),
    subscribe({ id: response.taskId, type: WS_TASK_CONFIG_DISCARDED }, wsMessage => {
      const data = wsMessage.data as unknown as WSTaskConfigDiscardedData
      connection.discardedReason = data.reason
      logger.info(`收到配置会话丢弃通知: reason=${data.reason}`)
      // 已经落到未知的会话：这个丢弃帧就是迟到的终态，直接改判，不用再让用户查一次
      if (connection.unknown) {
        applyTaskOutcome(
          targetId,
          connection,
          {
            taskId: connection.taskId,
            outcome: TaskOutcome.outcome.DISCARDED,
            reason: data.reason,
          },
          clearState
        )
      }
    }),
    subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
      sessionEnded = true
      // 完成帧只说明任务结束了：写入是否生效仍要以终态为准
      void settleConfigSession(targetId, clearState)
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

// 任务自己结束了（原生窗口被关掉等）：查终态收尾，查不到就进未知
const settleConfigSession = async (targetId: string, clearState: () => void) => {
  const connection = activeConnections.value.get(targetId)
  if (!connection || connection.settling) return
  connection.settling = true
  await new Promise(resolve => setTimeout(resolve, DISCARD_FRAME_GRACE_MS))
  try {
    const result = await fetchTaskOutcome(connection.taskId)
    if (result) applyTaskOutcome(targetId, connection, result, clearState)
    else enterUnknownState(targetId)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`查询配置会话终态失败: ${errorMsg}`)
    enterUnknownState(targetId)
  }
}

// 结束会话并落定结果：重复点击复用同一个请求，只有第一次真的发出去
const stopConfigSession = (targetId: string, clearState: () => void): Promise<void> => {
  const connection = activeConnections.value.get(targetId)
  if (!connection) {
    message.error(t('scripts.toast.noSession'))
    return Promise.resolve()
  }
  if (connection.stopPromise) return connection.stopPromise
  connection.stopPromise = (async () => {
    if (connection.settling) return
    // 停止请求在途时完成帧也可能到达：由这里统一落定，避免同一会话弹两次结果
    connection.settling = true
    try {
      const response = await Service.stopTaskApiDispatchStopPost({
        taskId: connection.taskId,
      })
      if (response.code !== 200) {
        logger.error(
          `结束${connection.label}配置会话失败: code=${response.code} ${response.message}`
        )
        enterUnknownState(targetId)
        return
      }
      // 丢弃帧先于停止响应写出，但到达顺序不保证，等一个回合再按响应里的终态判定
      await new Promise(resolve => setTimeout(resolve, DISCARD_FRAME_GRACE_MS))
      applyTaskOutcome(targetId, connection, response, clearState)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`结束${connection.label}配置会话失败: ${errorMsg}`)
      enterUnknownState(targetId)
    }
  })()
  return connection.stopPromise
}

// 遮罩对应的会话目标：MaaEnd 用户级会话用 userId，其余用 scriptId
const configMaskTargetId = computed(() => {
  const mask = configMask.value
  if (!mask) return null
  return mask.user?.id ?? mask.script.id
})

// 当前会话结果未知：遮罩保留现场，并给出一次「查询状态」动作
const configMaskUnknown = computed(() => {
  const targetId = configMaskTargetId.value
  if (!targetId) return false
  return activeConnections.value.get(targetId)?.unknown === true
})

// 会话进入未知后的唯一出路：查一次终态，查到就按终态收尾
const queryConfigSession = async (targetId: string, clearState: () => void) => {
  const connection = activeConnections.value.get(targetId)
  if (!connection || connection.settling) return
  connection.settling = true
  try {
    const result = await fetchTaskOutcome(connection.taskId)
    if (result) applyTaskOutcome(targetId, connection, result, clearState)
    else enterUnknownState(targetId)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`查询配置会话终态失败: ${errorMsg}`)
    enterUnknownState(targetId)
  }
}

const handleQueryConfigMask = () => {
  const targetId = configMaskTargetId.value
  if (!targetId) return
  void queryConfigSession(targetId, clearConfigMask)
}

// 脚本级配置会话（MAA / SRC / Whimbox）：走通用的 start/stop，带 sessionEnded 竞态守卫
const handleStartScriptConfig = async (script: Script, kind: 'MAA' | 'SRC' | 'Whimbox') => {
  try {
    const started = await startConfigSession(
      script.id,
      kind,
      () => {
        configMask.value = { kind, script, user: null }
      },
      clearConfigMask,
      // 终态为 saved 时统一由会话收尾弹这一条，避免停止、完成帧、超时各弹一次
      t('scripts.toast.configSaved', { name: script.name })
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

// 保存即结束会话：结果提示由终态决定（saved/discarded/failed/unknown 各不相同）
const handleStartMAAConfig = (script: Script) => handleStartScriptConfig(script, 'MAA')
const handleSaveMAAConfig = (script: Script) => stopConfigSession(script.id, clearConfigMask)
const handleStartSRCConfig = (script: Script) => handleStartScriptConfig(script, 'SRC')
const handleSaveSRCConfig = (script: Script) => stopConfigSession(script.id, clearConfigMask)
// 奇想盒：无参数拉起原生 app（下载跑图路线、配置模型/键位等都在那边做，MAS 零写入）
const handleStartWhimboxConfig = (script: Script) => handleStartScriptConfig(script, 'Whimbox')
const handleSaveWhimboxConfig = (script: Script) => stopConfigSession(script.id, clearConfigMask)

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
      clearConfigMask,
      user
        ? t('scripts.toast.maaEndUserSaved', { script: script.name, user: user.Info.Name })
        : t('scripts.toast.configSaved', { name: script.name })
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

const handleSaveMaaEndConfig = (script: Script) => {
  const currentUser = configMask.value?.kind === 'MaaEnd' ? configMask.value.user : null
  const targetId = currentUser?.id ?? script.id
  return stopConfigSession(targetId, clearConfigMask)
}

const handleStartOkwwConfig = async (script: Script) => {
  try {
    const started = await startConfigSession(
      script.id,
      'ok-ww',
      () => {
        configMask.value = { kind: 'Okww', script, user: null }
      },
      clearConfigMask,
      t('scripts.toast.okwwSaved', { name: script.name })
    )
    if (started) message.success(t('scripts.toast.okwwStarted', { name: script.name }))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动 ok-ww 设置失败: ${errorMsg}`)
    message.error(t('scripts.toast.okwwStartFailed', { error: errorMsg }))
  }
}

const handleSaveOkwwConfig = (script: Script) => stopConfigSession(script.id, clearConfigMask)

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
  gap: 12px;
}

.mask-unknown-tip {
  font-size: 13px;
  color: var(--ant-color-warning-text, var(--ant-color-warning));
  margin: 16px 0 0;
  line-height: 1.5;
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
