<template>
  <div class="popup-container" :data-theme="isDark ? 'dark' : 'light'">
    <div class="popup-content">
      <div class="popup-header">
        <h3 class="popup-title">{{ title }}</h3>
      </div>

      <div class="popup-body">
        <p class="popup-message">{{ message }}</p>
      </div>

      <div class="popup-footer">
        <button
          v-for="(option, index) in options"
          :key="index"
          class="popup-button"
          :class="{ primary: index === 0, default: index !== 0 }"
          @click="handleChoice(index === 0)"
        >
          {{ option }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useTheme } from '@/composables/useTheme'

defineOptions({
  name: 'PopupDialog',
})

const route = useRoute()
const { isDark } = useTheme()

const title = ref('操作确认')
const message = ref('是否要执行此操作？')
const options = ref(['确定', '取消'])
const messageId = ref('')

onMounted(() => {
  // 从路由参数中读取对话框数据
  const data = route.query.data as string
  if (data) {
    try {
      const dialogData = JSON.parse(decodeURIComponent(data))
      title.value = dialogData.title || '操作确认'
      message.value = dialogData.message || '是否要执行此操作？'
      options.value = dialogData.options || ['确定', '取消']
      messageId.value = dialogData.messageId || ''
    } catch (error) {
      console.error('解析对话框数据失败:', error)
    }
  }

  // 添加键盘监听
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  // 清理键盘监听
  window.removeEventListener('keydown', handleKeydown)
})

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter') {
    // Enter 键确认（选择第一个选项）
    event.preventDefault()
    handleChoice(true)
  } else if (event.key === 'Escape') {
    // Esc 键取消（选择第二个选项）
    event.preventDefault()
    handleChoice(false)
  }
}

const handleChoice = async (choice: boolean) => {
  if (messageId.value) {
    try {
      await window.electronAPI.dialogResponse(messageId.value, choice)
      // 窗口会被主进程关闭，不需要手动导航
    } catch (error) {
      console.error('发送对话框响应失败:', error)
    }
  }
}
</script>

<style scoped>
:root {
  /* 亮色模式变量 */
  --primary-color: #1677ff;
  --primary-hover: #4096ff;
  --primary-active: #0958d9;
  --danger-color: #ff4d4f;
  --danger-hover: #ff7875;
  --danger-active: #d9363e;

  --text-primary: #262626;
  --text-secondary: #595959;
  --text-tertiary: #8c8c8c;

  --bg-primary: #ffffff;
  --bg-secondary: #fafafa;
  --bg-tertiary: #f5f5f5;

  --border-primary: #d9d9d9;
  --border-secondary: #f0f0f0;
  --border-hover: #4096ff;

  --radius-sm: 6px;
  --radius-md: 8px;
}

.popup-container {
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  position: fixed;
  top: 0;
  left: 0;
}

.popup-container[data-theme='dark'] {
  --primary-color: #1668dc;
  --primary-hover: #3c89e8;
  --primary-active: #1554ad;

  --text-primary: #ffffff;
  --text-secondary: #c9cdd4;
  --text-tertiary: #a6adb4;

  --bg-primary: #1f1f1f;
  --bg-secondary: #2a2a2a;
  --bg-tertiary: #373737;

  --border-primary: #434343;
  --border-secondary: #303030;
  --border-hover: #3c89e8;
}

.popup-content {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-primary);
  box-shadow:
    0 10px 15px -3px rgba(0, 0, 0, 0.3),
    0 4px 6px -2px rgba(0, 0, 0, 0.2);
  animation: popup-scale-in 0.15s ease-out;
}

@keyframes popup-scale-in {
  from {
    transform: scale(0.95);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

.popup-header {
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--border-secondary);
}

.popup-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  text-align: center;
}

.popup-body {
  flex: 1;
  padding: 20px 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow-y: auto;
}

.popup-message {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  margin: 0;
  word-wrap: break-word;
  white-space: pre-wrap;
  text-align: center;
  max-width: 100%;
}

.popup-footer {
  padding: 10px 16px 14px;
  display: flex;
  justify-content: center;
  gap: 10px;
  border-top: 1px solid var(--border-secondary);
}

.popup-button {
  padding: 6px 14px;
  height: 30px;
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s cubic-bezier(0.645, 0.045, 0.355, 1);
  min-width: 70px;
  outline: none;
}

.popup-button.primary {
  background: var(--primary-color);
  border-color: var(--primary-color);
  color: #ffffff;
}

.popup-button.primary:hover {
  background: var(--primary-hover);
  border-color: var(--primary-hover);
}

.popup-button.primary:active {
  background: var(--primary-active);
  border-color: var(--primary-active);
}

.popup-button.default:hover {
  background: var(--bg-tertiary);
  border-color: var(--border-hover);
  color: var(--primary-color);
}

.popup-button:focus {
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.2);
  border-color: var(--border-hover);
}

.popup-button:active {
  transform: translateY(1px);
}
</style>
