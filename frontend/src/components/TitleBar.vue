<template>
  <div class="title-bar" :class="{ 'title-bar-dark': isDark }">
    <!-- 左侧：Logo和软件名 -->
    <div class="title-bar-left">
      <div class="logo-section">
        <!-- 新增虚化主题色圆形阴影 -->
        <span class="logo-glow" aria-hidden="true"></span>
        <img src="@/assets/AUTO-MAS.ico" alt="AUTO-MAS" class="title-logo" />
        <span class="title-text">AUTO-MAS</span>
        <span class="version-text">
          {{ version }}
          <span v-if="isBootstrapping" class="startup-status">
            <LoadingOutlined />
            {{ t('comp.backendStarting') }}
          </span>
          <span v-if="downloadHint" class="update-hint clickable" @click="openDownloadModal">
            {{ downloadHint }}
          </span>
          <span
            v-else-if="updateInfo?.if_need_update"
            class="update-hint clickable"
            @click="handleAppUpdateClick"
          >
            检测到更新 {{ updateInfo.latest_version }} 请尽快更新
          </span>
          <span
            v-if="backendUpdateInfo?.if_need_update && isRuntimeDevelopment"
            class="update-hint disabled"
            :title="t('comp.backendUpdateDevUnsupported')"
          >
            {{ t('comp.backendUpdateDevUnsupported') }}
          </span>
          <span
            v-else-if="backendUpdateInfo?.if_need_update"
            class="update-hint clickable"
            @click="handleBackendUpdateClick"
          >
            {{ t('comp.backendUpdateAvailableClick') }}
          </span>
        </span>
      </div>
    </div>

    <!-- 中间：可拖拽区域 -->
    <div class="title-bar-center drag-region"></div>

    <!-- 右侧：窗口控制按钮 -->
    <div class="title-bar-right">
      <div class="window-controls">
        <button
          class="control-button minimize-button"
          :title="t('comp.minimize')"
          @click="minimizeWindow"
        >
          <MinusOutlined />
        </button>
        <button
          class="control-button maximize-button"
          :title="isMaximized ? '还原' : '最大化'"
          @click="toggleMaximize"
        >
          <BorderOutlined />
        </button>
        <button
          v-if="!hideCloseButton"
          class="control-button close-button"
          :title="t('comp.close')"
          @click="closeWindow"
        >
          <CloseOutlined />
        </button>
      </div>
    </div>

    <!-- Runtime 链路的后端更新进度与失败处置 -->
    <a-modal
      v-model:open="updateModalVisible"
      :title="t('comp.backendUpdateTitle', { version: updateTargetVersion })"
      :width="620"
      :footer="null"
      :mask-closable="false"
      :closable="!updateRunning"
      :z-index="9999"
      centered
      @cancel="closeUpdateModal"
    >
      <div class="backend-update-body">
        <template v-if="updateRunning">
          <a-progress :percent="updateOverallPercent" :show-info="false" :stroke-width="8" />
          <p class="backend-update-message">
            <LoadingOutlined />
            {{ updateCurrentMessage }}
          </p>
          <div class="backend-update-actions">
            <a-button danger :loading="updateCancelling" @click="cancelUpdate">
              {{ t('comp.backendUpdateCancelAction') }}
            </a-button>
          </div>
        </template>

        <template v-else-if="updateOutcome">
          <a-alert
            :type="updateAlertType"
            :message="updateAlertMessage"
            :description="updateOutcome.error"
            show-icon
          />
          <p v-if="updateOutcome.code" class="backend-update-meta">
            {{ t('comp.backendUpdateErrorCode') }}: {{ updateOutcome.code }}
          </p>
          <p v-if="updateOutcome.logPath" class="backend-update-meta">
            {{ t('comp.backendUpdateLogPath') }}: {{ updateOutcome.logPath }}
          </p>
          <pre v-if="updateOutcome.logs" class="backend-update-logs">{{ updateOutcome.logs }}</pre>
          <p v-if="updateActions.showContactSupport" class="backend-update-meta">
            {{ t('comp.backendUpdateContactSupport') }}
          </p>

          <div class="backend-update-actions">
            <a-button
              v-for="action in updateActions.retryActions"
              :key="action"
              type="primary"
              @click="retryUpdate(action)"
            >
              {{ retryActionLabel(action) }}
            </a-button>
            <a-button
              v-if="updateActions.showRestartBackend"
              type="primary"
              :loading="updateRestartingBackend"
              @click="restartBackendAfterUpdate"
            >
              {{ t('comp.backendUpdateRestartBackend') }}
            </a-button>
            <a-button @click="closeUpdateModal">{{ t('comp.close') }}</a-button>
          </div>
        </template>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { closeApp } from '@/composables/useAppLifecycle'
