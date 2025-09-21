<template>
  <div class="log-panel">
    <div class="section-header">
      <h3>日志</h3>
      <div class="log-controls">
        <a-space size="small">
          <a-button 
            @click="toggleLogMode" 
            size="small"
            :type="logMode === 'follow' ? 'primary' : 'default'"
          >
            {{ logMode === 'follow' ? '跟随模式' : '自由浏览' }}
          </a-button>
        </a-space>
      </div>
    </div>
    <div class="log-content" ref="logContentRef" @scroll="onScroll">
      <div v-if="!logContent" class="empty-state-mini">
        <a-empty description="暂无日志信息" />
      </div>
      <pre v-else class="log-text">{{ logContent }}</pre>
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
// 默认为跟随模式
const logMode = ref<LogMode>('follow')


const toggleLogMode = () => {
  logMode.value = logMode.value === 'follow' ? 'browse' : 'follow'
  // 切换到跟随模式时，自动滚动到底部
  if (logMode.value === 'follow') {
    nextTick(() => {
      scrollToBottom()
    })
  }
}

const scrollToBottom = () => {
  if (logContentRef.value) {
    logContentRef.value.scrollTop = logContentRef.value.scrollHeight
  }
}

const onScroll = () => {
  if (logContentRef.value) {
    const { scrollTop, scrollHeight, clientHeight } = logContentRef.value
    const isAtBottom = Math.abs(scrollHeight - clientHeight - scrollTop) < 1
    emit('scroll', isAtBottom)
  }
}

// 监听日志变化，根据模式决定是否自动滚动
watch(
  () => props.logContent,
  () => {
    nextTick(() => {
      // 跟随模式下自动滚动到底部
      if (logMode.value === 'follow' && logContentRef.value) {
        scrollToBottom()
      }
    })
  }
)

// 组件挂载时设置引用
onMounted(() => {
  if (logContentRef.value) {
    emit('setRef', logContentRef.value, props.tabKey)
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
</style>