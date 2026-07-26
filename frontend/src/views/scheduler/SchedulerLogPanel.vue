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
    <div ref="logContentRef" class="log-content" :class="{ 'log-locked': logMode === 'follow' }">
      <div v-if="!logContent" class="empty-state">
        <EmptyState compact title="暂无日志" description="任务开始后，运行日志会显示在这里。" />
      </div>
      <div v-else-if="usePlainLog" ref="plainLogContainerRef" class="plain-log-container">
        <pre class="log-text">{{ logContent }}</pre>
      </div>
      <div v-else class="monaco-container">
        <vue-monaco-editor
          :value="logContent"
          language="logfile"
          :theme="editorTheme"
          :options="editorOptions"
          @before-mount="handleBeforeMount"
          @mount="handleEditorMount"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useLogHighlight } from '@/composables/useLogHighlight'
import EmptyState from '@/components/v6/EmptyState.vue'
import {
  computed,
  defineAsyncComponent,
  nextTick,
  onMounted,
  onUnmounted,
  ref,
  toRefs,
  watch,
} from 'vue'

// 异步加载，避免 4.2 MB 的 monaco chunk 成为本路由的静态依赖。
const VueMonacoEditor = defineAsyncComponent(() =>
  import('@guolao/vue-monaco-editor').then(module => module.VueMonacoEditor)
)

interface Props {
  logContent: string
  tabKey: string
  isLogAtBottom: boolean
  externalLogMode?: 'follow' | 'browse' // 外部控制的日志模式
}

interface Emits {
  (_e: 'scroll', _isAtBottom: boolean): void
  (_e: 'setRef', _el: HTMLElement | null, _key: string): void
}

// 日志显示模式类型
type LogMode = 'follow' | 'browse'

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// 解构 props 以便在模板中直接使用（保持响应性）
const { logContent, tabKey: _tabKey } = toRefs(props)
const LARGE_LOG_MONACO_THRESHOLD = 60000
const usePlainLog = computed(() => logContent.value.length > LARGE_LOG_MONACO_THRESHOLD)

// 使用日志高亮 composable
const { registerLogLanguage, editorTheme, editorConfig } = useLogHighlight()

const logContentRef = ref<HTMLElement | null>(null)
const plainLogContainerRef = ref<HTMLElement | null>(null)

// 在编辑器挂载前注册语言
const handleBeforeMount = (monaco: any) => {
  registerLogLanguage(monaco)
}
// 根据 isLogAtBottom 属性初始化模式
const logMode = ref<LogMode>('follow')

// 监听外部控制的日志模式变化
watch(
  () => props.externalLogMode,
  newMode => {
    if (newMode && logMode.value !== newMode) {
      logMode.value = newMode
      if (newMode === 'follow') {
        setTimeout(scrollToBottom, 10)
      }
    }
  }
)

watch(usePlainLog, plain => {
  if (plain) {
    editorInstance = null
  }
})

// Monaco Editor 实例
let editorInstance: any = null

// Monaco Editor 配置
const editorOptions = computed(() => ({
  readOnly: true,
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  fontSize: editorConfig.value.fontSize,
  fontFamily: 'SFMono-Regular, Consolas, Liberation Mono, Menlo, Courier, monospace',
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
  smoothScrolling: true,
  cursorBlinking: 'smooth' as const,
  unicodeHighlight: {
    ambiguousCharacters: false,
    invisibleCharacters: false,
  },
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
  } else if (plainLogContainerRef.value) {
    plainLogContainerRef.value.scrollTop = plainLogContainerRef.value.scrollHeight
  } else if (logContentRef.value) {
    logContentRef.value.scrollTop = logContentRef.value.scrollHeight
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
  container: scheduler-log / inline-size;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--v6-color-surface-transparent);
  border-radius: var(--v6-radius-card);
  box-shadow: var(--v6-shadow-card);
  border: 1px solid var(--v6-color-border-subtle);
  backdrop-filter: blur(18px) saturate(1.08);
  overflow: hidden;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: var(--v6-space-3) var(--v6-space-4);
  border-bottom: 1px solid var(--v6-color-border-subtle);
  flex-shrink: 0;
}

.section-header h3 {
  margin: 0;
  font-size: var(--v6-font-size-lg);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
}

.log-controls {
  flex-shrink: 0;
}

.log-content {
  flex: 1;
  overflow: hidden;
  font-family: var(--v6-font-mono);
  font-size: var(--v6-font-size-base);
  line-height: 1.5;
  transition: background-color var(--v6-motion-fast) var(--v6-ease-out);
}

.monaco-container {
  height: 100%;
  width: 100%;
}

.plain-log-container {
  height: 100%;
  overflow: auto;
  padding: var(--v6-space-3) var(--v6-space-4);
  background: transparent;
}

.monaco-container :deep(.monaco-editor) {
  height: 100% !important;
}

/* 保持最新模式：滚动条样式调整，表示锁定状态 */
.log-locked {
  position: relative;
}

.log-locked::-webkit-scrollbar-thumb {
  background-color: var(--v6-color-info);
  border-radius: var(--v6-radius-control);
}

.log-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--v6-color-text);
  font: inherit;
}

.empty-state-mini {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

/* .log-panel 自身规则须由外层 scheduler/index.vue 的 scheduler-log-host
   宿主容器驱动(@container 不能命中声明容器的元素自身) */
@container scheduler-log-host (max-width: 768px) {
  .log-panel {
    border-radius: var(--v6-radius-md);
  }
}

@container scheduler-log (max-width: 768px) {
  .section-header {
    padding: var(--v6-space-3);
  }

  .log-content {
    padding: var(--v6-space-3);
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
</style>
