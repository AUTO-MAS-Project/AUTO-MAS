import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'

const logger = window.electronAPI.getLogger('日志查看器')

export type LogSource = 'app' | 'frontend'
export type LogLevel = 'error' | 'warning' | 'info' | 'debug' | 'trace'
export type ConnectionState = 'connected' | 'disconnected' | 'reconnecting'

const LEVEL_PATTERNS: Record<LogLevel, RegExp> = {
  error: /\b(ERROR|FATAL|CRITICAL|SEVERE)\b/i,
  warning: /\b(WARN|WARNING)\b/i,
  info: /\b(INFO|INFORMATION|NOTICE)\b/i,
  debug: /\b(DEBUG)\b/i,
  trace: /\b(TRACE|VERBOSE|FINE|FINER|FINEST)\b/i,
}

const DEFAULT_MAX_LINES = 10000
const DEFAULT_REFRESH_INTERVAL = 2000
const TAIL_READ_LINES = 1000
const MAX_RETRIES = 5
const RETRY_BASE_DELAY = 1000

export interface UseLogViewerOptions {
  initialSource?: LogSource
  maxLines?: number
  refreshInterval?: number
}

export function useLogViewer(options: UseLogViewerOptions = {}) {
  const source = ref<LogSource>(options.initialSource ?? 'app')
  const maxLines = options.maxLines ?? DEFAULT_MAX_LINES
  const refreshInterval = options.refreshInterval ?? DEFAULT_REFRESH_INTERVAL

  const loading = ref(false)
  const error = ref<string | null>(null)
  const isRealtime = ref(true)
  const isPaused = ref(false)
  const viewCleared = ref(false)
  const keywordFilter = ref('')
  const levelFilter = ref<LogLevel | ''>('')
  const connectionState = ref<ConnectionState>('connected')
  const retryCount = ref(0)

  const rawLines = shallowRef<string[]>([])

  // ---- 可取消轮询 ----
  let refreshTimer: ReturnType<typeof setInterval> | null = null
  let mounted = true
  // 轮询 generation：每次 load() 调用递增，回调中检查是否过期
  let pollGeneration = 0
  // 截断检测：记录上次读取的内容尾部哈希
  let lastContentTail = ''

  const fileName = computed(() => (source.value === 'app' ? 'app.log' : 'frontend.log'))

  const filteredLines = computed(() => {
    const kw = keywordFilter.value.trim().toLowerCase()
    const level = levelFilter.value
    if (!kw && !level) return rawLines.value

    return rawLines.value.filter(line => {
      if (level && !LEVEL_PATTERNS[level].test(line)) return false
      if (kw && !line.toLowerCase().includes(kw)) return false
      return true
    })
  })

  // ---- 有界缓存 ----
  const applyBounds = (lines: string[]): string[] => {
    if (lines.length > maxLines) {
      return lines.slice(lines.length - maxLines)
    }
    return lines
  }

  const parseContent = (content: string): string[] => {
    if (!content) return []
    return content.split('\n')
  }

  // ---- 截断检测 ----
  const detectTruncation = (newContent: string): boolean => {
    if (!lastContentTail || !newContent) return false
    // 截断：新内容明显短于上次内容，且尾部不匹配
    if (newContent.length < lastContentTail.length * 0.5) {
      // 检查新内容尾部是否与旧内容尾部匹配
      const tailLen = Math.min(200, newContent.length)
      const newTail = newContent.slice(-tailLen)
      const oldTail = lastContentTail.slice(-tailLen)
      if (newTail !== oldTail) {
        return true
      }
    }
    return false
  }

  // ---- 增量合并 ----
  const mergeIncremental = (existing: string[], newLines: string[]): string[] => {
    if (existing.length === 0) return applyBounds(newLines)
    if (newLines.length === 0) return existing

    // 从尾部向前查找重叠，找到第一个新行
    const overlapWindow = Math.min(existing.length, newLines.length, 100)
    let overlapStart = -1

    for (let i = 1; i <= overlapWindow; i++) {
      const existingTail = existing[existing.length - i]
      const newHead = newLines[0]
      if (existingTail === newHead) {
        // 检查重叠窗口是否匹配
        const windowLen = Math.min(overlapWindow - i + 1, newLines.length)
        let match = true
        for (let j = 0; j < windowLen && i + j < existing.length && j < newLines.length; j++) {
          if (existing[existing.length - i + j] !== newLines[j]) {
            match = false
            break
          }
        }
        if (match) {
          overlapStart = i
          break
        }
      }
    }

    if (overlapStart > 0 && overlapStart <= existing.length) {
      // 找到重叠：保留 existing 的头部 + newLines 的全部（去重重叠部分）
      const merged = [...existing, ...newLines.slice(overlapStart)]
      return applyBounds(merged)
    }

    // 没有重叠：直接追加
    return applyBounds([...existing, ...newLines])
  }

  // ---- 核心加载 ----
  const load = async (silent = false): Promise<void> => {
    const gen = ++pollGeneration

    if (!silent) loading.value = true

    try {
      // 首次加载或截断后全量读取；增量轮询时只读尾部
      const isFirstLoad = rawLines.value.length === 0
      const linesToRead = isFirstLoad ? 0 : TAIL_READ_LINES

      const content = await window.electronAPI?.getLogs?.(linesToRead, fileName.value)

      // generation 过期检查
      if (!mounted || gen !== pollGeneration) return

      if (typeof content !== 'string') {
        error.value = '日志读取失败：返回内容为空'
        connectionState.value = 'disconnected'
        stopRealtime()
        return
      }

      // 截断检测
      if (!isFirstLoad && detectTruncation(content)) {
        logger.warn('检测到日志文件截断，重新全量加载')
        lastContentTail = ''
        rawLines.value = []
        // 递归调用全量加载
        pollGeneration = gen // 保持 generation
        try {
          await loadFull(silent)
        } catch {
          // loadFull 内部已设置 error，此处只需确保状态一致
          if (mounted && gen === pollGeneration) {
            connectionState.value = 'disconnected'
            stopRealtime()
          }
        }
        return
      }

      const newLines = parseContent(content)

      if (isFirstLoad) {
        rawLines.value = applyBounds(newLines)
      } else {
        rawLines.value = mergeIncremental(rawLines.value, newLines)
      }
      viewCleared.value = false

      // 更新截断检测尾部
      lastContentTail = content.length > 500 ? content.slice(-500) : content

      error.value = null
      connectionState.value = 'connected'
      retryCount.value = 0
    } catch (err) {
      if (!mounted || gen !== pollGeneration) return
      const msg = err instanceof Error ? err.message : String(err)
      logger.error(`加载日志失败: ${msg}`)
      error.value = msg
      connectionState.value = 'disconnected'
      stopRealtime()
    } finally {
      if (mounted && gen === pollGeneration && !silent) {
        loading.value = false
      }
    }
  }

  // 全量加载（用于截断恢复）
  const loadFull = async (silent = false): Promise<void> => {
    const gen = ++pollGeneration
    if (!silent) loading.value = true

    try {
      const content = await window.electronAPI?.getLogs?.(0, fileName.value)
      if (!mounted || gen !== pollGeneration) return

      if (typeof content === 'string') {
        rawLines.value = applyBounds(parseContent(content))
        viewCleared.value = false
        lastContentTail = content.length > 500 ? content.slice(-500) : content
        error.value = null
        connectionState.value = 'connected'
        retryCount.value = 0
      }
    } catch (err) {
      if (!mounted || gen !== pollGeneration) return
      const msg = err instanceof Error ? err.message : String(err)
      error.value = msg
      // 不在此处设置 connectionState='disconnected'：
      // - load() 的 catch 已负责设置
      // - retry() 自行管理状态，loadFull 不应覆盖
    } finally {
      if (mounted && gen === pollGeneration && !silent) {
        loading.value = false
      }
    }
  }

  // ---- 重连逻辑 ----
  const retry = async (): Promise<void> => {
    if (connectionState.value === 'connected') return
    connectionState.value = 'reconnecting'
    error.value = null

    const attempt = async (delay: number, count: number) => {
      if (!mounted || connectionState.value !== 'reconnecting') return
      if (count >= MAX_RETRIES) {
        connectionState.value = 'disconnected'
        error.value = `重连失败：已尝试 ${MAX_RETRIES} 次`
        return
      }

      retryCount.value = count + 1
      await new Promise(resolve => setTimeout(resolve, delay))

      if (!mounted || connectionState.value !== 'reconnecting') return

      // loadFull 内部捕获错误不抛出，需通过 connectionState 判断结果
      await loadFull(true)
      if ((connectionState.value as ConnectionState) === 'connected') {
        if (isRealtime.value) {
          startRealtime()
        }
        return
      }
      // loadFull 未设置 connected（失败），指数退避重试
      const nextDelay = Math.min(delay * 2, 30000)
      await attempt(nextDelay, count + 1)
    }

    await attempt(RETRY_BASE_DELAY, 0)
  }

  // ---- 实时轮询 ----
  const startRealtime = () => {
    stopRealtime()
    if (!mounted) return
    refreshTimer = setInterval(() => {
      if (connectionState.value === 'disconnected') return
      load(true)
    }, refreshInterval)
  }

  const stopRealtime = () => {
    if (refreshTimer) {
      clearInterval(refreshTimer)
      refreshTimer = null
    }
  }

  const toggleRealtime = async () => {
    isRealtime.value = !isRealtime.value
    if (isRealtime.value) {
      if (connectionState.value === 'disconnected') {
        await retry()
      } else {
        await load()
        startRealtime()
      }
    } else {
      stopRealtime()
    }
  }

  const togglePause = () => {
    isPaused.value = !isPaused.value
  }

  const clearView = () => {
    // 仅清空当前查看器，不删除磁盘日志；同时停止轮询，避免下一轮立即回填。
    pollGeneration += 1
    stopRealtime()
    isRealtime.value = false
    isPaused.value = false
    viewCleared.value = true
    rawLines.value = []
    lastContentTail = ''
    error.value = null
    connectionState.value = 'connected'
    retryCount.value = 0
  }

  const setSource = (value: LogSource) => {
    source.value = value
  }

  const setKeyword = (value: string) => {
    keywordFilter.value = value
  }

  const setLevel = (value: LogLevel | '') => {
    levelFilter.value = value
  }

  interface ExportResult {
    success: boolean
    message?: string
    error?: string
    zipPath?: string
  }

  const exportLogs = async (): Promise<ExportResult> => {
    try {
      const result = await window.electronAPI?.exportLogs?.()
      if (!result) {
        const msg = '导出日志失败: 未收到响应'
        logger.error(msg)
        return { success: false, error: msg }
      }
      if (result.success && result.zipPath) {
        await window.electronAPI?.showItemInFolder?.(result.zipPath)
      }
      return {
        success: result.success,
        message: result.message,
        error: result.error,
        zipPath: result.zipPath,
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      logger.error(`导出日志失败: ${msg}`)
      return { success: false, error: msg }
    }
  }

  const copyLines = async (lines: string[]): Promise<boolean> => {
    const text = lines.join('\n')
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      const textarea = document.createElement('textarea')
      textarea.value = text
      document.body.appendChild(textarea)
      textarea.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(textarea)
      return ok
    }
  }

  // ---- 源切换 ----
  watch(source, () => {
    lastContentTail = ''
    rawLines.value = []
    error.value = null
    viewCleared.value = false
    load()
  })

  onMounted(() => {
    load()
    if (isRealtime.value) {
      startRealtime()
    }
  })

  onUnmounted(() => {
    mounted = false
    stopRealtime()
  })

  return {
    source,
    loading,
    error,
    isRealtime,
    isPaused,
    viewCleared,
    keywordFilter,
    levelFilter,
    connectionState,
    retryCount,
    rawLines,
    filteredLines,
    fileName,
    load,
    retry,
    startRealtime,
    stopRealtime,
    toggleRealtime,
    togglePause,
    clearView,
    setSource,
    setKeyword,
    setLevel,
    exportLogs,
    copyLines,
  }
}