import { useTheme } from '@/composables/useTheme'
import { updateInfo, backendUpdateInfo } from '@/composables/useVersionService'
import { useUpdateModal } from '@/composables/useUpdateChecker'
import { useAppInitialization } from '@/composables/useAppInitialization'
import { useUpdateDownload } from '@/composables/useUpdateDownload'
import { useBackendRuntimeUpdate } from '@/composables/useBackendRuntimeUpdate'
import { useUiPreferences } from '@/composables/useUiPreferences'
import { resolveBackendUpdateActions } from '@/utils/backendUpdateActions'
import { useSchedulerLogic } from '@/views/scheduler/useSchedulerLogic'
import {
  BorderOutlined,
  CloseOutlined,
  LoadingOutlined,
  MinusOutlined,
} from '@ant-design/icons-vue'
import { Modal } from 'ant-design-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import type { RuntimeUpdateRetryAction } from '@/types/electron'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('标题栏')
const router = useRouter()
const { isBootstrapping, resetInitializationStatus } = useAppInitialization()
const { showUpdateModal } = useUpdateModal()
const { hideCloseButton, syncUiPreferences } = useUiPreferences()
const { startTaskById } = useSchedulerLogic()
let removeTrayActionListener: (() => void) | undefined

const {
  status: downloadStatus,
  sourceLabel,
  progressPercent,
  open: openDownloadModal,
} = useUpdateDownload()

const {
  ensureLaunchMode,
  isRuntimeManaged,
  isRuntimeDevelopment,
  modalVisible: updateModalVisible,
  running: updateRunning,
  cancelling: updateCancelling,
  restartingBackend: updateRestartingBackend,
  targetVersion: updateTargetVersion,
  currentMessage: updateCurrentMessage,
  overallPercent: updateOverallPercent,
  outcome: updateOutcome,
  start: startRuntimeUpdate,
  retry: retryUpdate,
  cancel: cancelUpdate,
  restartBackend: restartBackendAfterUpdate,
  close: closeUpdateModal,
} = useBackendRuntimeUpdate()

const updateAlertType = computed(() => {
  const result = updateOutcome.value
  if (!result) return 'info'
  if (result.success) return 'success'
  return result.cancelled ? 'warning' : 'error'
})

// 三类失败结局各有各的后果，文案不能共用一句「更新失败」。
const updateAlertMessage = computed(() => {
  const result = updateOutcome.value
  if (!result) return ''
  if (result.success) return t('comp.backendUpdateSucceeded')
  if (result.cancelled) return t('comp.backendUpdateCancelled')
  if (result.unsupported) return t('comp.backendUpdateUnsupportedMode')

  if (result.phase === 'shutdown') return t('comp.backendUpdateFailedShutdown')
  if (result.phase === 'restart') return t('comp.backendUpdateFailedRestart')
  return t('comp.backendUpdateFailedBootstrap')
})

// 不可重试（retryable=false / INTERNAL_ERROR / contact-support）时一个重试按钮都不给。
const updateActions = computed(() => resolveBackendUpdateActions(updateOutcome.value))

