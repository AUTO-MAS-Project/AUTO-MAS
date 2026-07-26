<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useEventListener } from '@vueuse/core'
import type { ToolsConfig } from '@/api'
import { Service } from '@/api'
import { useToolsApi } from '@/composables/useToolsApi'
import { useStatusTag, createStatusTag } from '@/composables/useStatusTag'
import TabArknightsPC from './TabArknightsPC.vue'
import TabGameSign from './TabGameSign.vue'
import PageHeader from '@/components/mac/PageHeader.vue'
const logger = window.electronAPI.getLogger('工具')

const { loading, getTools, updateTools } = useToolsApi()

// 活动标签
const activeKey = ref('arknightspc')

// 工具数据
const toolsConfig = reactive<ToolsConfig>({
  ArknightsPC: {
    Enabled: false,
    PauseKey: 'f10',
    SelectDeployedKey: 'w',
    UseSkillKey: 'r',
    RetreatKey: 't',
    NextFrameKey: 'f',
    AnotherQuitKey: 'space',
    Status: '-',
  },
  GameSign: {
    Enabled: false,
    NotifyEnabled: false,
    WindowStart: '08:00',
    WindowEnd: '22:00',
    LastSignDate: '2000-01-01',
    ScheduledTime: '',
    Status: '-',
    Result: '{}',
  },
})

// 本地编辑状态
const editingConfig = reactive<ToolsConfig>({
  ArknightsPC: {
    Enabled: false,
    PauseKey: 'f10',
    SelectDeployedKey: 'w',
    UseSkillKey: 'r',
    RetreatKey: 't',
    NextFrameKey: 'f',
    AnotherQuitKey: 'space',
    Status: '-',
  },
  GameSign: {
    Enabled: false,
    NotifyEnabled: false,
    WindowStart: '08:00',
    WindowEnd: '22:00',
    LastSignDate: '2000-01-01',
    ScheduledTime: '',
    Status: '-',
    Result: '{}',
  },
})

// 使用通用的状态标签解析
const arknightsPCStatusTag = useStatusTag(
  () => toolsConfig.ArknightsPC?.Status,
  createStatusTag('未启用', 'default')
)

const gameSignStatusTag = useStatusTag(
  () => toolsConfig.GameSign?.Status,
  createStatusTag('未启用', 'default')
)

const toolTabOptions = [
  { label: '明日方舟 PC', value: 'arknightspc' },
  { label: '游戏社区签到', value: 'gamesign' },
]

const activeStatusTag = computed(() =>
  activeKey.value === 'gamesign' ? gameSignStatusTag.value : arknightsPCStatusTag.value
)

// 轮询定时器
let pollTimer: NodeJS.Timeout | null = null

// 卸载守卫：组件卸载后阻止异步回调写入响应式状态
let isMounted = true

// 仅更新状态（不影响编辑状态，不触发 loading）
const updateStatus = async () => {
  // 如果下拉框正在打开，跳过更新避免干扰用户操作
  if (isSelectOpen.value) {
    return
  }
  try {
    // 直接调用 Service 而非 getTools()，避免 loading 状态切换导致组件重渲染闪烁
    const response = await Service.getToolsApiToolsGetPost()
    // 组件可能在 await 期间已卸载，此时不再写入响应式状态
    if (!isMounted) return
    if (response.code !== 200 || !response.data) return
    const data = response.data
    if (data.ArknightsPC?.Status) {
      // 只更新 toolsConfig 的状态，不更新 editingConfig
      // 这样轮询只影响状态标签显示，不会触发编辑表单重新渲染
      toolsConfig.ArknightsPC!.Status = data.ArknightsPC.Status
    }
    if (data.GameSign?.Status) {
      toolsConfig.GameSign!.Status = data.GameSign.Status
    }
    if (data.GameSign?.Result) {
      toolsConfig.GameSign!.Result = data.GameSign.Result
      // 同步签到结果到编辑状态，否则展示组件读到的是初始空值
      editingConfig.GameSign!.Result = data.GameSign.Result
    }
  } catch {
    // 静默失败，不影响用户操作
  }
}

// 签到完成后立即刷新配置（不等轮询）
const refreshGameSignConfig = async () => {
  try {
    const response = await Service.getToolsApiToolsGetPost()
    if (!isMounted) return
    if (response.code !== 200 || !response.data) return
    const data = response.data
    if (data.GameSign?.Status) {
      toolsConfig.GameSign!.Status = data.GameSign.Status
    }
    if (data.GameSign?.Result) {
      toolsConfig.GameSign!.Result = data.GameSign.Result
      editingConfig.GameSign!.Result = data.GameSign.Result
    }
  } catch {
    // 静默失败
  }
}

