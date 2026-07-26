<template>
  <div class="scripts-page">
    <PageHeader
      class="scripts-page-header"
      title="脚本管理"
      subtitle="管理脚本、用户与运行配置"
      compact
      transparent
    >
      <StatePanel type="neutral" :title="scriptSummary" compact />
    </PageHeader>

    <Toolbar class="scripts-toolbar" position="both" aria-label="脚本管理工具栏">
      <template #trailing>
        <!-- 行内横向展开的搜索框(mac Spotlight/Safari 风格):锚点在右,与工具栏同行向左展开,不推挤右侧按钮 -->
        <Transition name="script-search-expand">
          <div v-if="scriptSearchOpen" class="script-search-inline">
            <ScriptSearchBar
              ref="scriptSearchBarRef"
              v-model="scriptSearchKeyword"
              :summary="scriptSearchSummary"
              :match-count="scriptSearchMatches.length"
              @clear="clearScriptSearch"
              @close="closeScriptSearch"
              @navigate="navigateScriptSearchMatch"
            />
          </div>
        </Transition>
        <a-button
          aria-label="搜索脚本"
          title="搜索"
          :aria-expanded="scriptSearchOpen ? 'true' : 'false'"
          @click="openScriptSearch"
        >
          <template #icon>
            <SearchOutlined />
          </template>
        </a-button>
        <a-tooltip title="收起所有脚本的用户列表">
          <a-button
            :disabled="scripts.length === 0 || hasScriptSearchQuery"
            @click="handleCollapseAll"
          >
            <template #icon>
              <UpOutlined />
            </template>
            一键收起
          </a-button>
        </a-tooltip>
        <a-tooltip title="展开所有脚本的用户列表">
          <a-button
            :disabled="scripts.length === 0 || hasScriptSearchQuery"
            @click="handleExpandAll"
          >
            <template #icon>
              <DownOutlined />
            </template>
            一键展开
          </a-button>
        </a-tooltip>
        <a-button
          type="primary"
          class="link"
          :disabled="availableScriptTypes.length === 0"
          @click="handleAddScript"
        >
          <template #icon>
            <PlusOutlined />
          </template>
          新建脚本
        </a-button>
      </template>
    </Toolbar>

    <main class="scripts-content">
      <LoadingSkeleton
        v-if="!loadedOnce && !scriptListError && addLoading === false"
        class="script-list-loading"
        variant="list"
        :rows="5"
      />

      <StatePanel
        v-else-if="scriptListError"
        class="script-list-error"
        type="error"
        title="脚本列表加载失败"
      >
        <p class="state-description">{{ scriptListError }}</p>
        <template #actions>
          <a-button type="primary" size="small" @click="loadScripts">
            <template #icon>
              <ReloadOutlined />
            </template>
            重试
          </a-button>
        </template>
      </StatePanel>

      <StatePanel
        v-else-if="!addLoading && loadedOnce && scripts.length === 0"
        class="script-list-empty"
        type="neutral"
        title="暂无脚本"
      >
        <p class="state-description">创建第一个脚本后，即可添加用户并配置运行方式。</p>
        <template #actions>
          <a-button
            type="primary"
            size="small"
            :disabled="availableScriptTypes.length === 0"
            @click="handleAddScript"
          >
            新建脚本
          </a-button>
        </template>
      </StatePanel>

      <StatePanel
        v-else-if="hasNoScriptSearchResults"
        class="script-search-empty"
        type="neutral"
        title="未找到匹配的脚本或用户"
      >
        <p class="state-description">请调整关键词，或清除搜索查看全部脚本。</p>
        <template #actions>
          <a-button type="primary" ghost size="small" @click="clearScriptSearch">
            清除搜索
          </a-button>
        </template>
      </StatePanel>

      <ScriptSplitView
        v-else-if="loadedOnce && (filteredScripts.length > 0 || addLoading)"
        ref="scriptTableRef"
        :scripts="filteredScripts"
        :search-keyword="scriptSearchKeyword"
        :active-search-match-key="activeScriptSearchMatchKey"
        :active-connections="configSession.state.activeConnections"
        :copying-script-id="copyingScriptId"
        :all-plans-data="allPlansData"
        @edit="handleEditScript"
        @copy="handleCopyScript"
        @delete="handleDeleteScript"
        @add-user="handleAddUser"
        @edit-user="handleEditUser"
        @delete-user="handleDeleteUser"
        @start-src-config="handleStartSRCConfig"
        @start-maa-end-config="handleStartMaaEndConfig"
        @toggle-user-status="handleToggleUserStatus"
        @pass-check-user="handlePassCheckUser"
        @scripts-reordered="handleScriptsReordered"
      />
    </main>

    <ScriptConfigMask
      :visible="configSession.state.currentScript !== null"
      :script="configSession.state.currentScript"
      :kind="configSession.state.currentKind"
      :saving="false"
      @save="handleSaveConfig"
    />

    <ScriptCreateDialog
      v-model:open="scriptCreateVisible"
      :templates="templates"
      :submitting="addLoading || templateLoading"
      :template-loading="templateLoading"
      :template-error="templateError"
      :type-options="scriptCreateTypeOptions"
      @request-templates="loadTemplates"
      @submit="handleSubmitScriptCreate"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  DownOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  UpOutlined,
} from '@ant-design/icons-vue'
import PageHeader from '@/components/mac/PageHeader.vue'
import StatePanel from '@/components/mac/StatePanel.vue'
import Toolbar from '@/components/mac/Toolbar.vue'
import LoadingSkeleton from '@/components/v6/LoadingSkeleton.vue'
import ScriptSplitView from '@/views/scripts/components/ScriptSplitView.vue'
import ScriptCreateDialog from '@/views/scripts/components/ScriptCreateDialog.vue'
import ScriptSearchBar from '@/views/scripts/components/ScriptSearchBar.vue'
import ScriptConfigMask from '@/views/scripts/components/ScriptConfigMask.vue'
import { useScriptConfigSession } from '@/views/scripts/composables/useScriptConfigSession'
import type { Script, User } from '@/types/script'
import type { ScriptTypeDescriptor } from '@/types/scriptRegistry'
import {
  createScriptTypeOptions,
  type ScriptCreateRequest,
} from '@/views/scripts/components/scriptCreateFlow'
import {
  buildScriptSearchResult,
  createScriptSearchFocusManager,
  createScriptSearchKeyboardController,
  getAdjacentSearchMatchKey,
  reconcileActiveSearchMatchKey,
} from '@/views/scripts/scriptPageSearch'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import { useWebSocket } from '@/composables/useWebSocket'
import { useTemplateApi } from '@/composables/useTemplateApi'
import { usePlanApi } from '@/composables/usePlanApi'
import type { PlanGetOut } from '@/api'
import {
  getScriptEditPath,
  getUserCreatePath,
  getUserEditPath,
  normalizeScriptRecord,
  descriptorMapFromList,
} from '@/utils/scriptRegistry'
const logger = window.electronAPI.getLogger('脚本管理')

