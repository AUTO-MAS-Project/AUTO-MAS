<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { useEventListener } from '@vueuse/core'
import type { ToolsConfig, ToolsConfig_ArknightsPC } from '@/api'
import { Service } from '@/api'
import { useToolsApi } from '@/composables/useToolsApi'
import { useStatusTag, createStatusTag } from '@/composables/useStatusTag'
import TabArknightsPC from './TabArknightsPC.vue'

const { t } = useI18n()

defineOptions({ name: 'ToolsPage' })

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
})

// 使用通用的状态标签解析
const arknightsPCStatusTag = useStatusTag(
  () => toolsConfig.ArknightsPC?.Status,
  createStatusTag(t('tools.statusDisabled'), 'default')
)

// 轮询定时器
let pollTimer: ReturnType<typeof setInterval> | null = null
let statusRequest: Promise<void> | null = null
let statusPollFailed = false

// 卸载守卫：组件卸载后阻止异步回调写入响应式状态
let isMounted = true

// 仅更新状态（不影响编辑状态，不触发 loading）
const updateStatus = () => {
  if (statusRequest) return statusRequest

  const request = (async () => {
    try {
      // 直接调用 Service 而非 getTools()，避免 loading 状态切换导致组件重渲染闪烁
      const response = await Service.getToolsApiToolsGetPost()
      if (!isMounted) return
      if (response.code !== 200 || !response.data) {
        throw new Error(response.message || t('tools.statusInvalid'))
      }
      const data = response.data
      statusPollFailed = false
      if (data.ArknightsPC?.Status) {
        // 只更新 toolsConfig 的状态，不更新 editingConfig
        // 这样轮询只影响状态标签显示，不会触发编辑表单重新渲染
        toolsConfig.ArknightsPC!.Status = data.ArknightsPC.Status
      }
    } catch (error) {
      if (!statusPollFailed) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.warn(`更新工具状态失败，将继续重试: ${errorMsg}`)
        statusPollFailed = true
      }
    }
  })()
  statusRequest = request
  void request.then(
    () => {
      if (statusRequest === request) statusRequest = null
    },
    () => {
      if (statusRequest === request) statusRequest = null
    }
  )
  return request
}

// 启动状态轮询
const startStatusPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
  }
  pollTimer = setInterval(() => {
    void updateStatus()
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
    // 游戏社区由侧边栏独立页面单独维护，工具页只接管明日方舟 PC 配置。
    Object.assign(toolsConfig, { ArknightsPC: data.ArknightsPC })
    Object.assign(editingConfig, {
      ArknightsPC: JSON.parse(JSON.stringify(data.ArknightsPC)),
    })
    logger.info('工具加载完成')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载工具失败: ${errorMsg}`)
  }
}

// 保存单个字段的变更（实时保存）
type ArknightsPCFieldKey = keyof ToolsConfig_ArknightsPC
type ArknightsPCKeyField = Exclude<ArknightsPCFieldKey, 'Enabled' | 'Status'>

const handleFieldChange = async <K extends ArknightsPCFieldKey>(
  key: K,
  value: ToolsConfig_ArknightsPC[K]
) => {
  const editingArknightsPC = editingConfig.ArknightsPC
  if (!editingArknightsPC) return

  const previousValue = editingArknightsPC[key]
  try {
    // 更新编辑状态
    editingArknightsPC[key] = value

    // 只提交当前字段，避免旧状态覆盖运行中的工具配置。
    await updateTools({
      ArknightsPC: { [key]: value },
    })

    // 保存成功后只同步修改的字段到 toolsConfig，不触碰 Status
    if (toolsConfig.ArknightsPC && key !== 'Status') {
      toolsConfig.ArknightsPC[key] = value
    }

    logger.info(`${key} 已保存`)
  } catch (error) {
    // 并发保存时只回滚仍保持本次值的字段，避免覆盖用户后续输入。
    if (editingArknightsPC[key] === value) {
      editingArknightsPC[key] = previousValue
    }
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 ${key} 失败: ${errorMsg}`)
  }
}