// 启动状态轮询
const startStatusPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
  }
  pollTimer = setInterval(() => {
    updateStatus()
  }, 1000) // 每秒更新一次
}

// 停止状态轮询
const stopStatusPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 加载配置
const loadTools = async () => {
  try {
    const data = await getTools()
    // 确保 ArknightsPC 配置存在
    if (!data.ArknightsPC) {
      data.ArknightsPC = {
        Enabled: false,
        PauseKey: 'f10',
        SelectDeployedKey: 'w',
        UseSkillKey: 'r',
        RetreatKey: 't',
        NextFrameKey: 'f',
        AnotherQuitKey: 'space',
        Status: '-',
      }
    }
    // 确保 GameSign 配置存在
    if (!data.GameSign) {
      data.GameSign = {
        Enabled: false,
        NotifyEnabled: false,
        WindowStart: '08:00',
        WindowEnd: '22:00',
        LastSignDate: '2000-01-01',
        ScheduledTime: '',
        Status: '-',
        Result: '{}',
      }
    }
    Object.assign(toolsConfig, data)
    Object.assign(editingConfig, JSON.parse(JSON.stringify(data)))
    logger.info('工具加载完成')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载工具失败: ${errorMsg}`)
  }
}

// 保存单个字段的变更（实时保存）
const handleFieldChange = async (key: string, value: any) => {
  if (!editingConfig.ArknightsPC) return

  // 保存旧值，API 失败时回滚编辑态，避免 UI 显示与后端不一致
  const oldValue = (editingConfig.ArknightsPC as any)[key]
  try {
    // 更新编辑状态
    ;(editingConfig.ArknightsPC as any)[key] = value

    // 立即保存到后端
    await updateTools(editingConfig)

    // 保存成功后只同步修改的字段到 toolsConfig，不触碰 Status
    if (toolsConfig.ArknightsPC && key !== 'Status') {
      ;(toolsConfig.ArknightsPC as any)[key] = value
    }

    logger.info(`${key} 已保存`)
  } catch (error) {
    // 回滚编辑态到旧值
    ;(editingConfig.ArknightsPC as any)[key] = oldValue
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 ${key} 失败: ${errorMsg}`)
  }
}

