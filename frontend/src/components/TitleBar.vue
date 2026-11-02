<template>
  <div class="title-bar" :class="{ 'title-bar-dark': isDark, 'title-bar-macos': isMacOS }">
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
            {{ t('bootstrap.comp.backendStarting') }}
          </span>
          <span v-if="downloadHint" class="update-hint clickable" @click="openDownloadModal">
            {{ downloadHint }}
          </span>
          <span
            v-else-if="updateInfo?.if_need_update"
            class="update-hint clickable"
            @click="handleAppUpdateClick"
          >
            {{ t('bootstrap.comp.updateAvailableHint', { version: updateInfo.latest_version }) }}
          </span>
          <span
            v-if="backendUpdateInfo?.if_need_update && isRuntimeDevelopment"
            class="update-hint disabled"
            :title="t('bootstrap.comp.backendUpdateDevUnsupported')"
          >
            {{ t('bootstrap.comp.backendUpdateDevUnsupported') }}
          </span>
          <span
            v-else-if="
              runtimeBackendUpdateAvailable ||
              (backendUpdateInfo?.if_need_update && !isRuntimeManaged)
            "
            class="update-hint clickable"
            @click="handleBackendUpdateClick"
          >
            {{
              t(
                runtimeBackendUpdateAvailable
                  ? 'bootstrap.comp.backendUpdateReady'
                  : 'bootstrap.comp.backendUpdateAvailableClick'
              )
            }}
          </span>
        </span>
      </div>
    </div>

    <!-- 中间：可拖拽区域 -->
    <div class="title-bar-center drag-region"></div>

    <WindowControls :show-controls="!isMacOS" />

    <!-- Runtime 链路的后端更新进度与失败处置 -->
    <a-modal
      v-model:open="updateModalVisible"
      :title="t('bootstrap.comp.backendUpdateTitle', { version: updateTargetVersion })"
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
              {{ t('bootstrap.comp.backendUpdateCancelAction') }}
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
            {{ t('bootstrap.comp.backendUpdateErrorCode') }}: {{ updateOutcome.code }}
          </p>
          <p v-if="updateOutcome.logPath" class="backend-update-meta">
            {{ t('bootstrap.comp.backendUpdateLogPath') }}: {{ updateOutcome.logPath }}
          </p>
          <pre v-if="updateOutcome.logs" class="backend-update-logs">{{ updateOutcome.logs }}</pre>
          <p v-if="updateActions.showContactSupport" class="backend-update-meta">
            {{ t('bootstrap.comp.backendUpdateContactSupport') }}
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
              {{ t('bootstrap.comp.backendUpdateRestartBackend') }}
            </a-button>
            <a-button @click="closeUpdateModal">{{ t('bootstrap.comp.close') }}</a-button>
          </div>
        </template>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  beginIntentionalBackendRestart,
  endIntentionalBackendRestart,
} from '@/composables/useAppLifecycle'
import { useTheme } from '@/composables/useTheme'
import {
  updateInfo,
  backendUpdateInfo,
  runtimeBackendUpdateAvailable,
  runtimeBackendUpdateCommitMessage,
} from '@/composables/useVersionService'
import { useUpdateModal } from '@/composables/useUpdateChecker'
import { useAppInitialization } from '@/composables/useAppInitialization'
import { useUpdateDownload } from '@/composables/useUpdateDownload'
import { useBackendRuntimeUpdate } from '@/composables/useBackendRuntimeUpdate'
import {
  confirmCloseIfRunningTasks,
  hasRunningTasks,
} from '@/composables/useQueueCloseConfirmation'
import { resolveBackendUpdateActions } from '@/utils/backendUpdateActions'
import { LoadingOutlined } from '@ant-design/icons-vue'
import { Modal } from 'ant-design-vue'
import { computed, h, onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import WindowControls from '@/components/WindowControls.vue'

import type { RuntimeUpdateRetryAction } from '@/types/electron'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('标题栏')
const isMacOS = window.electronAPI.isMacOS
const router = useRouter()
const { isBootstrapping, resetInitializationStatus } = useAppInitialization()
const { showUpdateModal } = useUpdateModal()
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
  if (result.success) return t('bootstrap.comp.backendUpdateSucceeded')
  if (result.cancelled) return t('bootstrap.comp.backendUpdateCancelled')
  if (result.unsupported) return t('bootstrap.comp.backendUpdateUnsupportedMode')

  if (result.phase === 'shutdown') return t('bootstrap.comp.backendUpdateFailedShutdown')
  if (result.phase === 'restart') return t('bootstrap.comp.backendUpdateFailedRestart')
  return t('bootstrap.comp.backendUpdateFailedBootstrap')
})