// 键位录制状态
const recordingKeyField = ref<ArknightsPCKeyField | null>(null)

// 开始录制键位
const startRecordKey = (fieldName: ArknightsPCKeyField) => {
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
  if (fieldName) await handleFieldChange(fieldName, keyName)
}

// 使用 VueUse 的 useEventListener 管理键盘事件
useEventListener(document, 'keydown', handleKeyDown)
useEventListener(window, 'focus', () => void updateStatus())
useEventListener(document, 'visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    void updateStatus()
  }
})

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
  <div class="settings-container">
    <div class="settings-header">
      <h1 class="page-title">{{ t('tools.title') }}</h1>
    </div>
    <div class="settings-content">
      <a-tabs v-model:active-key="activeKey" type="card" :loading="loading" class="settings-tabs">
        <a-tab-pane key="arknightspc">
          <template #tab>
            <span style="display: flex; align-items: center; gap: 8px">
              <span>{{ t('tools.arknightsPC') }}</span>
              <a-tag
                v-if="arknightsPCStatusTag"
                :color="arknightsPCStatusTag.color"
                style="margin: 0; font-size: 12px"
              >
                {{ arknightsPCStatusTag.text }}
              </a-tag>
            </span>
          </template>
          <TabArknightsPC
            v-if="editingConfig.ArknightsPC"
            :config="editingConfig.ArknightsPC"
            :disabled="loading"
            :on-field-change="handleFieldChange"
            :recording-key-field="recordingKeyField"
            :start-record-key="startRecordKey"
            :stop-record-key="stopRecordKey"
          />
        </a-tab-pane>
      </a-tabs>
    </div>
  </div>
</template>

<style scoped>
/* 统一样式，使用 :deep 作用到子组件内部 */
.settings-container {
  /* Allow the settings page to expand with the window width */
  width: 100%;
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  /* Use full viewport min-height so the page can grow and scroll */
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.settings-header {
  margin-bottom: 16px;
  padding: 0 4px;
}

.page-title {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
}

.settings-content {
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  width: 100%;
  flex: 1;
}

.settings-tabs {
  margin: 0;
  padding: 12px;
}

.settings-tabs :deep(.ant-tabs-nav) {
  padding: 0;
  margin: 0;
}

.settings-tabs :deep(.ant-tabs-content-holder) {
  overflow: visible;
}

.settings-tabs :deep(.ant-tabs-card > .ant-tabs-nav .ant-tabs-tab) {
  background: transparent;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px 8px 0 0;
  margin-right: 8px;
}

.settings-tabs :deep(.ant-tabs-card > .ant-tabs-nav .ant-tabs-tab-active) {
  background: var(--ant-color-bg-container);
  border-bottom-color: var(--ant-color-bg-container);
}

:deep(.tab-content) {
  padding: 24px;
  width: 100%;
}

:deep(.form-section) {
  margin-bottom: 32px;
}

:deep(.form-section:last-child) {
  margin-bottom: 0;
}

:deep(.section-header) {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

:deep(.section-header h3) {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

:deep(.section-header h3::before) {
  content: '';
  width: 4px;
  height: 24px;
  background: var(--ant-color-primary);
  border-radius: 2px;
}

:deep(.section-description) {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

:deep(.form-item-vertical) {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

:deep(.form-label-wrapper) {
  display: flex;
  align-items: center;
  gap: 8px;
}

:deep(.form-label) {
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

:deep(.help-icon) {
  color: #8c8c8c;
  font-size: 14px;
}

/* Tab 标签中的状态标签样式 - 与脚本管理页统一 */
.settings-tabs :deep(.ant-tabs-tab) {
  .ant-tag {
    font-size: 11px;
    font-weight: 500;
    border-radius: 4px;
    margin: 0;
    border: 1px solid rgba(0, 0, 0, 0.15);
  }
}

@media (max-width: 860px) {
  .settings-tabs {
    padding: 8px;
  }

  :deep(.tab-content) {
    padding: 16px;
  }

  :deep(.section-header) {
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 12px;
  }
}
</style>
