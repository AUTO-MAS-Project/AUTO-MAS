import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  ActionService,
  type PatternDebugIn,
  type PushLogPattern as ApiPushLogPattern,
} from '@/api'
import type { PushLogPattern } from './usePushLogPatterns'

export interface DebugResult {
  idx: number
  hit: boolean
  extracted: string
  line: string
  error?: string | null
}

export interface UseLogPatternDebugOptions {
  logPath?: string | (() => string | undefined)
}

export function useLogPatternDebug(options: UseLogPatternDebugOptions = {}) {
  const { logPath } = options
  const resolveLogPath = (): string | undefined =>
    typeof logPath === 'function' ? logPath() : logPath

  const modalOpen = ref(false)
  const input = ref('')
  const results = ref<DebugResult[]>([])
  const compileError = ref<string | null>(null)
  const running = ref(false)
  const loadingLog = ref(false)
  const onlyHit = ref(false)
  const logLines = ref(500)
  const currentPattern = ref<PushLogPattern | null>(null)

  const hitCount = computed(() => results.value.filter(r => r.hit).length)
  const filteredResults = computed(() => results.value.filter(r => !onlyHit.value || r.hit))
  const isMultiline = computed(() => currentPattern.value?.type === 'multiline')

  const open = (pattern: PushLogPattern) => {
    currentPattern.value = pattern
    input.value = ''
    results.value = []
    compileError.value = null
    modalOpen.value = true
  }

  const clear = () => {
    input.value = ''
    results.value = []
    compileError.value = null
  }

  const close = () => {
    modalOpen.value = false
  }

  const runDebug = async () => {
    if (!currentPattern.value) return
    const pattern = currentPattern.value

    running.value = true
    compileError.value = null
    try {
      const body: PatternDebugIn = {
        // 本地类型含 _uid 且 type 为字符串联合，与生成的 PushLogPattern[type] 命名空间
        // 枚举存在类型差异，仅在组装请求体时做一次边界转换，复用生成契约避免重复定义
        pattern: pattern as ApiPushLogPattern,
        logText: input.value,
      }
      const data = await ActionService.debugPatternApiApiSettingDebugPatternPost(body)
      if (data.code !== 200) {
        compileError.value = data.message || '调试请求失败'
        results.value = []
        return
      }
      if (data.configError) {
        compileError.value = data.configError
        results.value = []
        return
      }
      results.value = (data.results || []).map(r => ({
        idx: r.idx,
        hit: r.hit,
        extracted: r.extracted || '',
        line: r.line || '',
        error: r.error || null,
      }))
    } catch (error) {
      compileError.value = '调试请求失败: ' + (error as Error).message
      results.value = []
    } finally {
      running.value = false
    }
  }

  const loadLog = async () => {
    const logPath = resolveLogPath()
    if (!logPath || logPath === '.') {
      message.warning('请先在脚本配置中设置日志文件路径')
      return
    }
    try {
      loadingLog.value = true
      const content = await window.electronAPI.readFile(logPath)
      if (!content) {
        message.warning('日志文件为空或无法读取')
        return
      }
      const allLines = content.split('\n')
      const n = logLines.value
      const lines = n < 0 ? allLines : allLines.slice(Math.max(0, allLines.length - n))
      input.value = lines.join('\n')
      message.success(`已加载 ${lines.length} 行日志（共 ${allLines.length} 行）`)
    } catch (error) {
      message.error('加载日志文件失败: ' + (error as Error).message)
    } finally {
      loadingLog.value = false
    }
  }

  return {
    modalOpen,
    input,
    results,
    compileError,
    running,
    loadingLog,
    onlyHit,
    logLines,
    currentPattern,
    isMultiline,
    hitCount,
    filteredResults,
    open,
    clear,
    close,
    runDebug,
    loadLog,
  }
}