// 常量数组要放进 computed，否则切换语言后按钮文案不跟着变。
const retryActionLabels = computed<Record<RuntimeUpdateRetryAction, string>>(() => ({
  'workspace-sync': t('comp.backendUpdateRetryWorkspaceSync'),
  'dependencies-sync': t('comp.backendUpdateRetryDependenciesSync'),
  'dependencies-rebuild': t('comp.backendUpdateRetryDependenciesRebuild'),
  repair: t('comp.backendUpdateRetryRepair'),
}))

const retryActionLabel = (action: RuntimeUpdateRetryAction): string =>
  retryActionLabels.value[action]

const downloadHint = computed(() => {
  if (downloadStatus.value === 'completed') return '下载完成，点击安装'
  if (downloadStatus.value === 'switchingSource') return '正在切换至 CNB 源'
  if (downloadStatus.value === 'cancelling') return '正在取消下载'
  if (downloadStatus.value === 'failed') return '下载失败，点击查看'
  if (downloadStatus.value === 'downloading') {
    const sourceText = sourceLabel.value ? `从 ${sourceLabel.value}` : ''
    return `正在${sourceText}下载 ${progressPercent.value.toFixed(1)}%`
  }
  return ''
})

// 检查是否有运行中的队列任务
const hasRunningTasks = (): boolean => {
  try {
    const saved = sessionStorage.getItem('scheduler-tabs-session')
    if (saved) {
      const tabs = JSON.parse(saved)
      if (Array.isArray(tabs)) {
        return tabs.some((tab: any) => tab.status === '运行')
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`检查运行任务状态失败: ${errorMsg}`)
  }
  return false
}

const { isDark } = useTheme()
const isMaximized = ref(false)

// 使用 import.meta.env 或直接定义版本号，确保打包后可用
const version = import.meta.env.VITE_APP_VERSION || '获取版本失败！'

// 处理版本更新点击
const handleAppUpdateClick = () => {
  if (!updateInfo.value?.if_need_update) return

  showUpdateModal(updateInfo.value.update_info || {}, updateInfo.value.latest_version || '')
}

/**
 * Runtime 链路的目标版本。
 *
 * `/api/update/check` 返回的 `latest_version` 就是发布标签；还没查到时退回应用自身版本，
 * 主进程会再做一次规范化与合法性校验。
 */
const resolveRuntimeUpdateVersion = (): string => updateInfo.value?.latest_version || version

// 处理后端更新点击
const handleBackendUpdateClick = () => {
  Modal.confirm({
    title: t('comp.restartBackendUpdate'),
    content: t('comp.backendAboutUpdateWhich'),
    okText: t('comp.confirm'),
    cancelText: t('comp.cancel'),
    centered: true,
    onOk: async () => {
      // Runtime 监督链路下走「停机 → bootstrap → 重新监督」，不再跳初始化页整包更新。
      if (isRuntimeManaged.value) {
        await startRuntimeUpdate(resolveRuntimeUpdateVersion())
        return
      }

      try {
        logger.info('开始更新后端')

        // 1. 先关闭后端
        logger.info('正在关闭后端...')
        const result = await window.electronAPI.stopBackend()
        if (result.success) {
          logger.info('后端已成功关闭')
        } else {
          logger.warn(`后端关闭失败: ${String(result.error)}`)
        }

        // 2. 重置初始化状态
        resetInitializationStatus()

        // 3. 设置强制后端更新标志（在清理 sessionStorage 之前）
        sessionStorage.setItem('forceBackendUpdate', 'true')
        logger.info('已设置强制后端更新标志')

        // 4. 清理 sessionStorage 中的其他状态（保留 forceBackendUpdate）
        const forceUpdateFlag = sessionStorage.getItem('forceBackendUpdate')
        sessionStorage.clear()
        if (forceUpdateFlag) {
          sessionStorage.setItem('forceBackendUpdate', forceUpdateFlag)
        }

        // 5. 跳转到初始化页面
        await router.push('/initialization')
        logger.info('已跳转到初始化页面')
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`更新后端失败: ${errorMsg}`)
      }
    },
  })
}