const router = useRouter()
const route = useRoute()
const registryApi = useScriptRegistryApi()
const { subscribe, unsubscribe } = useWebSocket()
const { getWebConfigTemplates, importScriptFromWeb, error: templateError } = useTemplateApi()
const { getPlans } = usePlanApi()

const scripts = ref<Script[]>([])
const scriptTableRef = ref<InstanceType<typeof ScriptSplitView> | null>(null)
const scriptSearchBarRef = ref<InstanceType<typeof ScriptSearchBar> | null>(null)
const scriptSearchOpen = ref(false)
const scriptSearchKeyword = ref('')
const activeScriptSearchMatchKey = ref('')
const scriptTypeDescriptors = ref<ScriptTypeDescriptor[]>([])
const scriptListError = ref<string | null>(null)

// 增加：标记是否已经完成过一次脚本列表加载（成功或失败都算一次）
const loadedOnce = ref(false)
// 所有计划表数据 (planId -> planData)
const allPlansData = ref<Record<string, Record<string, any>>>({})
const scriptCreateVisible = ref(false)
const copyingScriptId = ref<string | null>(null)
const templates = ref<Awaited<ReturnType<typeof getWebConfigTemplates>>>([])
const addLoading = ref(false)
const templateLoading = ref(false)

// SRC / MaaEnd 配置会话（mask、WS 订阅、30 分钟超时、错误回滚）
const configSession = useScriptConfigSession({
  ensureAvailable: ensureScriptAvailable,
})

let pluginSystemSubscriptionId: string | null = null

