<template>
  <div v-if="showControls" class="title-bar-right" :class="{ 'title-bar-controls-dark': isDark }">
    <div class="window-controls">
      <button
        class="control-button minimize-button"
        :title="t('bootstrap.comp.minimize')"
        @click="minimizeWindow"
      >
        <MinusOutlined />
      </button>
      <button
        class="control-button maximize-button"
        :title="
          isMaximized ? t('bootstrap.comp.restoreWindow') : t('bootstrap.comp.maximizeWindow')
        "
        @click="toggleMaximize"
      >
        <SwitcherOutlined v-if="isMaximized" />
        <BorderOutlined v-else />
      </button>
      <button
        v-if="!hideCloseButton"
        class="control-button close-button"
        :title="t('bootstrap.comp.close')"
        :disabled="actionInProgress"
        @click="closeWindow"
      >
        <CloseOutlined />
      </button>
    </div>
  </div>
  <AppClosePrompt
    v-model:open="closePromptOpen"
    :busy="actionInProgress"
    :default-action="lastAction"
    @choose="handleCloseChoice"
    @cancel="closePromptOpen = false"
  />
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  BorderOutlined,
  CloseOutlined,
  MinusOutlined,
  SwitcherOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import AppClosePrompt from '@/components/AppClosePrompt.vue'
import { confirmCloseIfRunningTasks } from '@/composables/useQueueCloseConfirmation'
import { useTheme } from '@/composables/useTheme'
import { useAppClosePreferences } from '@/composables/useAppClosePreferences'
import type { AppCloseAction } from '@/utils/appClosePreferences'

defineProps<{ hideCloseButton: boolean; showControls: boolean }>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('窗口控制')
const { isDark } = useTheme()
const { confirmBeforeClose, lastAction, load, setConfirmationEnabled, chooseAction } =
  useAppClosePreferences()
const isMaximized = ref(false)
const closePromptOpen = ref(false)
const actionInProgress = ref(false)
let removeWindowMaximizedListener: (() => void) | undefined
let removeNativeCloseListener: (() => void) | undefined

const minimizeWindow = async (): Promise<void> => {
  try {
    const minimized = await window.electronAPI.windowMinimize()
    if (!minimized) message.error(t('bootstrap.comp.minimizeToTrayFailed'))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`最小化窗口失败: ${errorMsg}`)
    message.error(t('bootstrap.comp.minimizeToTrayFailed'))
  }
}

const toggleMaximize = async (): Promise<void> => {
  try {
    await window.electronAPI.windowMaximize()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`切换最大化状态失败: ${errorMsg}`)
  }
}

const runCloseAction = async (action: AppCloseAction): Promise<boolean> => {
  if (action === 'tray') {
    let hidden = false
    try {
      hidden = await window.electronAPI.windowHideToTray()
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`最小化到托盘失败: ${errorMsg}`)
    }

    if (hidden) return true

    message.error(t('bootstrap.comp.minimizeToTrayFailed'))
    if (!confirmBeforeClose.value) {
      try {
        await setConfirmationEnabled(true)
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`恢复关闭确认设置失败: ${errorMsg}`)
      }
    }
    return false
  }

  if (!(await confirmCloseIfRunningTasks())) return false
  await window.electronAPI.windowClose()
  return true
}

const closeWindow = async (): Promise<void> => {
  if (actionInProgress.value || closePromptOpen.value) return
  actionInProgress.value = true
  try {
    await load()
    if (confirmBeforeClose.value) {
      closePromptOpen.value = true
    } else {
      await runCloseAction(lastAction.value)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`关闭应用失败: ${errorMsg}`)
  } finally {
    actionInProgress.value = false
  }
}

const handleCloseChoice = async (action: AppCloseAction, remember: boolean): Promise<void> => {
  if (actionInProgress.value) return
  closePromptOpen.value = false
  actionInProgress.value = true

  try {
    if (action === 'quit') {
      if (!(await confirmCloseIfRunningTasks())) return
      try {
        await chooseAction(action, remember)
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`保存关闭应用选择失败: ${errorMsg}`)
      }
      await window.electronAPI.windowClose()
      return
    }

    if (await runCloseAction(action)) {
      try {
        await chooseAction(action, remember)
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`保存关闭应用选择失败: ${errorMsg}`)
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`关闭应用失败: ${errorMsg}`)
  } finally {
    actionInProgress.value = false
  }
}

onMounted(async () => {
  removeNativeCloseListener = window.electronAPI.onNativeWindowCloseRequested?.(() => {
    void closeWindow()
  })
  window.electronAPI.notifyNativeCloseHandlerReady?.()

  removeWindowMaximizedListener = window.electronAPI.onWindowMaximizedChange(maximized => {
    isMaximized.value = maximized
  })

  try {
    isMaximized.value = await window.electronAPI.windowIsMaximized()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`获取窗口状态失败: ${errorMsg}`)
  }

  await load()
})

onBeforeUnmount(() => {
  removeWindowMaximizedListener?.()
  removeNativeCloseListener?.()
})
</script>

<style scoped>
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
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  -webkit-app-region: no-drag;
}

.title-bar-controls-dark .control-button {
  color: var(--ant-color-text-secondary);
}

.control-button:hover {
  background: rgba(0, 0, 0, 0.05);
}

.title-bar-controls-dark .control-button:hover {
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

.title-bar-controls-dark .minimize-button:hover,
.title-bar-controls-dark .maximize-button:hover {
  background: rgba(255, 255, 255, 0.15);
}
</style>