// 不可重试（retryable=false / INTERNAL_ERROR / contact-support）时一个重试按钮都不给。
const updateActions = computed(() => resolveBackendUpdateActions(updateOutcome.value))

// 常量数组要放进 computed，否则切换语言后按钮文案不跟着变。
const retryActionLabels = computed<Record<RuntimeUpdateRetryAction, string>>(() => ({
  bootstrap: t('bootstrap.comp.backendUpdateRetryBootstrap'),
  'workspace-sync': t('bootstrap.comp.backendUpdateRetryWorkspaceSync'),
  'dependencies-sync': t('bootstrap.comp.backendUpdateRetryDependenciesSync'),
  'dependencies-rebuild': t('bootstrap.comp.backendUpdateRetryDependenciesRebuild'),
  repair: t('bootstrap.comp.backendUpdateRetryRepair'),
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

const { isDark } = useTheme()

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
    title: t('bootstrap.comp.restartBackendUpdate'),
    content:
      runtimeBackendUpdateAvailable.value && runtimeBackendUpdateCommitMessage.value
        ? h('div', [
            h('p', t('bootstrap.comp.backendUpdateReadyConfirm')),
            h('strong', t('bootstrap.comp.backendUpdateLatestCommit')),
            h(
              'div',
              {
                style: {
                  whiteSpace: 'pre-wrap',
                  overflowWrap: 'anywhere',
                  maxHeight: '200px',
                  overflowY: 'auto',
                },
              },
              runtimeBackendUpdateCommitMessage.value
            ),
          ])
        : t(
            runtimeBackendUpdateAvailable.value
              ? 'bootstrap.comp.backendUpdateReadyConfirm'
              : 'bootstrap.comp.backendAboutUpdateWhich'
          ),
    okText: t('bootstrap.comp.confirm'),
    cancelText: t('bootstrap.comp.cancel'),
    centered: true,
    onOk: async () => {
      // 同一 release 分支有新 Commit 时，重启应用让启动 bootstrap 在停机窗口完成同步。
      if (isRuntimeManaged.value && runtimeBackendUpdateAvailable.value) {
        await window.electronAPI.appRestart()
        return
      }
      // 跨版本更新仍走完整的 Runtime 更新编排。
      if (isRuntimeManaged.value) {
        await startRuntimeUpdate(resolveRuntimeUpdateVersion())
        return
      }

      // 关后端到初始化流程重新拉起它之间的断开是计划内的：先打好标记，
      // 否则生命周期协调器会当成事故——提示用户断线，并 taskkill 后抢着起一个后端
      beginIntentionalBackendRestart('标题栏触发后端更新')
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
        // 没能走到初始化页：后端不会有人再拉起它，交回协调器按事故处理
        endIntentionalBackendRestart('后端更新流程异常中断')
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`更新后端失败: ${errorMsg}`)
      }
    },
  })
}

// 先由主进程隐藏窗口，再让生命周期协调器在后台执行关闭流程
const doCloseWindow = async () => {
  try {
    logger.info('开始关闭应用...')
    await window.electronAPI?.windowClose()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`关闭应用失败: ${errorMsg}`)
  }
}

// 托盘触发退出：按任务运行状态确认。
const handleTrayQuit = () => {
  if (hasRunningTasks()) {
    // 窗口可能隐藏在托盘，先恢复窗口确保确认窗可见
    window.electronAPI?.windowFocus?.()
  }
  void confirmCloseIfRunningTasks().then(confirmed => {
    if (confirmed) return doCloseWindow()
  })
}

// 退出需要标题栏的确认流程；任务启动由应用作用域接收。
const handleTrayActionRequest = (request: {
  action: 'quit' | 'startTask'
  taskId?: string
  label?: string
}) => {
  if (request.action === 'quit') {
    handleTrayQuit()
  }
}

onMounted(async () => {
  // 监听托盘退出请求
  removeTrayActionListener = window.electronAPI?.onTrayActionRequest?.(handleTrayActionRequest)

  // 后端更新入口按启动链路分流，模式一个生命周期只查一次
  await ensureLaunchMode()
})

onBeforeUnmount(() => {
  removeTrayActionListener?.()
  removeTrayActionListener = undefined
})
</script>

<style scoped src="./TitleBar.css"></style>
