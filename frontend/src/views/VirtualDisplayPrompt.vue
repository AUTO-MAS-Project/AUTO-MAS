<script setup lang="ts">
// 真实显示器回来了但有任务在跑：后端不拆虚拟屏，改为问用户。
// 这个页面跑在主进程另开的小窗口里，落在接回的那块屏右下角——虚拟屏此刻是主显示器，
// 主窗口和任务栏都在看不见的那块上，画在主窗口里用户根本看不到。
// 它不建自己的 WebSocket（主连接只能有一条，第二条会把主窗口顶下线），数据由主进程
// 转来；拆不拆直接调后端 HTTP 接口，弹窗收不收由后端消息经主窗口通知主进程。
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { DesktopOutlined } from '@ant-design/icons-vue'
import { ActionService } from '@/api'
import type { VirtualDisplayPromptPayload } from '@/types/electron'

defineOptions({ name: 'VirtualDisplayPrompt' })

const logger = window.electronAPI.getLogger('虚拟显示器询问弹窗')
const { t } = useI18n()

const payload = ref<VirtualDisplayPromptPayload | null>(null)
const detaching = ref(false)
const errorText = ref('')

const devices = computed(() => payload.value?.returned.join(', ') ?? '')

let disposeData: (() => void) | undefined

onMounted(async () => {
  disposeData = window.electronAPI.onVirtualDisplayPromptData?.(data => {
    payload.value = data
    errorText.value = ''
  })
  try {
    // 主进程在页面加载完成时推送会早于这里注册监听，所以挂载后自己取一次
    payload.value = (await window.electronAPI.getVirtualDisplayPrompt?.()) ?? null
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`读取询问数据失败: ${errorMsg}`)
  }
})

onUnmounted(() => {
  disposeData?.()
})

const close = async () => {
  try {
    await window.electronAPI.closeVirtualDisplayPrompt?.()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`关闭弹窗失败: ${errorMsg}`)
  }
}

const handleKeep = () => {
  logger.info('用户选择保留虚拟显示器，任务结束后由守卫自动拆除')
  void close()
}

const handleDetach = async () => {
  if (detaching.value) return
  detaching.value = true
  errorText.value = ''
  logger.info('用户选择立即拆除虚拟显示器')
  try {
    const result = await ActionService.detachVirtualDisplayApiSettingVirtualDisplayDetachPost()
    if (result.code !== 200) {
      errorText.value = t('setting.display.prompt.detachFailed', { reason: result.message })
      return
    }
    // 后端拆完会发 display.detach.prompt.closed 让主窗口收掉这个窗；这里不等它，直接关
    await close()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`拆除虚拟显示器失败: ${errorMsg}`)
    errorText.value = t('setting.display.prompt.detachFailed', { reason: errorMsg })
  } finally {
    detaching.value = false
  }
}
</script>

<template>
  <div class="vdd-prompt">
    <div class="vdd-prompt-header">
      <DesktopOutlined class="vdd-prompt-icon" />
      <span class="vdd-prompt-title">{{ t('setting.display.prompt.title') }}</span>
    </div>
    <p class="vdd-prompt-body">{{ t('setting.display.prompt.body', { devices }) }}</p>
    <p v-if="errorText" class="vdd-prompt-error">{{ errorText }}</p>
    <div class="vdd-prompt-actions">
      <a-button type="primary" :disabled="detaching" @click="handleKeep">
        {{ t('setting.display.prompt.keep') }}
      </a-button>
      <a-button danger :loading="detaching" @click="handleDetach">
        {{ detaching ? t('setting.display.prompt.detaching') : t('setting.display.prompt.detach') }}
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.vdd-prompt {
  box-sizing: border-box;
  height: 100vh;
  width: 100vw;
  display: flex;
  flex-direction: column;
  padding: 16px 20px;
  background: var(--ant-color-bg-elevated, #ffffff);
  color: var(--ant-color-text, rgba(0, 0, 0, 0.88));
  border: 1px solid var(--ant-color-border, #d9d9d9);
  border-radius: 8px;
  overflow: hidden;
  /* 无边框窗口：标题区域可拖动，正文和按钮不拖 */
  user-select: none;
}

.vdd-prompt-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  -webkit-app-region: drag;
}

.vdd-prompt-icon {
  font-size: 20px;
  color: var(--ant-color-warning, #faad14);
}

.vdd-prompt-title {
  font-size: 16px;
  font-weight: 600;
}

.vdd-prompt-body {
  flex: 1;
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--ant-color-text-secondary, rgba(0, 0, 0, 0.65));
  overflow-y: auto;
}

.vdd-prompt-error {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--ant-color-error, #ff4d4f);
}

.vdd-prompt-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
  -webkit-app-region: no-drag;
}
</style>
