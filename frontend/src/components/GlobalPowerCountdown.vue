<template>
  <!-- 电源操作倒计时弹窗 - 倒计时状态由后端 power.countdown.updated 驱动 -->
  <a-modal
    v-model:open="visible"
    :title="null"
    :footer="null"
    :closable="false"
    :keyboard="false"
    :mask-closable="false"
    :mask="{ blur: true }"
    :width="480"
    centered
    wrap-class-name="power-countdown-modal"
  >
    <div class="countdown-content">
      <div class="warning-icon">⚠️</div>
      <h2 class="countdown-title">{{ title }}</h2>
      <p class="countdown-message">{{ message }}</p>
      <div class="countdown-timer">
        <span class="countdown-number">{{ remaining }}</span>
        <span class="countdown-unit">秒</span>
      </div>
      <a-progress
        :percent="Math.max(0, Math.min(100, ((60 - remaining) / 60) * 100))"
        :show-info="false"
        :stroke-color="remaining <= 10 ? '#ff4d4f' : '#1890ff'"
        :stroke-width="8"
        class="countdown-progress"
      />
      <div class="countdown-actions">
        <a-button type="primary" size="large" class="cancel-button" @click="handleCancel">
          取消操作
        </a-button>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Service } from '@/api'
import { useAppLifecycle } from '@/composables/useAppLifecycle'
const logger = window.electronAPI.getLogger('全局电源倒计时')

// 电源操作显示名
const POWER_OPERATION_LABEL: Record<string, string> = {
  Shutdown: '关机',
  ShutdownForce: '强制关机',
  Reboot: '重启',
  Hibernate: '休眠',
  Sleep: '睡眠',
  KillSelf: '关闭软件',
  Logoff: '注销',
}

const { powerCountdown } = useAppLifecycle()

const visible = ref(false)
const remaining = computed(() => powerCountdown.value?.remaining ?? 0)
const operationLabel = computed(() => {
  const operation = powerCountdown.value?.operation || ''
  return POWER_OPERATION_LABEL[operation] || operation || '电源操作'
})
const title = computed(() => `${operationLabel.value}倒计时`)
const message = computed(() => `程序将在倒计时结束后执行 ${operationLabel.value} 操作`)

// 激活窗口到前台
const focusWindow = async () => {
  try {
    if (window.electronAPI?.windowFocus) {
      await window.electronAPI.windowFocus()
      logger.info('窗口已激活到前台')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`激活窗口失败: ${errorMsg}`)
  }
}

// 倒计时出现时弹窗并拉起窗口（即使在托盘状态）；倒计时结束/取消时关闭
watch(
  () => powerCountdown.value,
  (current, previous) => {
    if (current && !previous) {
      logger.info(`收到电源倒计时: ${current.operation}, 剩余 ${current.remaining} 秒`)
      visible.value = true
      void focusWindow()
    } else if (!current && previous) {
      logger.info('电源倒计时结束或已取消，关闭弹窗')
      visible.value = false
    }
  },
  { immediate: true }
)

// 取消电源操作（走现有 HTTP API，后端会回发 power.countdown.cancelled）
const handleCancel = async () => {
  logger.info('用户取消电源操作')
  try {
    await Service.cancelPowerTaskApiDispatchCancelPowerPost()
    logger.info('电源操作已取消')

    // 触发全局事件，通知调度中心刷新电源状态
    window.dispatchEvent(new CustomEvent('power-state-changed'))
    logger.info('已发送电源状态变更事件')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`取消电源操作失败: ${errorMsg}`)
  }
}
</script>

<style>
/* 电源操作倒计时 Modal 全局样式 */
.power-countdown-modal .ant-modal-content {
  padding: 48px;
  border-radius: 16px;
}

.power-countdown-modal .ant-modal-body {
  padding: 0;
}
</style>

<style scoped>
/* 倒计时内容样式 */
.countdown-content {
  text-align: center;
}

.countdown-content .warning-icon {
  font-size: 64px;
  margin-bottom: 24px;
  display: block;
  animation: pulse 2s infinite;
}

.countdown-title {
  font-size: 28px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin: 0 0 16px 0;
}

.countdown-message {
  font-size: 16px;
  color: var(--ant-color-text-secondary);
  margin: 0 0 32px 0;
  line-height: 1.5;
}

.countdown-timer {
  display: flex;
  align-items: baseline;
  justify-content: center;
  margin-bottom: 32px;
}

.countdown-number {
  font-size: 72px;
  font-weight: 700;
  color: var(--ant-color-primary);
  line-height: 1;
  margin-right: 8px;
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
}

.countdown-unit {
  font-size: 24px;
  color: var(--ant-color-text-secondary);
  font-weight: 500;
}

.countdown-progress {
  margin-bottom: 32px;
}

.countdown-actions {
  display: flex;
  justify-content: center;
}

.cancel-button {
  padding: 12px 32px;
  height: auto;
  font-size: 16px;
  font-weight: 500;
}

/* 动画效果 */
@keyframes pulse {
  0%,
  100% {
    transform: scale(1);
  }

  50% {
    transform: scale(1.1);
  }
}

/* 响应式 - 移动端适配 */
@media (max-width: 768px) {
  .countdown-title {
    font-size: 24px;
  }

  .countdown-number {
    font-size: 56px;
  }

  .countdown-unit {
    font-size: 20px;
  }

  .countdown-content .warning-icon {
    font-size: 48px;
    margin-bottom: 16px;
  }
}
</style>