const minimizeWindow = async () => {
  try {
    await window.electronAPI?.windowMinimize()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`最小化窗口失败: ${errorMsg}`)
  }
}

const toggleMaximize = async () => {
  try {
    await window.electronAPI?.windowMaximize()
    isMaximized.value = (await window.electronAPI?.windowIsMaximized()) || false
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`切换最大化状态失败: ${errorMsg}`)
  }
}

// 执行实际的关闭操作：交给生命周期协调器执行"退出并关闭后端"流程
const doCloseWindow = async () => {
  try {
    logger.info('开始关闭应用...')
    await closeApp()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`关闭应用失败: ${errorMsg}`)
  }
}

const closeWindow = async () => {
  // 检查是否有运行中的队列任务
  if (hasRunningTasks()) {
    Modal.confirm({
      title: t('comp.confirmExit'),
      content: t('comp.queueStillRunningClose'),
      okText: t('comp.confirmExit'),
      cancelText: t('comp.cancel'),
      okType: 'danger',
      centered: true,
      onOk: () => {
        doCloseWindow()
      },
    })
  } else {
    // 没有运行中的任务，直接关闭
    await doCloseWindow()
  }
}

// 托盘触发退出：与窗口关闭按钮走同一套确认流程
const handleTrayQuit = () => {
  if (hasRunningTasks()) {
    // 窗口可能隐藏在托盘，先恢复窗口确保确认窗可见
    window.electronAPI?.windowFocus?.()
    Modal.confirm({
      title: t('comp.confirmExit'),
      content: t('comp.queueStillRunningClose'),
      okText: t('comp.confirmExit'),
      cancelText: t('comp.cancel'),
      okType: 'danger',
      centered: true,
      onOk: () => {
        doCloseWindow()
      },
    })
  } else {
    void doCloseWindow()
  }
}

// 托盘触发重启：统一确认窗风格（与关闭确认一致）
const handleTrayRestart = () => {
  // 窗口可能隐藏在托盘，先恢复窗口确保确认窗可见
  window.electronAPI?.windowFocus?.()
  Modal.confirm({
    title: t('comp.confirmRestart'),
    content: t('comp.restartingAutoMasStops'),
    okText: t('comp.confirmRestart'),
    cancelText: t('comp.cancel'),
    okType: 'danger',
    centered: true,
    onOk: async () => {
      await window.electronAPI?.appRestart()
    },
  })
}

// 托盘触发启动任务：不调起前端，直接按任务 ID 新建调度台并启动
const handleTrayStartTask = (taskId?: string, label?: string) => {
  if (!taskId) {
    logger.warn('托盘启动任务缺少任务 ID，忽略')
    return
  }
  void startTaskById(taskId, label)
}

// 托盘动作请求统一入口：启动任务 / 退出 / 重启
const handleTrayActionRequest = (request: {
  action: 'quit' | 'restart' | 'startTask'
  taskId?: string
  label?: string
}) => {
  if (request.action === 'restart') {
    handleTrayRestart()
  } else if (request.action === 'quit') {
    handleTrayQuit()
  } else {
    handleTrayStartTask(request.taskId, request.label)
  }
}

onMounted(async () => {
  // 监听托盘动作请求（启动任务 / 退出 / 重启）
  removeTrayActionListener = window.electronAPI?.onTrayActionRequest?.(handleTrayActionRequest)

  // 后端更新入口按启动链路分流，模式一个生命周期只查一次
  await ensureLaunchMode()

  try {
    const config = await window.electronAPI?.loadConfig()
    syncUiPreferences(config?.UI)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`获取界面设置失败: ${errorMsg}`)
  }

  try {
    isMaximized.value = (await window.electronAPI?.windowIsMaximized()) || false
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`获取窗口状态失败: ${errorMsg}`)
  }
})