const hasScriptSearchQuery = computed(() => scriptSearchKeyword.value.trim().length > 0)
const scriptSearchResult = computed(() =>
  buildScriptSearchResult(scripts.value, scriptSearchKeyword.value)
)
const filteredScripts = computed(() => {
  // 搜索激活时跨全部脚本检索（保留 Ctrl+F 全局搜索能力）
  if (hasScriptSearchQuery.value) {
    return scriptSearchResult.value.scripts
  }
  return scripts.value
})
const scriptSearchMatches = computed(() => scriptSearchResult.value.matches)
const activeScriptSearchMatchIndex = computed(() =>
  scriptSearchMatches.value.findIndex(match => match.key === activeScriptSearchMatchKey.value)
)
const activeScriptSearchMatchPosition = computed(() =>
  scriptSearchMatches.value.length === 0 ? 0 : Math.max(activeScriptSearchMatchIndex.value, 0) + 1
)
const hasNoScriptSearchResults = computed(
  () =>
    !scriptListError.value &&
    loadedOnce.value &&
    scripts.value.length > 0 &&
    hasScriptSearchQuery.value &&
    filteredScripts.value.length === 0
)

const scriptSearchSummary = computed(() =>
  hasScriptSearchQuery.value
    ? scriptSearchMatches.value.length > 0
      ? `${activeScriptSearchMatchPosition.value} / ${scriptSearchMatches.value.length} 个匹配项 · ${filteredScripts.value.length} 个脚本`
      : '0 个匹配项'
    : `共 ${scripts.value.length} 个脚本`
)
const scriptSummary = computed(() => {
  if (!loadedOnce.value) return '正在加载脚本'
  const userCount = scripts.value.reduce((total, script) => total + script.users.length, 0)
  return `${scripts.value.length} 个脚本 · ${userCount} 位用户`
})

watch(
  scriptSearchMatches,
  async matches => {
    const previousKey = activeScriptSearchMatchKey.value
    const nextKey = reconcileActiveSearchMatchKey(matches, previousKey)
    activeScriptSearchMatchKey.value = nextKey
    if (!nextKey || nextKey === previousKey) return
    await nextTick()
    scriptTableRef.value?.scrollToSearchMatch(nextKey)
  },
  { flush: 'post' }
)

const availableScriptTypes = computed(() => scriptTypeDescriptors.value)
const scriptCreateTypeOptions = computed(() => createScriptTypeOptions(availableScriptTypes.value))

const isScriptAvailable = (script: Script) => script.available !== false

const canEditScript = (script: Script) => script.providerAvailable ?? isScriptAvailable(script)

function ensureScriptAvailable(script: Script): boolean {
  if (isScriptAvailable(script)) {
    return true
  }
  message.warning(script.unavailableReason || `脚本类型 ${script.type} 当前未启用，暂时不能操作`)
  return false
}

const focusScriptSearchInput = async () => {
  await nextTick()
  scriptSearchBarRef.value?.focus()
}

const scriptSearchFocusManager = createScriptSearchFocusManager()

const openScriptSearch = async () => {
  if (!scriptSearchOpen.value) scriptSearchFocusManager.capture(document.activeElement)
  scriptSearchOpen.value = true
  await focusScriptSearchInput()
}

const clearScriptSearch = () => {
  scriptSearchKeyword.value = ''
  activeScriptSearchMatchKey.value = ''
  void focusScriptSearchInput()
}

const closeScriptSearch = async () => {
  scriptSearchOpen.value = false
  scriptSearchKeyword.value = ''
  activeScriptSearchMatchKey.value = ''
  await nextTick()
  scriptSearchFocusManager.restore()
}

const navigateScriptSearchMatch = async (direction: 1 | -1) => {
  const nextKey = getAdjacentSearchMatchKey(
    scriptSearchMatches.value,
    activeScriptSearchMatchKey.value,
    direction
  )
  if (!nextKey) return
  activeScriptSearchMatchKey.value = nextKey
  await nextTick()
  scriptTableRef.value?.scrollToSearchMatch(nextKey)
}

const scriptSearchKeyboardController = createScriptSearchKeyboardController({
  isActive: () => route.name === 'Scripts' || route.path === '/scripts',
  isOpen: () => scriptSearchOpen.value,
  open: openScriptSearch,
  close: closeScriptSearch,
})
let unbindScriptSearchKeyboard: (() => void) | null = null

onMounted(() => {
  unbindScriptSearchKeyboard = scriptSearchKeyboardController.bind(window)
  pluginSystemSubscriptionId = subscribe({ id: 'PluginSystem' }, message => {
    const payload = message.data as { kind?: string } | undefined
    if (payload?.kind === 'snapshot') void loadScripts()
  })
  loadScripts()
  loadCurrentPlan()
})

