<template>
  <div class="log-panel">
    <div class="section-header">
      <h3>日志</h3>
      <div class="log-controls">
        <a-space size="small">
          <a-button size="small" :type="logMode === 'follow' ? 'primary' : 'default'" @click="toggleLogMode">
            {{ logMode === 'follow' ? '保持最新' : '自由浏览' }}
          </a-button>
        </a-space>
      </div>
    </div>
    <div ref="logContentRef" class="log-content" :class="{ 'log-locked': logMode === 'follow' }">
      <div v-if="!logContent" class="empty-state">
        <div class="empty-content">
          <div class="empty-image-container">
            <img src="@/assets/NoData.png" alt="暂无数据" class="empty-image" />
          </div>
        </div>
      </div>
      <div v-else class="monaco-container">
        <vue-monaco-editor :value="logContent" language="logfile" :theme="editorTheme" :options="editorOptions"
          @before-mount="handleBeforeMount" @mount="handleEditorMount" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useLogHighlight } from '@/composables/useLogHighlight'
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { computed, nextTick, onMounted, onUnmounted, ref, toRefs, watch } from 'vue'

interface Props {
  logContent: string
  tabKey: string
  isLogAtBottom: boolean
  externalLogMode?: 'follow' | 'browse' // 外部控制的日志模式
}

interface Emits {
  (e: 'scroll', isAtBottom: boolean): void
  (e: 'setRef', el: HTMLElement | null, key: string): void
}

// 日志显示模式类型
type LogMode = 'follow' | 'browse'

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// 解构 props 以便在模板中直接使用（保持响应性）
const { logContent, tabKey } = toRefs(props)

// 使用日志高亮 composable
const { registerLogLanguage, editorTheme, editorConfig } = useLogHighlight()

const logContentRef = ref<HTMLElement | null>(null)

// 在编辑器挂载前注册语言
const handleBeforeMount = (monaco: any) => {
  registerLogLanguage(monaco)
}
// 根据 isLogAtBottom 属性初始化模式
const logMode = ref<LogMode>('follow')

// 监听外部控制的日志模式变化
watch(
  () => props.externalLogMode,
  (newMode) => {
    if (newMode && logMode.value !== newMode) {
      logMode.value = newMode
      if (newMode === 'follow') {
        setTimeout(handleAutoScroll, 10)
      }
    }
  }
)

// Monaco Editor 实例
let editorInstance: any = null

// Monaco Editor 配置
const editorOptions = computed(() => ({
  readOnly: true,
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  fontSize: editorConfig.value.fontSize,
  fontFamily: editorConfig.value.fontFamily,
  lineHeight: editorConfig.value.lineHeight * editorConfig.value.fontSize,
  lineNumbers: 'on' as const,
  wordWrap: 'on' as const,
  automaticLayout: true,
  scrollbar: {
    vertical: 'visible' as const,
    horizontal: 'visible' as const,
    useShadows: false,
    verticalScrollbarSize: 10,
    horizontalScrollbarSize: 10,
  },
  renderWhitespace: 'none' as const,
  contextmenu: true,
  folding: false,
  renderLineHighlight: 'none' as const,
  occurrencesHighlight: 'off' as const,
  codeLens: false,
  lightbulb: { enabled: 'off' as const },
  smoothScrolling: true,
  cursorBlinking: 'smooth' as const,
}))

// 处理编辑器挂载
const handleEditorMount = (editor: any) => {
  editorInstance = editor
  // 初始滚动到底部
  if (logMode.value === 'follow' && props.logContent) {
    nextTick(() => scrollToBottom())
  }
}

const toggleLogMode = () => {
  if (logMode.value === 'follow') {
    // 从保持最新切换到自由浏览
    logMode.value = 'browse'
  } else {
    // 从自由浏览切换到保持最新
    logMode.value = 'follow'
    // 简单延迟滚动，避免nextTick的递归风险
    setTimeout(scrollToBottom, 10)
  }
}

// 滚动到底部
const scrollToBottom = () => {
  if (editorInstance) {
    const lineCount = editorInstance.getModel()?.getLineCount()
    if (lineCount) {
      editorInstance.revealLine(lineCount)
      editorInstance.setScrollTop(editorInstance.getScrollHeight())
    }
  }
  emit('scroll', true)
}

// 只监听日志内容变化
watch(
  () => props.logContent,
  () => {
    if (logMode.value === 'follow') {
      // 使用简单的延迟，避免nextTick可能导致的递归
      setTimeout(scrollToBottom, 10)
    }
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
  editorInstance = null
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
  overflow: hidden;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace;
  font-size: 14px;
  line-height: 1.5;
  transition: all 0.2s ease;
}

.monaco-container {
  height: 100%;
  width: 100%;
}

.monaco-container :deep(.monaco-editor) {
  height: 100% !important;
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