onBeforeUnmount(() => {
  removeTrayActionListener?.()
  removeTrayActionListener = undefined
})
</script>

<style scoped>
.title-bar {
  height: 32px;
  background: #ffffff;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  align-items: center;
  justify-content: space-between;
  user-select: none;
  position: relative;
  z-index: 1000;
  overflow: hidden;
  /* 新增：裁剪超出顶栏的发光 */
}

.title-bar-dark {
  background: #1f1f1f;
  border-bottom: 1px solid #333;
}

.title-bar-left {
  display: flex;
  align-items: center;
  padding-left: 12px;
  min-width: 64px;
  height: 100%;
  -webkit-app-region: drag;
}

.logo-section {
  display: flex;
  align-items: center;
  gap: 8px;
  position: relative;
  /* 使阴影绝对定位基准 */
}

/* 新增：主题色虚化圆形阴影 */
.logo-glow {
  position: absolute;
  left: 55px;
  /* 调整：更贴近图标 */
  top: 50%;
  transform: translate(-50%, -50%);
  width: 200px;
  /* 缩小尺寸以适配 32px 高度 */
  height: 100px;
  pointer-events: none;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 50%, var(--ant-color-primary) 0%, rgba(0, 0, 0, 0) 70%);
  filter: blur(24px);
  /* 降低模糊避免越界过多 */
  opacity: 0.4;
  z-index: 0;
}

.title-bar-dark .logo-glow {
  opacity: 0.7;
  filter: blur(24px);
}

.title-logo {
  width: 20px;
  height: 20px;
  position: relative;
  z-index: 1;
  /* 确保在阴影上方 */
}

.title-text {
  font-size: 13px;
  font-weight: 600;
  color: #333;
  position: relative;
  z-index: 1;
}

.version-text {
  font-size: 13px;
  font-weight: 400;
  opacity: 0.8;
  position: relative;
  z-index: 1;
  margin-left: 4px;
}

.title-bar-dark .title-text {
  color: #fff;
}

.startup-status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 8px;
  color: var(--ant-color-primary);
}

.title-bar-dark .version-text {
  color: #ffffff;
}

.title-bar-center {
  flex: 1;
  height: 100%;
}

.drag-region {
  -webkit-app-region: drag;
}

.title-bar-right {
  display: flex;
  align-items: center;
  height: 100%;
}

.window-controls {
  display: flex;
  height: 100%;
}

.control-button {
  width: 46px;
  height: 32px;
  border: none;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background-color 0.2s;
  color: #666;
  font-size: 12px;
  -webkit-app-region: no-drag;
}

.title-bar-dark .control-button {
  color: #ccc;
}

.control-button:hover {
  background: rgba(0, 0, 0, 0.05);
}

.title-bar-dark .control-button:hover {
  background: rgba(255, 255, 255, 0.1);
}

.close-button:hover {
  background: #e81123 !important;
  color: #fff !important;
}

.minimize-button:hover,
.maximize-button:hover {
  background: rgba(0, 0, 0, 0.08);
}

.title-bar-dark .minimize-button:hover,
.title-bar-dark .maximize-button:hover {
  background: rgba(255, 255, 255, 0.15);
}

.update-hint {
  font-weight: 600;
  margin-left: 4px;
  cursor: help;
  background: linear-gradient(
    45deg,
    #ff1744,
    #ff5722,
    #ff9800,
    #ffc107,
    #4caf50,
    #00bcd4,
    #2196f3,
    #9c27b0,
    #ff1744
  );
  background-size: 400% 400%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation:
    rainbow-flow 3s ease-in-out infinite,
    glow-pulse 2s ease-in-out infinite;
  position: relative;
  filter: drop-shadow(0 0 4px rgba(255, 64, 129, 0.4));
  transition: all 0.3s ease;
  font-size: 13px;
  line-height: 1.2;
  padding: 2px 4px;
  border-radius: 4px;
}

