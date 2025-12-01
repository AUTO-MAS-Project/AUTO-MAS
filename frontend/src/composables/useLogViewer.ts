/**
 * 日志查看器组合式函数
 * 提供日志查看的响应式API
 * 支持日志过滤、搜索和级别控制
 */

import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { message } from 'ant-design-vue'
// 直接定义类型，避免导入问题
type LogLevel = 'TRACE' | 'DEBUG' | 'INFO' | 'WARN' | 'ERROR' | 'CRITICAL' | 'SUCCESS'
type LogSource = 'backend' | 'frontend' | 'system'

interface ParsedLogEntry {
    id?: string
    timestamp: Date
    level: LogLevel
    module: string
    message: string
    source?: LogSource
    originalLog?: string
    isValid?: boolean
    parseError?: string
    coloredLog?: string
    metadata?: Record<string, any>
}

interface LogFilterConditions {
    levels?: LogLevel[]
    modules?: string[]
    timeRange?: [Date, Date]
    keywords?: string[]
    sources?: LogSource[]
}

// 日志查看器配置接口
export interface LogViewerConfig {
    enableVirtualScroll?: boolean
    itemHeight?: number
    bufferSize?: number
    autoRefresh?: boolean
    refreshInterval?: number
    maxLogs?: number
}

// 日志查看器状态接口
export interface LogViewerState {
    logs: ParsedLogEntry[]
    loading: boolean
    error: string | null
    selectedLogLevel: string
    selectedSource: string
    searchKeyword: string
    enableColorHighlight: boolean
    autoScroll: boolean
    stats: {
        total: number
        filtered: number
        byLevel: Record<string, number>
        bySource: Record<string, number>
    }
}

// 日志查看器操作接口
export interface LogViewerActions {
    refresh: () => Promise<void>
    clear: () => Promise<void>
    export: (format?: string) => Promise<void>
    subscribe: (id: string, filter?: LogFilterConditions) => Promise<void>
    unsubscribe: (id: string) => Promise<void>
    selectLog: (log: ParsedLogEntry, index: number) => void
    scrollToTop: () => void
    scrollToBottom: () => void
    toggleAutoScroll: () => void
}

// 默认配置
const DEFAULT_CONFIG: LogViewerConfig = {
    enableVirtualScroll: true,
    itemHeight: 30,
    bufferSize: 5,
    autoRefresh: false,
    refreshInterval: 2000,
    maxLogs: 10000
}

/**
 * 日志查看器组合式函数
 */
