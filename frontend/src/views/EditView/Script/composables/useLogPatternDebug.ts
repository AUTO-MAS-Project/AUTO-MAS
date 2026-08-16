import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import { OpenAPI } from '@/api'
import type { PushLogPattern } from './usePushLogPatterns'

// TODO: OpenAPI 重新生成后，替换为生成的 Service.debugPatternApiSettingDebugPatternPost
async function debugPatternRequest(pattern: Record<string, unknown>, logText: string) {
  const baseURL = OpenAPI.BASE || ''
  const resp = await fetch(`${baseURL}/api/setting/debug_pattern`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pattern, logText }),
  })
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}`)
  }
  return resp.json()
}

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
  const filteredResults = computed(() =>
    results.value.filter(r => !onlyHit.value || r.hit),
  )
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
    const config = {
      type: pattern.type,
      match: pattern.match,
      head: pattern.head,
      headInclude: pattern.headInclude,
      tail: pattern.tail,
      tailInclude: pattern.tailInclude,
      extract: pattern.extract,
      start: pattern.start,
      end: pattern.end,
      maxLines: pattern.maxLines,
    }

    running.value = true
    compileError.value = null
    try {
      const data = (await debugPatternRequest(config, input.value)) as {
        code: number
        message?: string
        configError?: string
        results?: DebugResult[]
      }
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
