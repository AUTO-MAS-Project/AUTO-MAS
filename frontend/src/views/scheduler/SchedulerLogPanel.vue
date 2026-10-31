<template>
  <div class="scheduler-panel log-panel">
    <div class="scheduler-panel-header">
      <h3>{{ t('core.scheduler.log.title') }}</h3>
      <div class="log-controls">
        <a-space size="small">
          <a-select
            v-model:value="logThemeMode"
            size="small"
            class="log-theme-select"
            :aria-label="t('core.scheduler.log.theme')"
          >
            <a-select-option value="theme">{{
              t('core.scheduler.log.followTheme')
            }}</a-select-option>
            <a-select-option value="dark">{{ t('core.comp.darkTheme') }}</a-select-option>
            <a-select-option value="light">{{ t('core.comp.lightTheme') }}</a-select-option>
          </a-select>
          <a-button
            size="small"
            :type="logMode === 'follow' ? 'primary' : 'default'"
            @click="toggleLogMode"
          >
            {{
              logMode === 'follow' ? t('core.scheduler.log.follow') : t('core.scheduler.log.browse')
            }}
          </a-button>
        </a-space>
      </div>
    </div>
    <div
      ref="logContentRef"
      class="log-content"
      :class="{ 'log-locked': logMode === 'follow', 'log-dark': logIsDark }"
      :style="{ backgroundColor: logBackground, color: logForeground }"
    >
      <div v-if="!logContent" class="empty-state">
        <NoData :image-style="{ height: '80px' }" :description="false" />
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
import { useI18n } from 'vue-i18n'
import { useLogHighlight } from '@/composables/useLogHighlight'
import { useTheme } from '@/composables/useTheme'
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { useLocalStorage } from '@vueuse/core'
import { message, theme } from 'ant-design-vue'
import { computed, nextTick, onUnmounted, ref, toRefs, watch } from 'vue'

const { t } = useI18n()

interface Props {
  logContent: string
  externalLogMode?: 'follow' | 'browse' // 外部控制的日志模式
  // 日志首行在完整日志里的行号。后端只推最近一段日志，行号得接着完整日志排。
  // 调用方（scheduler/index.vue）保证一定给值，这里不再做第二层兜底。
  firstLine: number
}

// 日志显示模式类型
type LogMode = 'follow' | 'browse'
type LogThemeMode = 'theme' | 'dark' | 'light'

const props = defineProps<Props>()

// 解构 props 以便在模板中直接使用（保持响应性）
const { logContent } = toRefs(props)

const { isDark } = useTheme()
const { token } = theme.useToken()
const logger = window.electronAPI.getLogger('调度日志')
// 只保存日志面板的本地显示偏好，不改变应用主题。
const logThemeMode = useLocalStorage<LogThemeMode>('auto-mas.scheduler.log-theme', 'theme', {
  serializer: {
    read: value => (value === 'dark' || value === 'light' ? value : 'theme'),
    write: value => value,
  },
  onError: error => {
    logger.error(`保存日志主题失败: ${String(error)}`)
    message.error(t('core.scheduler.log.saveThemeFailed'))
  },
})
const logIsDark = computed(() =>
  logThemeMode.value === 'theme' ? isDark.value : logThemeMode.value === 'dark'
)
const logBackground = computed(() =>
  logThemeMode.value === 'theme'
    ? token.value.colorPrimaryBg
    : logIsDark.value
      ? '#1e1e1e'
      : '#ffffff'
)
const logForeground = computed(() => (logIsDark.value ? '#d4d4d4' : '#333333'))
const editorColors = computed(() => ({
  'editor.background': logBackground.value,
  'editor.foreground': logForeground.value,
  'editorGutter.background': logBackground.value,
}))

// 使用独立主题名，保留其他日志页面的配色。
const { registerLogLanguage, editorTheme, editorConfig, lightColors, darkColors, styles } =
  useLogHighlight({ name: 'scheduler-log', isDark: logIsDark, colors: editorColors })

const logContentRef = ref<HTMLElement | null>(null)

// 在编辑器挂载前注册语言
let monacoInstance: typeof import('monaco-editor') | null = null
const handleBeforeMount = (monaco: typeof import('monaco-editor')) => {
  monacoInstance = monaco
  registerLogLanguage(monaco)
}
const logMode = ref<LogMode>('follow')

watch([editorColors, lightColors, darkColors, styles], () => {
  if (monacoInstance) registerLogLanguage(monacoInstance)
})

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
  // 显示真实行号：后端只推最近一段日志，但编号要接着完整日志往下排，
  // 否则每轮都从 1 重数，和存下来的日志对不上
  lineNumbers: (lineNumber: number) => String(lineNumber + props.firstLine - 1),
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
  } else if (logContentRef.value) {
    logContentRef.value.scrollTop = logContentRef.value.scrollHeight
  }
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

onUnmounted(() => {
  editorInstance = null
  monacoInstance = null
})
</script>

<style scoped src="./schedulerPanel.css"></style>

<style scoped>
.scheduler-panel-header {
  flex-wrap: wrap;
  gap: 8px;
}

.scheduler-panel-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text-heading);
}

.log-controls {
  flex-shrink: 0;
}

.log-theme-select {
  width: 136px;
}

.log-content {
  --app-scrollbar-thumb: rgba(0, 0, 0, 0.28);
  --app-scrollbar-thumb-hover: rgba(0, 0, 0, 0.45);
  flex: 1;
  overflow: hidden;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace;
  font-size: 14px;
  line-height: 1.5;
  transition: all 0.2s ease;
}

/* 日志可以独立于应用切换深浅色，复用全局滚动条规则。 */
.log-content.log-dark {
  --app-scrollbar-thumb: rgba(255, 255, 255, 0.28);
  --app-scrollbar-thumb-hover: rgba(255, 255, 255, 0.45);
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

.empty-state-mini {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

@media (max-width: 768px) {
  .log-panel {
    border-radius: 8px;
  }

  .scheduler-panel-header {
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
</style>
