<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Modal } from 'ant-design-vue'
import { closeApp } from '@/composables/useAppLifecycle'
import { useTheme } from '@/composables/useTheme'
import { useAppInitialization } from '@/composables/useAppInitialization'
import { useUpdateModal } from '@/composables/useUpdateChecker'
import { useUpdateDownload } from '@/composables/useUpdateDownload'
import { useUiPreferences } from '@/composables/useUiPreferences'
import { updateInfo, backendUpdateInfo } from '@/composables/useVersionService'
import TitleBarStatus from './app-shell/TitleBarStatus.vue'
import TitleBarControls from './app-shell/TitleBarControls.vue'
import TitleBarBrand from './app-shell/TitleBarBrand.vue'

const logger = window.electronAPI.getLogger('标题栏')
const router = useRouter()
const { isDark } = useTheme()
const { isBootstrapping, resetInitializationStatus } = useAppInitialization()
const { showUpdateModal } = useUpdateModal()
const { hideCloseButton, syncUiPreferences } = useUiPreferences()

const {
  status: downloadStatus,
  sourceLabel,
  progressPercent,
  open: openDownloadModal,
} = useUpdateDownload()

const isMaximized = ref(false)
const appVersion = import.meta.env.VITE_APP_VERSION?.trim() || '开发版'

const windowTitle = computed(() => {
  return `AUTO-MAS · ${appVersion}`
})

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

const handleAppUpdateClick = () => {
  if (!updateInfo.value?.if_need_update) return
  showUpdateModal(updateInfo.value.update_info || {}, updateInfo.value.latest_version || '')
}

const handleBackendUpdateClick = () => {
  Modal.confirm({
    title: '重启后端以更新',
    content: '即将更新后端，这需要重启后端程序，您当前正在运行的任务将会被中断。确认继续？',
    okText: '确认',
    cancelText: '取消',
    centered: true,
    onOk: async () => {
      try {
        logger.info('开始更新后端')
        const result = await window.electronAPI.stopBackend()
        if (result.success) {
          logger.info('后端已成功关闭')
        } else {
          logger.warn(`后端关闭失败: ${String(result.error)}`)
        }
        resetInitializationStatus()
        sessionStorage.setItem('forceBackendUpdate', 'true')
        logger.info('已设置强制后端更新标志')
        const forceUpdateFlag = sessionStorage.getItem('forceBackendUpdate')
        sessionStorage.clear()
        if (forceUpdateFlag) {
          sessionStorage.setItem('forceBackendUpdate', forceUpdateFlag)
        }
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
  if (hasRunningTasks()) {
    Modal.confirm({
      title: '确认关闭',
      content: '队列正在运行中，确认关闭AUTO-MAS吗？',
      okText: '确认关闭',
      cancelText: '取消',
      okType: 'danger',
      centered: true,
      onOk: () => doCloseWindow(),
    })
  } else {
    await doCloseWindow()
  }
}

onMounted(async () => {
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
</script>

<template>
  <div class="title-bar" :class="{ 'title-bar-dark': isDark }">
    <TitleBarControls
      :is-maximized="isMaximized"
      :hide-close-button="hideCloseButton"
      @minimize="minimizeWindow"
      @toggle-maximize="toggleMaximize"
      @close="closeWindow"
    />

    <div class="title-bar-brand-wrap" :title="windowTitle">
      <TitleBarBrand :version="appVersion" />
    </div>

    <div class="title-bar-spacer drag-region" aria-hidden="true"></div>

    <div class="title-bar-right" aria-label="应用状态">
      <TitleBarStatus
        :is-bootstrapping="isBootstrapping"
        :download-hint="downloadHint"
        :update-info="updateInfo"
        :backend-update-info="backendUpdateInfo"
        @open-download="openDownloadModal"
        @open-app-update="handleAppUpdateClick"
        @open-backend-update="handleBackendUpdateClick"
      />
    </div>
  </div>
</template>

<style scoped>
.title-bar {
  height: var(--v6-titlebar-height);
  background: var(--v6-color-titlebar);
  border-bottom: 0.5px solid var(--v6-color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  user-select: none;
  -webkit-user-select: none;
  position: relative;
  z-index: var(--v6-z-titlebar);
  overflow: hidden;
  color: var(--v6-color-text);
  font-family: var(--v6-font-sans);
  background: var(--v6-vibrancy-titlebar);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-app-region: drag;
}

.title-bar-dark {
  /* 保持与浅色一致走 vibrancy token（dark ≈ 0.75 透明度），
     不再退回不透明的 --v6-color-titlebar（0.90），以符合设计毛玻璃层级。 */
  background: var(--v6-vibrancy-titlebar);
  border-bottom-color: var(--v6-color-border);
}

.title-bar-brand-wrap {
  min-width: 0;
  height: 100%;
  -webkit-app-region: drag;
}

.title-bar-spacer {
  flex: 1 1 auto;
  min-width: var(--v6-space-4);
}

.drag-region {
  height: 100%;
  -webkit-app-region: drag;
}

.title-bar-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-width: 0;
  max-width: min(42vw, 520px);
  height: 100%;
  margin-left: var(--v6-space-3);
  padding-right: var(--v6-space-3);
  overflow: hidden;
  -webkit-app-region: no-drag;
}

@media (max-width: 680px) {
  .title-bar-right {
    max-width: 36vw;
    margin-left: var(--v6-space-2);
    padding-right: var(--v6-space-2);
  }
}

@media (prefers-reduced-motion: reduce) {
  .title-bar {
    transition: none;
  }
}
</style>
