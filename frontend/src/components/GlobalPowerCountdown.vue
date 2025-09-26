<template>
  <!-- 电源操作倒计时全屏弹窗 -->
  <div v-if="visible" class="power-countdown-overlay">
    <div class="power-countdown-container">
      <div class="countdown-content">
        <div class="warning-icon">⚠️</div>
        <h2 class="countdown-title">{{ title }}</h2>
        <p class="countdown-message">{{ message }}</p>
        <div class="countdown-timer" v-if="countdown !== undefined">
          <span class="countdown-number">{{ countdown }}</span>
          <span class="countdown-unit">秒</span>
        </div>
        <div class="countdown-timer" v-else>
          <span class="countdown-text">等待后端倒计时...</span>
        </div>
        <a-progress 
          v-if="countdown !== undefined"
          :percent="Math.max(0, Math.min(100, (60 - countdown) / 60 * 100))" 
          :show-info="false" 
          :stroke-color="(countdown || 0) <= 10 ? '#ff4d4f' : '#1890ff'"
          :stroke-width="8"
          class="countdown-progress"
        />
        <div class="countdown-actions">
          <a-button 
            type="primary" 
            size="large" 
            @click="handleCancel"
            class="cancel-button"
          >
            取消操作
          </a-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Service } from '@/api'
import { ExternalWSHandlers } from '@/composables/useWebSocket'

// 响应式状态
const visible = ref(false)
const title = ref('')
const message = ref('')
const countdown = ref<number | undefined>(undefined)

// 倒计时定时器
let countdownTimer: ReturnType<typeof setInterval> | null = null

// 启动倒计时
const startCountdown = (data: any) => {
  console.log('[GlobalPowerCountdown] 启动倒计时:', data)
  
  // 清除之前的计时器
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }

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
      console.log('[GlobalPowerCountdown] 倒计时:', countdown.value)

      // 倒计时结束
      if (countdown.value <= 0) {
        if (countdownTimer) {
          clearInterval(countdownTimer)
          countdownTimer = null
        }
        visible.value = false
        console.log('[GlobalPowerCountdown] 倒计时结束，弹窗关闭')
      }
    }
  }, 1000)
}

// 取消电源操作
const handleCancel = async () => {
  console.log('[GlobalPowerCountdown] 用户取消电源操作')
  
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
    console.log('[GlobalPowerCountdown] 电源操作已取消')
  } catch (error) {
    console.error('[GlobalPowerCountdown] 取消电源操作失败:', error)
  }
}

// 处理Main消息的函数
const handleMainMessage = (message: any) => {
  if (!message || typeof message !== 'object') return
  
  const { type, data } = message
  
  if (type === 'Message' && data && data.type === 'Countdown') {
    console.log('[GlobalPowerCountdown] 收到倒计时消息:', data)
    startCountdown(data)
  }
}

// 清理函数
const cleanup = () => {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

// 生命周期
onMounted(() => {
  // 替换全局Main消息处理器，添加倒计时处理
  const originalMainHandler = ExternalWSHandlers.mainMessage
  
  ExternalWSHandlers.mainMessage = (message: any) => {
    // 先调用原有的处理逻辑
    if (typeof originalMainHandler === 'function') {
      try {
        originalMainHandler(message)
      } catch (e) {
        console.warn('[GlobalPowerCountdown] 原有Main消息处理器出错:', e)
      }
    }
    
    // 然后处理倒计时消息
    handleMainMessage(message)
  }
  
  console.log('[GlobalPowerCountdown] 全局电源倒计时组件已挂载')
})

onUnmounted(() => {
  cleanup()
  console.log('[GlobalPowerCountdown] 全局电源倒计时组件已卸载')
})
</script>

<style scoped>
/* 电源操作倒计时全屏弹窗样式 */
.power-countdown-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  backdrop-filter: blur(8px);
  z-index: 10000; /* 确保在所有其他内容之上 */
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.3s ease-out;
}

.power-countdown-container {
  background: var(--ant-color-bg-container);
  border-radius: 16px;
  padding: 48px;
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.2);
  text-align: center;
  max-width: 500px;
  width: 90%;
  animation: slideIn 0.3s ease-out;
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
@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-20px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.1);
  }
}

/* 响应式 - 移动端适配 */
@media (max-width: 768px) {
  .power-countdown-container {
    padding: 32px 24px;
    margin: 16px;
  }

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