onUnmounted(() => {
  unbindScriptSearchKeyboard?.()
  unbindScriptSearchKeyboard = null
  scriptSearchFocusManager.clear()
  if (pluginSystemSubscriptionId) unsubscribe(pluginSystemSubscriptionId)
})

const loadScripts = async () => {
  try {
    scriptListError.value = null
    const descriptors = await registryApi.getScriptTypes()
    scriptTypeDescriptors.value = descriptors
    const descriptorMap = descriptorMapFromList(descriptors)
    const scriptRecords = await registryApi.getScripts()
    const userRecords = await Promise.all(
      scriptRecords.map(record => registryApi.getUsers(record.id))
    )

    scripts.value = scriptRecords.map((record, index) =>
      normalizeScriptRecord(record, descriptorMap, userRecords[index] || [])
    )
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    scriptListError.value = errorMsg
    logger.error(`加载脚本列表失败: ${errorMsg}`)
    message.error(`加载脚本列表失败: ${errorMsg}`)
  } finally {
    // 首次加载结束（不论成功失败）后置位，避免初始闪烁
    loadedOnce.value = true
  }
}

// 加载所有计划表数据
const loadCurrentPlan = async () => {
  try {
    const response = (await getPlans()) as unknown as PlanGetOut
    if (response.data) {
      // 加载所有计划表数据
      allPlansData.value = response.data
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载计划表数据失败: ${errorMsg}`)
    // 不显示错误消息，因为计划表数据是可选的
  }
}

const handleCollapseAll = () => {
  scriptTableRef.value?.collapseAllUsers()
}

const handleExpandAll = () => {
  scriptTableRef.value?.expandAllUsers()
}

const handleScriptsReordered = (orderedScripts: Script[]) => {
  // ScriptTable 已在后端确认持久化；同步父层唯一真值，避免后续搜索/刷新
  // 重新计算 filteredScripts 时把成功的 DOM 顺序恢复成旧 props 顺序。
  scripts.value = [...orderedScripts]
}

const handleAddScript = () => {
  scriptCreateVisible.value = true
}

const navigateToCreatedScript = (result: { id: string; type: string; editor_kind: string }) => {
  if (result.type === 'MaaFW' || result.type === 'M9A') {
    router.push(`/scripts/${result.id}/setup/maafw`)
    return
  }
  router.push(
    getScriptEditPath({ id: result.id, type: result.type, editorKind: result.editor_kind })
  )
}

const handleSubmitScriptCreate = async (request: ScriptCreateRequest) => {
  addLoading.value = true
  try {
    const result = await registryApi.addScript(request.kind === 'new' ? request.type : 'General')

    if (request.kind === 'general-template') {
      const imported = await importScriptFromWeb(result.id, request.template.downloadUrl)
      if (!imported) return
      message.success(`已根据模板「${request.template.configName}」创建脚本`)
    }

    scriptCreateVisible.value = false
    navigateToCreatedScript(result)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`添加脚本失败: ${errorMsg}`)
    message.error(`添加脚本失败: ${errorMsg}`)
  } finally {
    addLoading.value = false
  }
}

const handleCopyScript = async (script: Script) => {
  if (!ensureScriptAvailable(script)) return

  addLoading.value = true
  copyingScriptId.value = script.id
  try {
    await registryApi.addScript(script.type, script.id)
    await loadScripts()
    message.success(`已复制脚本「${script.name}」`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`复制脚本失败: ${errorMsg}`)
    message.error(`复制脚本失败: ${errorMsg}`)
  } finally {
    addLoading.value = false
    copyingScriptId.value = null
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
  if (!canEditScript(script)) {
    ensureScriptAvailable(script)
    return
  }
  router.push(getScriptEditPath(script))
}

const handleDeleteScript = async (script: Script) => {
  try {
    await registryApi.deleteScript(script.id)
    await loadScripts()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`删除脚本失败: ${errorMsg}`)
  }
}

const handleAddUser = (script: Script) => {
  if (!ensureScriptAvailable(script)) {
    return
  }
  router.push(getUserCreatePath(script))
}

const handleEditUser = (user: User) => {
  // 从用户数据中找到对应的脚本
  const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
  if (script) {
    if (!ensureScriptAvailable(script)) {
      return
    }
    router.push(getUserEditPath(script, user))
  } else {
    message.error('找不到对应的脚本')
  }
}

const handleDeleteUser = async (user: User) => {
  // 从用户数据中找到对应的脚本
  const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
  if (!script) {
    message.error('找不到对应的脚本')
    return
  }
  if (!ensureScriptAvailable(script)) {
    return
  }

  try {
    await registryApi.deleteUser(script.id, user.id)
    const userIndex = script.users.findIndex(u => u.id === user.id)
    if (userIndex > -1) {
      script.users.splice(userIndex, 1)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`删除用户失败: ${errorMsg}`)
  }
}

const handleStartSRCConfig = (script: Script) => {
  void configSession.startSession(script, 'SRC')
}

const handleStartMaaEndConfig = (script: Script) => {
  void configSession.startSession(script, 'MaaEnd')
}

// ScriptConfigMask 的保存按钮统一入口
const handleSaveConfig = (script: Script) => {
  void configSession.saveSession(script)
}

const handleToggleUserStatus = async (user: User) => {
  try {
    // 找到该用户对应的脚本
    const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
    if (!script) {
      message.error('找不到对应的脚本')
      return
    }
    if (!ensureScriptAvailable(script)) {
      return
    }
    const newStatus = !user.Info.Status

    // 调用 updateUser API
    await registryApi.updateUser(script.id, user.id, {
      Info: {
        Status: newStatus,
      },
    })
    message.success('用户状态更新成功')
    user.Info.Status = newStatus
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新用户状态失败: ${errorMsg}`)
    message.error(`更新用户状态失败: ${errorMsg}`)
  }
}