// 保存 GameSign 字段的变更
const handleGameSignFieldChange = async (key: string, value: any) => {
  if (!editingConfig.GameSign) return

  const oldValue = (editingConfig.GameSign as any)[key]
  try {
    ;(editingConfig.GameSign as any)[key] = value
    await updateTools(editingConfig)

    if (toolsConfig.GameSign && key !== 'Status' && key !== 'Result') {
      ;(toolsConfig.GameSign as any)[key] = value
    }

    logger.info(`GameSign.${key} 已保存`)
  } catch (error) {
    ;(editingConfig.GameSign as any)[key] = oldValue
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 GameSign.${key} 失败: ${errorMsg}`)
  }
}

// 键位录制状态
const recordingKeyField = ref<string | null>(null)

// 下拉框打开状态
const isSelectOpen = ref<boolean>(false)

// 处理下拉框可见性变化
const handleSelectVisibleChange = (visible: boolean) => {
  isSelectOpen.value = visible
  if (visible) {
    logger.debug('下拉框打开，暂停轮询')
  } else {
    logger.debug('下拉框关闭，恢复轮询')
  }
}

// 开始录制键位
const startRecordKey = (fieldName: string) => {
  recordingKeyField.value = fieldName
  logger.info(`开始录制键位: ${fieldName}`)
}

// 停止录制键位
const stopRecordKey = () => {
  recordingKeyField.value = null
}

// 键盘事件处理 - 捕获单个键
const handleKeyDown = async (event: KeyboardEvent) => {
  if (!recordingKeyField.value) return

  event.preventDefault()
  event.stopPropagation()

  // 获取按键名称
  let keyName: string

  // 特殊键处理
  if (event.key === ' ') {
    keyName = 'space'
  } else if (event.key.length === 1) {
    // 单字符键，转为小写
    keyName = event.key.toLowerCase()
  } else {
    // 功能键（如 F1-F12, Escape, Enter 等）
    keyName = event.key.toLowerCase()
  }

  const fieldName = recordingKeyField.value

  // 停止录制
  stopRecordKey()

  // 立即保存
  await handleFieldChange(fieldName, keyName)
}

// 使用 VueUse 的 useEventListener 管理键盘事件
useEventListener(document, 'keydown', handleKeyDown)

// 生命周期：加载配置并启动轮询
onMounted(async () => {
  await loadTools()
  startStatusPolling()
})

// 生命周期：停止轮询，标记组件已卸载
onUnmounted(() => {
  isMounted = false
  stopStatusPolling()
})
</script>

<template>
  <div class="tools-page">
    <PageHeader title="工具" subtitle="管理辅助工具、快捷键和游戏社区签到" compact transparent />

    <div class="tools-navigation">
      <a-segmented v-model:value="activeKey" :options="toolTabOptions" block />
      <a-tag
        v-if="activeStatusTag"
        :color="activeStatusTag.color"
        class="tool-status"
        aria-live="polite"
      >
        {{ activeStatusTag.text }}
      </a-tag>
    </div>

    <a-spin :spinning="loading" tip="正在加载工具配置…">
      <div class="tool-panes">
        <section
          v-show="activeKey === 'arknightspc'"
          class="tool-pane"
          role="tabpanel"
          aria-label="明日方舟 PC"
        >
          <TabArknightsPC
            v-if="editingConfig.ArknightsPC"
            :config="editingConfig.ArknightsPC"
            :disabled="loading"
            :on-field-change="handleFieldChange"
            :recording-key-field="recordingKeyField"
            :start-record-key="startRecordKey"
            :stop-record-key="stopRecordKey"
            :on-select-visible-change="handleSelectVisibleChange"
          />
        </section>

        <section
          v-show="activeKey === 'gamesign'"
          class="tool-pane"
          role="tabpanel"
          aria-label="游戏社区签到"
        >
          <TabGameSign
            v-if="editingConfig.GameSign"
            :config="editingConfig.GameSign"
            :disabled="loading"
            :on-field-change="handleGameSignFieldChange"
            :on-select-visible-change="handleSelectVisibleChange"
            :on-refresh-config="refreshGameSignConfig"
          />
        </section>
      </div>
    </a-spin>
  </div>
</template>

<style scoped>
.tools-page {
  width: 100%;
  box-sizing: border-box;
  min-width: 0;
  container: tools-page / inline-size;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  gap: var(--v6-space-3);
}

.tools-navigation {
  display: flex;
  align-items: center;
  gap: var(--v6-space-3);
  padding: var(--v6-space-2);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-lg);
  background: color-mix(in srgb, var(--v6-color-surface) 78%, transparent);
  box-shadow: var(--v6-shadow-card);
  backdrop-filter: var(--v6-backdrop-vibrancy);
}

.tools-navigation :deep(.ant-segmented) {
  flex: 1;
  min-width: 0;
}

.tool-status {
  flex: none;
  margin: 0;
  border-radius: 999px;
}

.tool-panes {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 1px;
}

.tool-pane {
  width: 100%;
  animation: tool-pane-enter var(--v6-motion-base) var(--v6-ease-out);
}

.tool-pane :deep(.tab-content) {
  width: 100%;
  padding: 0;
}

.tool-pane :deep(.form-section) {
  margin-bottom: var(--v6-space-3);
  padding: var(--v6-space-5);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  background: color-mix(in srgb, var(--v6-color-surface) 82%, transparent);
  box-shadow: var(--v6-shadow-card);
  backdrop-filter: var(--v6-backdrop-vibrancy);
}

.tool-pane :deep(.section-header) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--v6-space-4);
  padding-bottom: var(--v6-space-3);
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.tool-pane :deep(.section-header h3) {
  margin: 0;
  font-size: 16px;
  font-weight: 650;
  color: var(--v6-color-text);
}

.tool-pane :deep(.form-item-vertical) {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.tool-pane :deep(.form-label-wrapper) {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tool-pane :deep(.form-label) {
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.tool-pane :deep(.help-icon) {
  color: var(--v6-color-text-tertiary);
  font-size: 14px;
}

@keyframes tool-pane-enter {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@container tools-page (max-width: 720px) {
  .tools-navigation {
    align-items: stretch;
    flex-direction: column;
  }
}

@media (prefers-reduced-motion: reduce) {
  .tool-pane {
    animation: none;
  }
}

:global(:root[data-perf-mode='low']) .tool-pane {
  animation: none;
}

:global(:root[data-perf-mode='low']) .tools-navigation,
:global(:root[data-perf-mode='low']) .tool-pane :deep(.form-section) {
  backdrop-filter: none;
}
</style>