export function useLogViewer(config: LogViewerConfig = {}) {
    // 合并配置
    const finalConfig = { ...DEFAULT_CONFIG, ...config }

    // 响应式状态
    const logs = ref<ParsedLogEntry[]>([])
    const loading = ref(false)
    const error = ref<string | null>(null)
    const selectedLogLevel = ref<string>('')
    const selectedSource = ref<string>('')
    const searchKeyword = ref<string>('')
    const enableColorHighlight = ref<boolean>(true)
    const autoScroll = ref<boolean>(true)
    const subscriberId = ref<string>(`log-viewer-${Date.now()}`)

    // 计算属性
    const filteredLogs = computed(() => {
        let result = logs.value

        // 按级别过滤
        if (selectedLogLevel.value) {
            result = result.filter(log => log.level === selectedLogLevel.value)
        }

        // 按来源过滤
        if (selectedSource.value) {
            result = result.filter(log => log.source === selectedSource.value)
        }

        // 按关键词搜索
        if (searchKeyword.value) {
            const keyword = searchKeyword.value.toLowerCase()
            result = result.filter(log =>
                log.message.toLowerCase().includes(keyword) ||
                log.module.toLowerCase().includes(keyword) ||
                log.level.toLowerCase().includes(keyword)
            )
        }

        return result
    })

    const stats = computed(() => {
        const levelStats: Record<string, number> = {}
        const sourceStats: Record<string, number> = {}

        // 统计各级别日志数量
        logs.value.forEach(log => {
            levelStats[log.level] = (levelStats[log.level] || 0) + 1
            sourceStats[log.source || 'unknown'] = (sourceStats[log.source || 'unknown'] || 0) + 1
        })

        return {
            total: logs.value.length,
            filtered: filteredLogs.value.length,
            byLevel: levelStats,
            bySource: sourceStats
        }
    })

    const hasLogs = computed(() => logs.value.length > 0)
    const hasFilteredLogs = computed(() => filteredLogs.value.length > 0)
    const isEmpty = computed(() => !hasLogs.value && !loading.value)

    // 日志级别选项
    const logLevels = computed(() => {
        const levels = new Set<string>()
        logs.value.forEach(log => levels.add(log.level))
        return Array.from(levels).sort()
    })

    // 日志来源选项
    const logSources = computed(() => {
        const sources = new Set<string>()
        logs.value.forEach(log => {
            if (log.source) {
                sources.add(log.source)
            }
        })
        return Array.from(sources).sort()
    })

    // 操作方法
    const refresh = async () => {
        loading.value = true
        error.value = null

        try {
            if (window.electronAPI?.logManagement) {
                const result = await window.electronAPI.logManagement.getLogs()
                if (result.success) {
                    // 恢复后端日志显示支持
                    logs.value = result.data || []
                } else {
                    throw new Error(result.error || '获取日志失败')
                }
            } else {
                // 降级到原有API
                const logContent = await window.electronAPI.getLogs(finalConfig.maxLogs)
                if (logContent) {
                    // 这里需要解析日志内容为ParsedLogEntry数组
                    // 简化处理，按行分割
                    const lines = logContent.split('\n').filter(line => line.trim())
                    const parsedLogs: ParsedLogEntry[] = lines.map((line, index) => ({
                        id: `log-${index}`,
                        timestamp: new Date(),
                        level: 'INFO' as LogLevel,
                        module: '前端',
                        message: line,
                        source: 'frontend' as LogSource,
                        originalLog: line,
                        isValid: true
                    }))
                    logs.value = parsedLogs
                }
            }
        } catch (err) {
            error.value = err instanceof Error ? err.message : String(err)
            console.error('刷新日志失败', error.value || '未知错误')
        } finally {
            loading.value = false
        }
    }

    const clear = async () => {
        try {
            if (window.electronAPI?.logManagement) {
                const result = await window.electronAPI.logManagement.clearLogs()
                if (result.success) {
                    logs.value = []
                    message.success('日志已清空')
                } else {
                    throw new Error(result.error || '清空日志失败')
                }
            } else {
                // 降级到原有API
                await window.electronAPI.clearLogs()
                logs.value = []
                message.success('日志已清空')
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : String(err)
            console.error('清空日志失败', errorMessage || '未知错误')
        }
    }

    const exportLogs = async (format: string = 'json') => {
        try {
            if (!hasLogs.value) {
                message.warning('没有日志可导出')
                return
            }

            let exportedData: string

            if (window.electronAPI?.logManagement) {
                const result = await window.electronAPI.logManagement.exportLogs({}, format)
                if (result.success) {
                    exportedData = result.data
                } else {
                    throw new Error(result.error || '导出日志失败')
                }
            } else {
                // 降级到前端导出
                const logText = filteredLogs.value
                    .map(log => `${log.timestamp.toISOString()} | ${log.level} | ${log.module} | ${log.message}`)
                    .join('\n')

                switch (format) {
                    case 'json':
                        exportedData = JSON.stringify(filteredLogs.value, null, 2)
                        break
                    case 'csv':
                        const headers = 'timestamp,level,module,message'
                        const csvRows = [
                            headers,
                            ...filteredLogs.value.map(log => [
                                log.timestamp.toISOString(),
                                log.level,
                                log.module,
                                `"${log.message.replace(/"/g, '""')}"`
                            ].join(','))
                        ]
                        exportedData = csvRows.join('\n')
                        break
                    default:
                        exportedData = logText
                }
            }

            // 创建下载链接
            const blob = new Blob([exportedData], {
                type: format === 'json' ? 'application/json' : 'text/plain'
            })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `logs_${new Date().toISOString().slice(0, 10)}.${format}`
            document.body.appendChild(a)
            a.click()
            document.body.removeChild(a)
            URL.revokeObjectURL(url)

            message.success('日志导出成功')
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : String(err)
            console.error('导出日志失败', errorMessage || '未知错误')
        }
    }

    const subscribe = async (id: string, filter?: LogFilterConditions) => {
        try {
            if (window.electronAPI?.logManagement) {
                // 恢复后端日志订阅支持
                const result = await (window.electronAPI as any).logManagement.subscribe(id, filter)
                if (result.success) {
                    // 订阅成功，设置日志更新监听
                    (window.electronAPI as any).onLogUpdate?.((newLogs: ParsedLogEntry[]) => {
                        // 恢复后端日志显示
                        logs.value = [...logs.value, ...newLogs]

                        // 限制最大日志数量
                        if (finalConfig.maxLogs && logs.value.length > finalConfig.maxLogs) {
                            logs.value = logs.value.slice(-finalConfig.maxLogs)
                        }

                        // 自动滚动到底部
                        if (autoScroll.value) {
                            nextTick(() => {
                                scrollToBottom()
                            })
                        }
                    })

                    // 恢复后端日志监听
                    window.electronAPI.onBackendLog?.((backendLog: any) => {
                        // 将后端日志转换为ParsedLogEntry格式
                        const parsedLog: ParsedLogEntry = {
                            id: `backend-log-${Date.now()}`,
                            timestamp: backendLog.timestamp ? new Date(backendLog.timestamp) : new Date(),
                            level: backendLog.level || 'INFO',
                            module: backendLog.module || '后端',
                            message: backendLog.message || '',
                            source: 'backend' as LogSource,
                            originalLog: backendLog.originalLog || backendLog.message || '',
                            isValid: backendLog.isValid !== false,
                            metadata: backendLog.metadata
                        }

                        // 确保后端日志使用与前端日志一致的样式
                        // 不再使用coloredLog，让前端日志系统自己处理颜色
                        delete parsedLog.coloredLog

                        logs.value = [...logs.value, parsedLog]

                        // 限制最大日志数量
                        if (finalConfig.maxLogs && logs.value.length > finalConfig.maxLogs) {
                            logs.value = logs.value.slice(-finalConfig.maxLogs)
                        }

                        // 自动滚动到底部
                        if (autoScroll.value) {
                            nextTick(() => {
                                scrollToBottom()
                            })
                        }
                    })
                } else {
                    throw new Error(result.error || '订阅日志失败')
                }
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : String(err)
            console.error('订阅日志失败', errorMessage || '未知错误')
        }
    }

    const unsubscribe = async (id: string) => {
        try {
            if (window.electronAPI?.logManagement) {
                const result = await (window.electronAPI as any).logManagement.unsubscribe(id)
                if (result.success) {
                    // 移除日志更新监听
                    (window.electronAPI as any).removeLogUpdateListener?.()
                } else {
                    throw new Error(result.error || '取消订阅失败')
                }
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : String(err)
            console.error('取消订阅失败', errorMessage || '未知错误')
        }
    }

    const selectLog = (log: ParsedLogEntry, index: number) => {
        // 可以在这里实现日志选中的逻辑
        console.log('选中日志:', log, index)
    }

    const scrollToTop = () => {
        // 滚动到顶部的逻辑需要在使用此组合式函数的组件中实现
        console.log('滚动到顶部')
    }

    const scrollToBottom = () => {
        // 滚动到底部的逻辑需要在使用此组合式函数的组件中实现
        console.log('滚动到底部')
    }

    const toggleAutoScroll = () => {
        autoScroll.value = !autoScroll.value
    }

    // 自动刷新定时器
    let refreshTimer: NodeJS.Timeout | null = null

    const startAutoRefresh = () => {
        if (refreshTimer) {
            clearInterval(refreshTimer)
        }

        if (finalConfig.autoRefresh) {
            refreshTimer = setInterval(() => {
                refresh()
            }, finalConfig.refreshInterval)
        }
    }

    const stopAutoRefresh = () => {
        if (refreshTimer) {
            clearInterval(refreshTimer)
            refreshTimer = null
        }
    }

    // 监听配置变化
    watch(() => finalConfig.autoRefresh, (newValue) => {
        if (newValue) {
            startAutoRefresh()
        } else {
            stopAutoRefresh()
        }
    })

    // 监听搜索关键词变化，防抖处理
    let searchTimer: NodeJS.Timeout | null = null
    watch(searchKeyword, () => {
        if (searchTimer) {
            clearTimeout(searchTimer)
        }

        searchTimer = setTimeout(() => {
            // 搜索逻辑已在computed中处理
        }, 300)
    })

    // 生命周期
    onMounted(() => {
        // 初始化时订阅日志
        subscribe(subscriberId.value)

        // 启动自动刷新
        if (finalConfig.autoRefresh) {
            startAutoRefresh()
        }

        // 初始加载日志
        refresh()
    })

    onUnmounted(() => {
        // 清理定时器
        stopAutoRefresh()
        if (searchTimer) {
            clearTimeout(searchTimer)
        }

        // 取消订阅
        unsubscribe(subscriberId.value)
    })

    // 返回状态和操作
    const state: LogViewerState = {
        logs: logs.value,
        loading: loading.value,
        error: error.value,
        selectedLogLevel: selectedLogLevel.value,
        selectedSource: selectedSource.value,
        searchKeyword: searchKeyword.value,
        enableColorHighlight: enableColorHighlight.value,
        autoScroll: autoScroll.value,
        stats: stats.value
    }

    const actions: LogViewerActions = {
        refresh,
        clear,
        export: exportLogs,
        subscribe,
        unsubscribe,
        selectLog,
        scrollToTop,
        scrollToBottom,
        toggleAutoScroll
    }

    return {
        // 状态
        ...state,

        // 计算属性
        hasLogs,
        hasFilteredLogs,
        isEmpty,
        filteredLogs,
        logLevels,
        logSources,

        // 操作
        ...actions,

        // 配置
        config: finalConfig
    }
}

// 导出类型已在文件顶部定义，无需重复导出