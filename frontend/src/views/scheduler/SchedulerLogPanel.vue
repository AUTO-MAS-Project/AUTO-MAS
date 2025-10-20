<template>
  <div class="log-panel">
    <div class="section-header">
      <h3>日志</h3>
      <div class="log-controls">
        <a-space size="small">
          <a-button
            size="small"
            :type="logMode === 'follow' ? 'primary' : 'default'"
            @click="toggleLogMode"
          >
            {{ logMode === 'follow' ? '保持最新' : '自由浏览' }}
          </a-button>
        </a-space>
      </div>
    </div>
    <div 
      ref="logContentRef" 
      class="log-content" 
      :class="{ 'log-locked': logMode === 'follow' }"
      @scroll="onScroll"
    >
      <div v-if="!logContent" class="empty-state">
        <div class="empty-content">
          <div class="empty-image-container">
            <img src="@/assets/NoData.png" alt="暂无数据" class="empty-image" />
          </div>
        </div>
      </div>
      <pre v-else class="log-text" :key="logContent.length">{{ logContent }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch, onMounted, onUnmounted } from 'vue'

interface Props {
  logContent: string
  tabKey: string
  isLogAtBottom: boolean
}

interface Emits {
  (e: 'scroll', isAtBottom: boolean): void
  (e: 'setRef', el: HTMLElement | null, key: string): void
}

// 日志显示模式类型
type LogMode = 'follow' | 'browse'

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const logContentRef = ref<HTMLElement | null>(null)
// 根据 isLogAtBottom 属性初始化模式
const logMode = ref<LogMode>('follow')

const toggleLogMode = () => {
  if (logMode.value === 'follow') {
    // 从保持最新切换到自由浏览
    logMode.value = 'browse'
  } else {
    // 从自由浏览切换到保持最新
    logMode.value = 'follow'
    // 简单延迟滚动，避免nextTick的递归风险
    setTimeout(handleAutoScroll, 10)
  }
}

// 简化的滚动函数
const scrollToBottom = () => {
  if (logContentRef.value) {
    logContentRef.value.scrollTop = logContentRef.value.scrollHeight
    emit('scroll', true)
  }
}

const onScroll = () => {
  if (!logContentRef.value) return
  
  const { scrollTop, scrollHeight, clientHeight } = logContentRef.value
  const isAtBottom = Math.abs(scrollHeight - clientHeight - scrollTop) < 5
  
  // 保持最新模式：锁定在底部
  if (logMode.value === 'follow') {
    // 如果不在底部，立即滚动回底部（不使用任何异步方法）
    if (!isAtBottom) {
      logContentRef.value.scrollTop = logContentRef.value.scrollHeight
    }
    emit('scroll', true)
  } else {
    // 自由浏览模式：正常响应
    emit('scroll', isAtBottom)
  }
}

// 使用一个统一的滚动处理函数，避免多个watch造成递归
const handleAutoScroll = () => {
  if (logMode.value === 'follow' && logContentRef.value && props.logContent) {
    logContentRef.value.scrollTop = logContentRef.value.scrollHeight
  }
}

// 只监听日志内容变化
watch(
  () => props.logContent,
  () => {
    if (logMode.value === 'follow') {
      // 使用简单的延迟，避免nextTick可能导致的递归
      setTimeout(handleAutoScroll, 10)
    }
  }
)

// 移除 watchEffect 避免与 watch 产生递归冲突

// 组件挂载时设置引用
onMounted(() => {
  if (logContentRef.value) {
    emit('setRef', logContentRef.value, props.tabKey)
    
    // 简单的初始滚动
    if (logMode.value === 'follow' && props.logContent) {
      setTimeout(handleAutoScroll, 100)
    }
  }
})

// 组件卸载前清理引用
onUnmounted(() => {
  emit('setRef', null, props.tabKey)
})
</script>

<style scoped>
.log-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--ant-color-bg-container);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 12px 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  flex-shrink: 0;
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text-heading);
}

.log-controls {
  flex-shrink: 0;
}

.log-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace;
  font-size: 14px;
  line-height: 1.5;
  transition: all 0.2s ease;
}

/* 保持最新模式：滚动条样式调整，表示锁定状态 */
.log-locked {
  position: relative;
}

.log-locked::-webkit-scrollbar-thumb {
  background-color: var(--ant-color-primary) !important;
  border-radius: 6px;
}



.log-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--ant-color-text);
}

.empty-state-mini {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

/* 暗色模式适配 */
@media (prefers-color-scheme: dark) {
  .log-panel {
    background: var(--ant-color-bg-container, #1f1f1f);
    border: 1px solid var(--ant-color-border, #424242);
  }

  .section-header {
    border-bottom: 1px solid var(--ant-color-border, #424242);
  }

  .log-text {
    color: var(--ant-color-text, #ffffff);
  }
}

@media (max-width: 768px) {
  .log-panel {
    border-radius: 8px;
  }

  .section-header {
    padding: 12px;
  }

  .log-content {
    padding: 12px;
  }
}

/* 空状态样式 */
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 200px;
  text-align: center;
}

.empty-content {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.empty-image-container {
  margin-bottom: 16px;
}

.empty-image {
  width: 80px;
  height: auto;
  opacity: 0.6;
}

.empty-title {
  font-size: 16px;
  font-weight: 500;
  margin: 0 0 4px 0;
  color: var(--ant-color-text);
}

.empty-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0;
}
</style>