const handlePassCheckUser = async (user: User) => {
  try {
    // 找到该用户对应的脚本
    const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
    if (!script) {
      message.error('找不到对应的脚本')
      return
    }
    if (!ensureScriptAvailable(script)) {
      return
    }

    // 调用 updateUser API，更新 Data.IfPassCheck 为 true
    await registryApi.updateUser(script.id, user.id, {
      Data: {
        IfPassCheck: true,
      },
    })
    message.success('已标记为「通过人工排查」')
    await loadScripts()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新人工排查状态失败: ${errorMsg}`)
    message.error(`更新人工排查状态失败: ${errorMsg}`)
  }
}
</script>

<style scoped>
.scripts-page {
  display: flex;
  flex-direction: column;
  min-width: 0;
  container: scripts-page / inline-size;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--v6-color-window);
  color: var(--v6-color-text);
}

.scripts-page-header,
.scripts-toolbar {
  flex-shrink: 0;
}

/* 允许 trailing 槽随行内搜索框伸缩,避免窄容器时工具栏横向溢出(仅本页实例覆盖);
   槽内保持右对齐,搜索框展开时向左伸出而非推挤右侧按钮 */
.scripts-toolbar :deep(.mac-toolbar__trailing) {
  flex: 0 1 auto;
  min-width: 0;
  justify-content: flex-end;
}

/* 行内搜索框容器:与工具栏按钮同行,锚点在右向左展开,宽度随页面容器收敛 */
.script-search-inline {
  display: flex;
  align-items: center;
  min-width: 0;
  width: min(520px, 52cqw);
  max-width: 100%;
}

/* 横向展开/收起动画:max-width 0 <-> 展开宽度(置于基础规则之后确保动画期间生效) */
.script-search-expand-enter-active,
.script-search-expand-leave-active {
  overflow: hidden;
  transition:
    max-width var(--v6-motion-base) var(--v6-ease-out),
    opacity var(--v6-motion-base) var(--v6-ease-out);
}

.script-search-expand-enter-from,
.script-search-expand-leave-to {
  max-width: 0;
  opacity: 0;
}

.script-search-expand-enter-to,
.script-search-expand-leave-from {
  max-width: min(520px, 52cqw);
  opacity: 1;
}

.link {
  display: inline-flex;
  align-items: center;
}

.link .anticon {
  margin-right: var(--v6-space-1);
}

.scripts-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: var(--v6-space-5) var(--v6-content-padding-inline)
    calc(var(--v6-space-8) + var(--v6-space-2));
}

.scripts-content > :deep(.script-split-view) {
  flex: 1;
  min-height: 0;
}

.script-list-loading {
  min-height: 320px;
}

.state-description {
  margin: 0;
  color: var(--v6-color-text-secondary);
  line-height: var(--v6-line-height-normal);
}

@container scripts-page (max-width: 900px) {
  .scripts-content {
    padding-inline: var(--v6-space-4);
  }

  .script-search-inline {
    width: min(380px, 60cqw);
  }
}

@media (prefers-reduced-motion: reduce) {
  .script-search-expand-enter-active,
  .script-search-expand-leave-active {
    transition: none;
  }
}
</style>