.update-hint.clickable {
  cursor: pointer;
  user-select: none;
  -webkit-app-region: no-drag;
}

.update-hint.clickable:hover {
  transform: scale(1.05);
  filter: drop-shadow(0 0 10px rgba(255, 64, 129, 0.8));
}

.update-hint.clickable:active {
  transform: scale(0.98);
}

/* development 模式下 Runtime 不管理源码，入口只展示不可点 */
.update-hint.disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.update-hint.disabled:hover {
  transform: none;
  filter: none;
}

.backend-update-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.backend-update-message {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: var(--ant-color-text-secondary);
}

.backend-update-meta {
  margin: 0;
  font-size: 12px;
  word-break: break-all;
  color: var(--ant-color-text-secondary);
}

.backend-update-logs {
  max-height: 220px;
  margin: 0;
  padding: 8px;
  overflow: auto;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  background: var(--ant-color-fill-quaternary);
  border-radius: 6px;
}

.backend-update-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.update-hint:hover {
  transform: scale(1.02);
  filter: drop-shadow(0 0 8px rgba(255, 64, 129, 0.7));
  animation-duration: 3s, 2s;
}

.update-hint::before {
  content: '';
  position: absolute;
  top: -2px;
  left: -2px;
  right: -2px;
  bottom: -2px;
  background: linear-gradient(
    45deg,
    #ff1744,
    #ff5722,
    #ff9800,
    #ffc107,
    #4caf50,
    #00bcd4,
    #2196f3,
    #9c27b0,
    #ff1744
  );
  background-size: 400% 400%;
  border-radius: 6px;
  z-index: -1;
  opacity: 0.12;
  filter: blur(8px);
  animation: rainbow-flow 4s ease-in-out infinite;
}

.update-hint::after {
  content: '';
  position: absolute;
  top: -3px;
  left: -3px;
  right: -3px;
  bottom: -3px;
  background: radial-gradient(circle at center, rgba(255, 64, 129, 0.08) 0%, transparent 70%);
  border-radius: 8px;
  z-index: -2;
  animation: pulse-ring 4s ease-in-out infinite;
}

/* 为相邻的更新提示添加间距 */
.update-hint + .update-hint {
  margin-left: 12px;
}

.title-bar-dark .update-hint {
  filter: drop-shadow(0 0 6px rgba(255, 64, 129, 0.6));
}

.title-bar-dark .update-hint::before {
  opacity: 0.2;
  filter: blur(10px);
}

.title-bar-dark .update-hint::after {
  background: radial-gradient(circle at center, rgba(255, 64, 129, 0.15) 0%, transparent 70%);
}

@keyframes rainbow-flow {
  0% {
    background-position: 0% 50%;
  }

  50% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0% 50%;
  }
}

@keyframes glow-pulse {
  0% {
    filter: drop-shadow(0 0 4px rgba(255, 64, 129, 0.4)) brightness(1);
    transform: scale(1);
  }

  33% {
    filter: drop-shadow(0 0 6px rgba(255, 152, 0, 0.5)) brightness(1.08);
    transform: scale(1.003);
  }

  66% {
    filter: drop-shadow(0 0 5px rgba(76, 175, 80, 0.45)) brightness(1.05);
    transform: scale(1.002);
  }

  100% {
    filter: drop-shadow(0 0 4px rgba(255, 64, 129, 0.4)) brightness(1);
    transform: scale(1);
  }
}

@keyframes pulse-ring {
  0% {
    opacity: 0.08;
    transform: scale(0.98);
  }

  50% {
    opacity: 0.04;
    transform: scale(1.02);
  }

  100% {
    opacity: 0.08;
    transform: scale(0.98);
  }
}
</style>
