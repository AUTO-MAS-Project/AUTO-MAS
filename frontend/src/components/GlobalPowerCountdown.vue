<template>
  <!-- 电源操作倒计时弹窗 - 使用 Ant Design Vue Modal -->
  <a-modal v-model:open="visible" :title="null" :footer="null" :closable="false" :keyboard="false"
    :mask-closable="false" :mask="{ blur: true }" :width="480" centered wrap-class-name="power-countdown-modal">
    <div class="countdown-content">
      <div class="warning-icon">⚠️</div>
      <h2 class="countdown-title">{{ title }}</h2>
      <p class="countdown-message">{{ message }}</p>
      <div v-if="countdown !== undefined" class="countdown-timer">
        <span class="countdown-number">{{ countdown }}</span>
        <span class="countdown-unit">秒</span>
      </div>
      <div v-else class="countdown-timer">
        <span class="countdown-text">等待后端倒计时...</span>
      </div>
      <a-progress v-if="countdown !== undefined" :percent="Math.max(0, Math.min(100, ((60 - countdown) / 60) * 100))"
        :show-info="false" :stroke-color="(countdown || 0) <= 10 ? '#ff4d4f' : '#1890ff'" :stroke-width="8"
        class="countdown-progress" />
      <div class="countdown-actions">
        <a-button type="primary" size="large" class="cancel-button" @click="handleCancel">
          取消操作
        </a-button>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Service } from '@/api'
import { subscribe, unsubscribe } from '@/composables/useWebSocket'
const logger = window.electronAPI.getLogger('全局电源倒计时')

// 响应式状态
const visible = ref(false)
const title = ref('')
const message = ref('')
const countdown = ref<number | undefined>(undefined)

// 倒计时定时器
let countdownTimer: ReturnType<typeof setInterval> | null = null
// WebSocket 订阅 ID
let subscriptionId: string | null = null

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

// 启动倒计时
const startCountdown = (data: any) => {
  logger.info(`启动倒计时: ${JSON.stringify(data)}`)

  // 清除之前的计时器
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }

  // 激活窗口到前台（即使在托盘状态）
  focusWindow()

  // 显示倒计时弹窗
  visible.value = true

  // 设置倒计时数据，从60秒开始
  title.value = data.title || '电源操作倒计时'
  message.value = data.message || '程序将在倒计时结束后执行电源操作'
  countdown.value = 60

  // 启动每秒倒计时
  countdownTimer = setInterval(() => {
    if (countdown.value !== undefined && countdown.value > 0) {
      countdown.value--
      logger.debug(`倒计时: ${countdown.value}`)

      // 倒计时结束
      if (countdown.value <= 0) {
        if (countdownTimer) {
          clearInterval(countdownTimer)
          countdownTimer = null
        }
        visible.value = false
        logger.info('倒计时结束，弹窗关闭')
      }
    }
  }, 1000)
}

// 取消电源操作
const handleCancel = async () => {
  logger.info('用户取消电源操作')

  // 清除倒计时器
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }

  // 关闭倒计时弹窗
  visible.value = false

  // 调用取消电源操作的API
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

// 清理函数
const cleanup = () => {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
  if (subscriptionId) {
    unsubscribe(subscriptionId)
    subscriptionId = null
  }
}

// 生命周期
onMounted(() => {
  // 直接订阅 Main 消息，处理倒计时
  subscriptionId = subscribe({ id: 'Main' }, (msg: any) => {
    if (!msg || typeof msg !== 'object') return

    const { type, data } = msg

    if (type === 'Message' && data && data.type === 'Countdown') {
      logger.info(`收到倒计时消息: ${JSON.stringify(data)}`)
      startCountdown(data)
    }
  })

  logger.info(`全局电源倒计时组件已挂载, subscriptionId: ${subscriptionId}`)
})

onUnmounted(() => {
  cleanup()
  logger.info('全局电源倒计时组件已卸载')
})
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

.countdown-text {
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
